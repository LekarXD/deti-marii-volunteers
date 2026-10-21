import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID
from fastapi import Depends, Request, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.crypto import digest, seal, unseal
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.models import Session, RegistrationSession, StaffMembership, PermissionGrant, User

@dataclass
class Principal:
    user_id: UUID | None
    registration_id: UUID | None
    foundation_id: UUID
    session_id: UUID
    is_staff: bool
    actor_id: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    grants: tuple = ()
    mfa_at: datetime | None = None
    def has_permission(self, name, scope_type="foundation", scope_id=None):
        return self.is_staff and any(p == name and (t == "foundation" or (t == scope_type and i == scope_id)) for p,t,i in self.grants)

async def resolve_principal(db, session):
    is_staff, grants = False, ()
    if session.user_id:
        user = await db.get(User, session.user_id)
        if user is None or user.account_state != "active" or user.foundation_id != session.foundation_id:
            raise ApiError(401, "session_invalid", "Сессия недействительна")
        membership = await db.scalar(select(StaffMembership).where(StaffMembership.user_id == session.user_id, StaffMembership.foundation_id == session.foundation_id, StaffMembership.revoked_at.is_(None)))
        if membership and session.mfa_at:
            is_staff = True
            rows = (await db.scalars(select(PermissionGrant).where(PermissionGrant.membership_id == membership.id, PermissionGrant.revoked_at.is_(None)))).all()
            grants = tuple((g.permission,g.scope_type,g.scope_id) for g in rows)
    else:
        registration = await db.get(RegistrationSession, session.registration_id)
        if registration is None or registration.expires_at <= utcnow() or registration.claimed_user_id:
            raise ApiError(401, "session_invalid", "Сессия недействительна")
    return Principal(session.user_id, session.registration_id, session.foundation_id, session.id, is_staff, str(session.user_id or session.registration_id), frozenset(p for p,t,i in grants if t == "foundation"), grants, session.mfa_at)

async def get_session_row(request, db):
    raw = request.cookies.get("opora_session")
    if not raw:
        return None
    return await db.scalar(select(Session).where(Session.token_hash == digest(raw), Session.revoked_at.is_(None), Session.expires_at > utcnow()))

async def get_principal(request: Request, db: AsyncSession = Depends(get_db)) -> Principal:
    session = await get_session_row(request, db)
    if session is None:
        raise ApiError(401, "session_expired", "Войдите снова")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("origin") not in get_settings().trusted_origins:
            raise ApiError(403, "origin_rejected", "Источник запроса не разрешён")
        csrf = request.headers.get("x-csrf-token", "")
        if not csrf or not secrets.compare_digest(digest(csrf), session.csrf_hash):
            raise ApiError(403, "csrf_rejected", "Обновите страницу и повторите действие")
    principal = await resolve_principal(db, session)
    request.state.principal = principal
    return principal

def require_permission(name):
    async def check(principal: Principal = Depends(get_principal)):
        if not principal.has_permission(name):
            raise ApiError(403, "permission_denied", "Недостаточно прав")
        return principal
    return check

async def authz_guard(db, principal):
    key = int.from_bytes(hashlib.sha256(f"authz:{principal.foundation_id}:{principal.user_id or principal.registration_id}".encode()).digest()[:8], "big", signed=True)
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
    row = await db.get(Session, principal.session_id, populate_existing=True)
    if row is None or row.revoked_at or row.expires_at <= utcnow():
        raise ApiError(401, "session_expired", "Войдите снова")
    fresh = await resolve_principal(db, row)
    principal.is_staff, principal.permissions, principal.grants = fresh.is_staff, fresh.permissions, fresh.grants
    return principal

async def issue_session(db, response, *, user_id=None, registration_id=None, mfa_at=None):
    settings = get_settings()
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    session = Session(foundation_id=settings.foundation_id, token_hash=digest(token), csrf_hash=digest(csrf), csrf_cipher=seal(csrf), user_id=user_id, registration_id=registration_id, expires_at=utcnow()+timedelta(hours=settings.session_hours), mfa_at=mfa_at)
    db.add(session)
    await db.flush()
    response.set_cookie("opora_session", token, httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=settings.session_hours*3600, path=settings.app_mount_prefix or "/")
    return session, csrf

async def session_view(db, session):
    principal = await resolve_principal(db, session)
    return {"user_id": str(principal.user_id) if principal.user_id else None, "registration_id": str(principal.registration_id) if principal.registration_id else None, "foundation_id": str(principal.foundation_id), "is_staff": principal.is_staff, "permissions": sorted(principal.permissions), "csrf_token": unseal(session.csrf_cipher), "actor_id": principal.actor_id, "mfa_required": bool(principal.user_id and not session.mfa_at and await db.scalar(select(StaffMembership.id).where(StaffMembership.user_id == principal.user_id, StaffMembership.revoked_at.is_(None))))}

@dataclass(frozen=True)
class BackgroundStaffAuthorization:
    """Read-only grants for an explicit persisted schedule; never an interactive identity."""
    user_id:UUID
    foundation_id:UUID
    membership_id:UUID
    grants:tuple
    def has_permission(self,name,scope_type='foundation',scope_id=None):
        return any(p==name and (t=='foundation' or (t==scope_type and i==scope_id)) for p,t,i in self.grants)

async def load_background_staff_authorization(db,foundation_id,user_id):
    from app.core.models import MfaFactor
    user=await db.scalar(select(User).where(User.id==user_id,User.foundation_id==foundation_id,User.account_state=='active'))
    member=await db.scalar(select(StaffMembership).where(StaffMembership.user_id==user_id,StaffMembership.foundation_id==foundation_id,StaffMembership.revoked_at.is_(None)))
    factor=await db.scalar(select(MfaFactor.id).where(MfaFactor.user_id==user_id,MfaFactor.confirmed_at.is_not(None)))
    if user is None or member is None or factor is None:return None
    rows=(await db.scalars(select(PermissionGrant).where(PermissionGrant.membership_id==member.id,PermissionGrant.revoked_at.is_(None)))).all()
    return BackgroundStaffAuthorization(user_id,foundation_id,member.id,tuple((g.permission,g.scope_type,g.scope_id) for g in rows))

async def lock_background_authorizations(db,foundation_id,user_ids):
    """Acquire before contact_guard/domain rows, matching interactive grant/revoke keys."""
    ids={UUID(str(value)) for value in user_ids}
    if not 1<=len(ids)<=1000:raise ApiError(422,'background_authorization_limit','Проверьте участников фоновой задачи')
    keys=sorted({int.from_bytes(hashlib.sha256(f'authz:{foundation_id}:{uid}'.encode()).digest()[:8],'big',signed=True) for uid in ids})
    for key in keys:await db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':key})
    transaction=db.sync_session.get_transaction()
    held=db.info.setdefault('background_authorization_locks',{})
    for uid in ids:held[(UUID(str(foundation_id)),uid)]=transaction

def assert_background_authorizations_locked(db,foundation_id,user_ids):
    transaction=db.sync_session.get_transaction()
    held=db.info.get('background_authorization_locks',{})
    if transaction is None or any(held.get((UUID(str(foundation_id)),UUID(str(uid)))) is not transaction for uid in user_ids):
        raise ApiError(409,'background_authorization_changed','Область фонового уведомления изменилась')
