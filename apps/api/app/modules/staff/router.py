from datetime import timedelta
from uuid import UUID
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal, require_permission, authz_guard
from app.core.audit import audit
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.models import User, StaffMembership, PermissionGrant, Session
router = APIRouter(prefix="/api/v1/coord/staff", tags=["staff"])
class GrantInput(BaseModel):
    user_id: UUID
    permission: str = Field(min_length=3, max_length=100)
    scope_type: str = "foundation"
    scope_id: UUID | None = None

async def grant_guard(db, principal, target):
    await authz_guard(db, principal)
    if not principal.has_permission("staff.manage") or not principal.mfa_at or principal.mfa_at < utcnow()-timedelta(minutes=10):
        raise ApiError(403, "step_up_required", "Подтвердите вход перед изменением доступа")
    # Same lock protocol as sensitive commands, for the grant target.
    from hashlib import sha256
    key = int.from_bytes(sha256(f"authz:{principal.foundation_id}:{target}".encode()).digest()[:8], "big", signed=True)
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})

@router.post("/grants", operation_id="staff_grant")
async def grant(body: GrantInput, principal: Principal = Depends(require_permission("staff.manage")), db: AsyncSession = Depends(get_db)):
    await grant_guard(db, principal, body.user_id)
    user = await db.get(User, body.user_id)
    if not user or user.foundation_id != principal.foundation_id:
        raise ApiError(404, "user_not_found", "Пользователь не найден")
    if body.scope_type not in ("foundation", "program", "group") or (body.scope_type != "foundation" and body.scope_id is None):
        raise ApiError(422, "invalid_scope", "Укажите область доступа")
    membership = await db.scalar(select(StaffMembership).where(StaffMembership.user_id == user.id, StaffMembership.foundation_id == principal.foundation_id))
    if not membership:
        membership = StaffMembership(user_id=user.id, foundation_id=principal.foundation_id)
        db.add(membership)
        await db.flush()
    membership.revoked_at = None
    row = PermissionGrant(membership_id=membership.id, permission=body.permission, scope_type=body.scope_type, scope_id=body.scope_id)
    db.add(row)
    user.authz_version += 1
    await db.flush()
    audit(db, principal, "staff.grant", "permission_grant", row.id, ("permission", "scope"))
    await db.commit()
    return {"id": str(row.id), "permission": row.permission}

@router.post("/grants/{grant_id}/revoke", operation_id="staff_revoke")
async def revoke(grant_id: UUID, principal: Principal = Depends(require_permission("staff.manage")), db: AsyncSession = Depends(get_db)):
    row = await db.get(PermissionGrant, grant_id)
    membership = await db.get(StaffMembership, row.membership_id) if row else None
    if not membership or membership.foundation_id != principal.foundation_id:
        raise ApiError(404, "grant_not_found", "Право не найдено")
    await grant_guard(db, principal, membership.user_id)
    row.revoked_at = utcnow()
    user = await db.get(User, membership.user_id)
    user.authz_version += 1
    audit(db, principal, "staff.revoke", "permission_grant", row.id, ("revoked_at",))
    await db.commit()
    return {"status": "revoked"}
