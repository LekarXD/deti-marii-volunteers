"""Email/password entry with bounded, single-use email possession proofs."""
import asyncio
import hashlib
import hmac
import re
import secrets
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.audit import audit
from app.core.auth import Principal, authz_guard, get_principal, issue_session, session_view
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.crypto import digest
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.model_loader import claim_registration
from app.core.models import ContactChannel, RegistrationSession, Session, User
from app.core.rate_limit import failure_limit, rate_limit, record_failure
from app.worker.queue import enqueue_outbox
from .password_models import PasswordChallenge, PasswordCredential
from .schemas import AuthSessionView, ChallengeView

router = APIRouter()
# OWASP equivalent minimum configuration: 32 MiB, N=2^15/r=8/p=3.
# https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html#scrypt
# One dedicated KDF worker bounds actual memory even when requests are cancelled.
_KDF_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix='password-kdf')
_KDF_PENDING = 0
_N, _R, _P = 32768, 8, 3
_DUMMY = 'scrypt$32768$8$3$' + ('00' * 16) + '$' + ('00' * 32)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P, maxmem=64*1024*1024, dklen=32)
    return f'scrypt${_N}${_R}${_P}${salt.hex()}${value.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split('$')
        if (algorithm, int(n), int(r), int(p)) != ('scrypt', _N, _R, _P) or len(salt) != 32 or len(expected) != 64:
            return False
        actual = hash_password(password, bytes.fromhex(salt)).split('$')[-1]
        return secrets.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


async def kdf(function, *args):
    global _KDF_PENDING
    if _KDF_PENDING >= 8:
        raise ApiError(429, 'rate_limited', 'Слишком много попыток. Попробуйте позже', retryable=True)
    _KDF_PENDING += 1
    future = asyncio.get_running_loop().run_in_executor(_KDF_POOL, function, *args)
    # Shield keeps a cancelled HTTP task from cancelling the queued KDF work.
    def finished(_):
        global _KDF_PENDING
        _KDF_PENDING -= 1
    future.add_done_callback(finished)
    return await asyncio.shield(future)


def code_digest(challenge_id, code):
    return hmac.new(get_settings().secret_key.encode(), f'email-proof:{challenge_id}:{code}'.encode(), hashlib.sha256).hexdigest()


class EmailInput(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class PasswordInput(EmailInput):
    password: str = Field(min_length=12, max_length=128)


class CodeInput(BaseModel):
    challenge_id: UUID
    code: str = Field(min_length=1, max_length=128)


class ResetVerifyInput(CodeInput):
    password: str = Field(min_length=12, max_length=128)


def normalize_email(value):
    value = value.strip().lower()
    if not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value):
        raise ApiError(422, 'invalid_contact', 'Укажите корректную почту')
    return value


async def anonymous(db, principal):
    await authz_guard(db, principal)
    if principal.user_id or not principal.registration_id:
        raise ApiError(409, 'already_authenticated', 'Вы уже вошли в аккаунт')


async def limits(db, principal, request, email, operation, limit=3):
    await rate_limit(db, principal.actor_id, operation, limit=limit)
    await rate_limit(db, email, operation+'_email', limit=limit)
    await rate_limit(db, request.client.host if request.client else 'unknown', operation+'_ip', limit=30)


async def contact(db, email):
    return await db.scalar(select(ContactChannel).where(ContactChannel.type == 'email', ContactChannel.normalized_value == email))


async def lock_user(db, foundation_id, user_id):
    key = int.from_bytes(hashlib.sha256(f'authz:{foundation_id}:{user_id}'.encode()).digest()[:8], 'big', signed=True)
    await db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': key})


async def create_challenge(db, principal, email, purpose, *, password_hash=None, user_id=None, credential_version=None, demo_code_allowed=False):
    # Resend replaces only proofs belonging to this browser and email/purpose.
    await db.execute(update(PasswordChallenge).where(
        PasswordChallenge.bound_session_id == principal.session_id,
        PasswordChallenge.normalized_contact == email,
        PasswordChallenge.purpose == purpose, PasswordChallenge.consumed_at.is_(None)
    ).values(consumed_at=utcnow()))
    identity, code = uuid4(), f'{secrets.randbelow(1000000):06d}'
    row = PasswordChallenge(id=identity, foundation_id=principal.foundation_id,
        bound_session_id=principal.session_id, normalized_contact=email, purpose=purpose,
        code_hash=code_digest(identity, code), pending_password_hash=password_hash,
        user_id=user_id, credential_version=credential_version, demo_code_allowed=demo_code_allowed, expires_at=utcnow()+timedelta(minutes=10))
    db.add(row)
    await db.flush()
    # Unknown reset accounts get an indistinguishable inert proof and no email.
    if not demo_code_allowed and (purpose == 'register' or user_id):
        enqueue_outbox(db, principal.foundation_id, 'email', {'to': email, 'purpose': purpose,
            'challenge_id': str(identity), 'code': code})
    audit(db, principal, 'auth.'+purpose+'.request', 'password_challenge', identity)
    await db.commit()
    return {'demo_code_allowed': demo_code_allowed, 'challenge_id': identity, 'status': 'queued', 'delivery': 'dev_inbox' if get_settings().dev_inbox else 'pending'}


@router.post('/register', operation_id='auth_password_register', response_model=ChallengeView)
async def register(body: PasswordInput, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    await anonymous(db, principal)
    email = normalize_email(body.email)
    await limits(db, principal, request, email, 'password_register')
    if await contact(db, email):
        await db.commit()
        raise ApiError(409, 'account_exists', 'Эта почта уже зарегистрирована. Войдите или восстановите пароль')
    encoded = await kdf(hash_password, body.password)
    return await create_challenge(db, principal, email, 'register', password_hash=encoded, demo_code_allowed=get_settings().demo_email_codes)


async def valid_challenge(db, principal, body, purpose):
    row = await db.scalar(select(PasswordChallenge).where(PasswordChallenge.id == body.challenge_id).with_for_update())
    if not row or row.foundation_id != principal.foundation_id or row.bound_session_id != principal.session_id or row.purpose != purpose or row.consumed_at or row.expires_at <= utcnow() or row.attempts >= 5:
        await db.commit()
        raise ApiError(400, 'challenge_invalid', 'Код недействителен или истёк')
    row.attempts += 1
    demo = get_settings().demo_email_codes and row.demo_code_allowed and bool(body.code.strip())
    if not demo and (not re.fullmatch(r'[0-9]{6}', body.code) or not secrets.compare_digest(row.code_hash, code_digest(row.id, body.code))):
        await db.commit()
        raise ApiError(400, 'challenge_invalid', 'Код недействителен или истёк')
    return row


async def authenticated(db, principal, response, user_id):
    old = await db.get(Session, principal.session_id)
    old.revoked_at = utcnow()
    new, _ = await issue_session(db, response, user_id=user_id)
    result = await session_view(db, new)
    await db.commit()
    return result


@router.post('/register/verify', operation_id='auth_password_register_verify', response_model=AuthSessionView)
async def register_verify(body: CodeInput, response: Response, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    await anonymous(db, principal)
    await limits(db, principal, request, str(body.challenge_id), 'password_register_verify', limit=20)
    row = await valid_challenge(db, principal, body, 'register')
    # Same contact advisory key as legacy verified login/contact changes.
    await db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': int(digest(row.normalized_contact)[:15], 16)})
    if await contact(db, row.normalized_contact):
        row.consumed_at = utcnow()
        await db.commit()
        raise ApiError(409, 'account_exists', 'Эта почта уже зарегистрирована. Войдите или восстановите пароль')
    user = User(foundation_id=principal.foundation_id)
    db.add(user)
    await db.flush()
    db.add(ContactChannel(user_id=user.id, normalized_value=row.normalized_contact, verified_at=utcnow()))
    db.add(PasswordCredential(user_id=user.id, password_hash=row.pending_password_hash, demo_created=row.demo_code_allowed))
    row.consumed_at = utcnow()
    registration = await db.get(RegistrationSession, principal.registration_id)
    registration.verified_email, registration.claimed_user_id = row.normalized_contact, user.id
    await claim_registration(db, registration.id, user.id, newly_created_user=True)
    audit(db, principal, 'auth.register.verify', 'user', user.id)
    return await authenticated(db, principal, response, user.id)


@router.post('/login', operation_id='auth_password_login', response_model=AuthSessionView)
async def login(body: PasswordInput, request: Request, response: Response, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    await anonymous(db, principal)
    email = normalize_email(body.email)
    # One account may be used on many devices at once: only wrong passwords count per email and network.
    host = request.client.host if request.client else 'unknown'
    await rate_limit(db, principal.actor_id, 'password_login', limit=10)
    await failure_limit(db, email, 'password_login_email', limit=10)
    await failure_limit(db, host, 'password_login_ip', limit=30)
    channel = await contact(db, email)
    credential = None
    user = await db.get(User, channel.user_id) if channel else None
    if user and user.foundation_id == principal.foundation_id:
        await lock_user(db, principal.foundation_id, user.id)
        # Contact replacement may have committed while this login waited for the user lock.
        user = await db.get(User, user.id, populate_existing=True)
        channel = await db.scalar(select(ContactChannel).where(ContactChannel.type == 'email', ContactChannel.normalized_value == email, ContactChannel.user_id == user.id).execution_options(populate_existing=True))
        if channel:
            credential = await db.scalar(select(PasswordCredential).where(PasswordCredential.user_id == user.id).execution_options(populate_existing=True))
    encoded = credential.password_hash if credential else _DUMMY
    matches = await kdf(verify_password, body.password, encoded)
    if not matches or not credential or not user or user.account_state != 'active':
        await record_failure(db, email, 'password_login_email')
        await record_failure(db, host, 'password_login_ip')
        await db.commit()
        raise ApiError(401, 'invalid_credentials', 'Проверьте почту и пароль')
    audit(db, principal, 'auth.password.login', 'user', user.id)
    return await authenticated(db, principal, response, user.id)


@router.post('/password/reset', operation_id='auth_password_reset_request', response_model=ChallengeView)
async def reset_request(body: EmailInput, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    await anonymous(db, principal)
    email = normalize_email(body.email)
    await limits(db, principal, request, email, 'password_reset')
    channel = await contact(db, email)
    user = await db.get(User, channel.user_id) if channel else None
    eligible = user and user.foundation_id == principal.foundation_id and user.account_state == 'active'
    credential = await db.scalar(select(PasswordCredential).where(PasswordCredential.user_id == user.id)) if eligible else None
    # Equal KDF work for known and unknown emails reduces obvious timing disclosure.
    await kdf(verify_password, secrets.token_urlsafe(20), _DUMMY)
    return await create_challenge(db, principal, email, 'password_reset', user_id=user.id if eligible else None, credential_version=credential.version if credential else 0, demo_code_allowed=bool(get_settings().demo_email_codes and credential and credential.demo_created))


@router.post('/password/reset/verify', operation_id='auth_password_reset_verify', response_model=AuthSessionView)
async def reset_verify(body: ResetVerifyInput, request: Request, response: Response, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    await anonymous(db, principal)
    await limits(db, principal, request, str(body.challenge_id), 'password_reset_verify', limit=20)
    # User authorization lock precedes challenge/domain rows, matching logout.
    peek = await db.get(PasswordChallenge, body.challenge_id)
    if peek and peek.user_id and peek.bound_session_id == principal.session_id:
        await lock_user(db, principal.foundation_id, peek.user_id)
    row = await valid_challenge(db, principal, body, 'password_reset')
    user = await db.get(User, row.user_id) if row.user_id else None
    channel = await contact(db, row.normalized_contact)
    credential = await db.scalar(select(PasswordCredential).where(PasswordCredential.user_id == row.user_id)) if user else None
    if not user or user.foundation_id != principal.foundation_id or user.account_state != 'active' or not channel or channel.user_id != user.id or (credential.version if credential else 0) != row.credential_version:
        row.consumed_at = utcnow()
        await db.commit()
        raise ApiError(400, 'challenge_invalid', 'Код недействителен или истёк')
    encoded = await kdf(hash_password, body.password)
    if credential:
        credential.password_hash = encoded
        credential.version += 1
    else:
        db.add(PasswordCredential(user_id=user.id, password_hash=encoded))
    await db.execute(update(Session).where(Session.user_id == user.id, Session.revoked_at.is_(None)).values(revoked_at=utcnow()))
    await db.execute(update(PasswordChallenge).where(PasswordChallenge.user_id == user.id, PasswordChallenge.consumed_at.is_(None)).values(consumed_at=utcnow()))
    row.consumed_at = utcnow()
    audit(db, principal, 'auth.password.reset', 'user', user.id)
    return await authenticated(db, principal, response, user.id)
