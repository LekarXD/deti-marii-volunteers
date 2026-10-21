import secrets
from datetime import timedelta
from uuid import UUID
import pyotp
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal, get_principal, get_session_row, issue_session, session_view, authz_guard
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.crypto import digest, seal, unseal
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.models import AuthChallenge, ContactChannel, Foundation, User, RegistrationSession, Session, MfaFactor, MfaRecovery, StaffMembership
from app.core.rate_limit import rate_limit
from app.core.audit import audit
from app.worker.queue import enqueue_outbox
from .schemas import AuthSessionView, MfaSessionView, ChallengeView, MfaEnrollmentView, AuthStatusView

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

class ChallengeInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    purpose: str = "login"

class VerifyInput(BaseModel):
    challenge_id: UUID
    token: str = Field(min_length=20, max_length=200)

class MfaInput(BaseModel):
    code: str = Field(min_length=6, max_length=100)

@router.get("/session", operation_id="auth_session", response_model=AuthSessionView)
async def session(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    existing = await get_session_row(request, db)
    if existing:
        return await session_view(db, existing)
    if await db.get(Foundation, get_settings().foundation_id) is None:
        raise ApiError(503, "installation_uninitialized", "Выполните настройку фонда", retryable=True)
    registration = RegistrationSession(foundation_id=get_settings().foundation_id, expires_at=utcnow()+timedelta(days=7))
    db.add(registration)
    await db.flush()
    created, _ = await issue_session(db, response, registration_id=registration.id)
    result = await session_view(db, created)
    await db.commit()
    return result

@router.post("/challenges", operation_id="auth_challenge_create", response_model=ChallengeView)
async def challenge(body: ChallengeInput, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    email = body.email.strip().lower()
    if body.purpose != "login" or "@" not in email or any(c.isspace() for c in email):
        raise ApiError(422, "invalid_contact", "Укажите корректную почту")
    await rate_limit(db, principal.actor_id, "challenge")
    await rate_limit(db, email, "challenge_contact")
    await rate_limit(db, request.client.host if request.client else "unknown", "challenge_ip", limit=30)
    raw = secrets.token_urlsafe(32)
    row = AuthChallenge(foundation_id=principal.foundation_id, registration_id=principal.registration_id, token_hash=digest(raw), normalized_contact=email, purpose="login", expires_at=utcnow()+timedelta(minutes=15))
    db.add(row)
    await db.flush()
    enqueue_outbox(db, principal.foundation_id, "email", {"to": email, "purpose": "login", "challenge_id": str(row.id), "token": raw})
    audit(db, principal, "auth.challenge", "auth_challenge", row.id)
    await db.commit()
    return {"challenge_id": str(row.id), "status": "queued", "delivery": "dev_inbox" if get_settings().dev_inbox else "pending"}

@router.post("/challenges/verify", operation_id="auth_challenge_verify", response_model=AuthSessionView)
async def verify(body: VerifyInput, response: Response, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    await rate_limit(db, principal.actor_id, "challenge_verify", limit=20)
    row = await db.scalar(select(AuthChallenge).where(AuthChallenge.id == body.challenge_id).with_for_update())
    valid = row and row.foundation_id == principal.foundation_id and row.registration_id == principal.registration_id and row.purpose == "login" and row.consumed_at is None and row.expires_at > utcnow() and row.attempts < 5
    if not valid:
        await db.commit()
        raise ApiError(400, "challenge_invalid", "Код недействителен или истёк")
    row.attempts += 1
    if not secrets.compare_digest(row.token_hash, digest(body.token)):
        await db.commit()
        raise ApiError(400, "challenge_invalid", "Код недействителен или истёк")
    row.consumed_at = utcnow()
    # Contact lock serializes first login; identity derives only from verified possession.
    from sqlalchemy import text
    lock = int(digest(row.normalized_contact)[:15], 16)
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    contact = await db.scalar(select(ContactChannel).where(ContactChannel.normalized_value == row.normalized_contact))
    if contact:
        user = await db.get(User, contact.user_id)
        if user.foundation_id != principal.foundation_id:
            raise ApiError(403, "contact_unavailable", "Контакт недоступен")
    else:
        user = User(foundation_id=principal.foundation_id)
        db.add(user)
        await db.flush()
        db.add(ContactChannel(user_id=user.id, normalized_value=row.normalized_contact, verified_at=utcnow()))
    if principal.registration_id:
        registration = await db.get(RegistrationSession, principal.registration_id)
        registration.verified_email, registration.claimed_user_id = row.normalized_contact, user.id
        # Transfer only the current session's owned domain records, within this transaction.
        from app.core.model_loader import claim_registration
        await claim_registration(db, principal.registration_id, user.id)
    old = await db.get(Session, principal.session_id)
    old.revoked_at = utcnow()
    new, _ = await issue_session(db, response, user_id=user.id)
    audit(db, principal, "auth.verify", "user", user.id)
    result = await session_view(db, new)
    await db.commit()
    return result

@router.post("/logout", operation_id="auth_logout", response_model=AuthStatusView)
async def logout(response: Response, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    await authz_guard(db, principal)
    row = await db.get(Session, principal.session_id)
    row.revoked_at = utcnow()
    audit(db, principal, "auth.logout", "session", row.id)
    await db.commit()
    response.delete_cookie("opora_session", path="/")
    return {"status": "logged_out"}

@router.post("/mfa/enroll", operation_id="auth_mfa_enroll", response_model=MfaEnrollmentView)
async def enroll(principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    if not principal.user_id or not await db.scalar(select(StaffMembership.id).where(StaffMembership.user_id == principal.user_id, StaffMembership.revoked_at.is_(None))):
        raise ApiError(403, "staff_required", "Недостаточно прав")
    await authz_guard(db, principal)
    factor = await db.scalar(select(MfaFactor).where(MfaFactor.user_id == principal.user_id).with_for_update())
    if factor and factor.confirmed_at:
        raise ApiError(409, "mfa_already_enrolled", "Фактор уже настроен")
    secret = pyotp.random_base32()
    if factor:
        factor.secret_cipher = seal(secret)
    else:
        db.add(MfaFactor(user_id=principal.user_id, secret_cipher=seal(secret)))
    audit(db, principal, "mfa.enroll", "user", principal.user_id)
    await db.commit()
    return {"secret": secret, "provisioning_uri": pyotp.TOTP(secret).provisioning_uri(str(principal.user_id), issuer_name="Опора")}

@router.post("/mfa/verify", operation_id="auth_mfa_verify", response_model=MfaSessionView)
async def mfa_verify(body: MfaInput, response: Response, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    if not principal.user_id:
        raise ApiError(403, "user_required", "Войдите в аккаунт")
    await rate_limit(db, principal.actor_id, "mfa", limit=10)
    factor = await db.scalar(select(MfaFactor).where(MfaFactor.user_id == principal.user_id).with_for_update())
    recovery = await db.scalar(select(MfaRecovery).where(MfaRecovery.user_id == principal.user_id, MfaRecovery.code_hash == digest(body.code), MfaRecovery.consumed_at.is_(None)).with_for_update())
    counter = int(utcnow().timestamp()) // 30
    matched_counter = next((c for c in (counter-1,counter,counter+1) if factor and pyotp.TOTP(unseal(factor.secret_cipher)).at(c*30) == body.code and c > factor.last_counter), None)
    if not factor or (matched_counter is None and not recovery):
        await db.commit()
        raise ApiError(400, "mfa_invalid", "Код недействителен")
    first = factor.confirmed_at is None
    if recovery:
        recovery.consumed_at = utcnow()
    else:
        factor.last_counter = matched_counter
    factor.confirmed_at = factor.confirmed_at or utcnow()
    codes = []
    if first:
        codes = [secrets.token_hex(8) for _ in range(8)]
        db.add_all([MfaRecovery(user_id=principal.user_id, code_hash=digest(c)) for c in codes])
    old = await db.get(Session, principal.session_id)
    old.revoked_at = utcnow()
    new, _ = await issue_session(db, response, user_id=principal.user_id, mfa_at=utcnow())
    audit(db, principal, "mfa.verify", "session", new.id)
    result = await session_view(db, new)
    result["recovery_codes"] = codes
    await db.commit()
    return result

@router.post("/mfa/revoke", operation_id="auth_mfa_revoke", response_model=AuthStatusView)
async def mfa_revoke(principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    await authz_guard(db, principal)
    if not principal.user_id or not principal.mfa_at or principal.mfa_at < utcnow()-timedelta(minutes=10):
        raise ApiError(403, "step_up_required", "Подтвердите вход перед изменением фактора")
    from sqlalchemy import delete
    await db.execute(delete(MfaRecovery).where(MfaRecovery.user_id == principal.user_id))
    await db.execute(delete(MfaFactor).where(MfaFactor.user_id == principal.user_id))
    await db.execute(update(Session).where(Session.user_id == principal.user_id, Session.revoked_at.is_(None)).values(revoked_at=utcnow()))
    audit(db, principal, "mfa.revoke", "user", principal.user_id)
    await db.commit()
    return {"status": "revoked"}
