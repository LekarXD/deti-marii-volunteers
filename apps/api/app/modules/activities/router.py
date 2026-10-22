from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, get_principal, require_permission, authz_guard
from app.core.audit import audit
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.idempotency import begin_command, finish_command
from .models import Opportunity, OpportunityRoleLink, OpportunityVersion, VolunteerRole, VolunteerRoleVersion
from .schemas import OpportunityCreate, OpportunityPage, OpportunityUpdate, OpportunityView, ActivityRevisionView, RoleCreate, RolePage, RoleUpdate, RoleUsage, RoleView, VersionCommand
from . import service

router = APIRouter(tags=['activities'])
roles_staff = require_permission('roles.manage')
opportunities_staff = require_permission('opportunities.manage')


async def command(db, principal, operation, key, body, action, request):
    payload = body.model_dump(mode='json')
    try:
        await authz_guard(db, principal)
        permission = ('roles.manage' if operation.startswith('roles.') else 'schedule.manage' if operation.startswith('calendar.') else 'assignments.manage' if operation.startswith('assignments.') else None if operation.startswith('participation.') else 'opportunities.manage')
        if permission and not principal.has_permission(permission):
            raise ApiError(403, 'permission_denied', 'Недостаточно прав.')
        if operation.startswith('participation.') and principal.user_id is None:
            raise ApiError(403, 'user_required', 'Подтвердите контакт и войдите в свой кабинет.')
        replay = await begin_command(db, principal, operation, key, payload)
        if replay is not None:
            await db.commit()
            return replay
        result = await action()
        result_json = result.model_dump(mode='json')
        audit(db, principal, operation, 'role' if operation.startswith('roles.') else 'event' if operation.startswith('calendar.') else 'opportunity', result.id,
              fields=[name for name in payload if name != 'expected_version'], request_id=getattr(request.state, 'request_id', None))
        await finish_command(db, principal, operation, key, result_json)
        await db.commit()
        return result_json
    except IntegrityError as exc:
        await db.rollback()
        if 'reservation_no_overlap' in str(exc.orig):
            raise ApiError(409, 'participation_overlap', 'В это время уже есть подтверждённое занятие или встреча.') from exc
        if 'uq_active_role_title' in str(exc.orig):
            raise ApiError(409, 'duplicate_role_title', 'Действующая роль с таким названием уже есть.', field_errors={'title': 'Выберите другое название.'}) from exc
        raise
    except Exception:
        await db.rollback()
        raise


@router.get('/coord/roles', response_model=RolePage, operation_id='listRoles')
async def list_roles(archived: bool=False, q: str=Query('', max_length=200), cursor: UUID | None=None, limit: int=Query(50, ge=1, le=100), principal: Principal=Depends(roles_staff), db: AsyncSession=Depends(get_db)):
    query = select(VolunteerRole).where(VolunteerRole.foundation_id == principal.foundation_id,
        VolunteerRole.archived_at.is_not(None) if archived else VolunteerRole.archived_at.is_(None))
    if q:
        query = query.where(VolunteerRole.normalized_title.contains(service.normalized_title(q), autoescape=True))
    if cursor:
        query = query.where(VolunteerRole.id > cursor)
    rows = list((await db.scalars(query.order_by(VolunteerRole.id).limit(limit+1))).all())
    return RolePage(items=[service.role_view(r) for r in rows[:limit]], next_cursor=rows[limit-1].id if len(rows)>limit else None)


@router.get('/coord/roles/{role_id}', response_model=RoleView, operation_id='getRole')
async def get_role(role_id: UUID, principal: Principal=Depends(roles_staff), db: AsyncSession=Depends(get_db)):
    return service.role_view(await service.find_role(db, principal, role_id))


@router.post('/coord/roles', response_model=RoleView, operation_id='createRole')
async def create_role(body: RoleCreate, request: Request, key: str=Header(alias='Idempotency-Key'), principal: Principal=Depends(roles_staff), db: AsyncSession=Depends(get_db)):
    return await command(db, principal, 'roles.create', key, body, lambda: service.create_role(db, principal, body), request)


@router.patch('/coord/roles/{role_id}', response_model=RoleView, operation_id='updateRole')
async def update_role(role_id: UUID, body: RoleUpdate, request: Request, key: str=Header(alias='Idempotency-Key'), principal: Principal=Depends(roles_staff), db: AsyncSession=Depends(get_db)):
    return await command(db, principal, f'roles.update:{role_id}', key, body, lambda: service.update_role(db, principal, role_id, body), request)


@router.post('/coord/roles/{role_id}/archive', response_model=RoleView, operation_id='archiveRole')
async def archive_role(role_id: UUID, body: VersionCommand, request: Request, key: str=Header(alias='Idempotency-Key'), principal: Principal=Depends(roles_staff), db: AsyncSession=Depends(get_db)):
    return await command(db, principal, f'roles.archive:{role_id}', key, body, lambda: service.archive_role(db, principal, role_id, body, True), request)


@router.post('/coord/roles/{role_id}/restore', response_model=RoleView, operation_id='restoreRole')
async def restore_role(role_id: UUID, body: VersionCommand, request: Request, key: str=Header(alias='Idempotency-Key'), principal: Principal=Depends(roles_staff), db: AsyncSession=Depends(get_db)):
    return await command(db, principal, f'roles.restore:{role_id}', key, body, lambda: service.archive_role(db, principal, role_id, body, False), request)


@router.get('/coord/roles/{role_id}/usage', response_model=RoleUsage, operation_id='getRoleUsage')
async def role_usage(role_id: UUID, principal: Principal=Depends(roles_staff), db: AsyncSession=Depends(get_db)):
    await service.find_role(db, principal, role_id)
    rows = (await db.execute(select(Opportunity.id, Opportunity.title, Opportunity.state).join(OpportunityRoleLink, OpportunityRoleLink.opportunity_id == Opportunity.id).where(OpportunityRoleLink.role_id == role_id, Opportunity.foundation_id == principal.foundation_id))).all()
    return RoleUsage(opportunity_count=len(rows), opportunities=[{'id': str(r.id), 'title': r.title, 'state': r.state} for r in rows])


@router.get('/coord/roles/{role_id}/history', response_model=list[ActivityRevisionView], operation_id='getRoleHistory')
async def role_history(role_id: UUID, principal: Principal=Depends(roles_staff), db: AsyncSession=Depends(get_db)):
    await service.find_role(db, principal, role_id)
    rows = (await db.scalars(select(VolunteerRoleVersion).where(VolunteerRoleVersion.role_id == role_id).order_by(VolunteerRoleVersion.version.desc()).limit(100))).all()
    return [ActivityRevisionView(version=r.version, snapshot=r.snapshot, created_at=r.created_at) for r in rows]


async def opportunity_list(db, principal, staff, q, state, regularity, format, cursor, limit):
    query = select(Opportunity).where(Opportunity.foundation_id == principal.foundation_id)
    query = query.where(Opportunity.state == (state if staff and state else 'published')) if not staff or state else query
    if q:
        query = query.where((Opportunity.title + ' ' + Opportunity.task + ' ' + Opportunity.program).ilike('%' + q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%', escape='\\'))
    if regularity:
        query = query.where(Opportunity.regularity == regularity)
    if format:
        query = query.where(Opportunity.format == format)
    if cursor:
        query = query.where(Opportunity.id > cursor)
    rows = list((await db.scalars(query.order_by(Opportunity.id).limit(limit+1))).all())
    from .matching import own_match_context
    match_context=await own_match_context(db,principal) if not staff else None
    return OpportunityPage(items=[await service.opportunity_view(db, r, staff, match_context) for r in rows[:limit]], next_cursor=rows[limit-1].id if len(rows)>limit else None)


@router.get('/opportunities', response_model=OpportunityPage, operation_id='listPublishedOpportunities')
async def list_public_opportunities(q: str=Query('', max_length=200), regularity: str|None=None, format: str|None=None, cursor: UUID|None=None, limit: int=Query(30, ge=1, le=100), principal: Principal=Depends(get_principal), db: AsyncSession=Depends(get_db)):
    return await opportunity_list(db, principal, False, q, None, regularity, format, cursor, limit)


@router.get('/coord/opportunities', response_model=OpportunityPage, operation_id='listStaffOpportunities')
async def list_staff_opportunities(q: str=Query('', max_length=200), state: str|None=None, regularity: str|None=None, format: str|None=None, cursor: UUID|None=None, limit: int=Query(30, ge=1, le=100), principal: Principal=Depends(opportunities_staff), db: AsyncSession=Depends(get_db)):
    return await opportunity_list(db, principal, True, q, state, regularity, format, cursor, limit)


@router.get('/opportunities/{opportunity_id}', response_model=OpportunityView, operation_id='getPublishedOpportunity')
async def get_public_opportunity(opportunity_id: UUID, principal: Principal=Depends(get_principal), db: AsyncSession=Depends(get_db)):
    from .matching import own_match_context
    return await service.opportunity_view(db, await service.find_opportunity(db, principal, opportunity_id),match_context=await own_match_context(db,principal))


@router.get('/coord/opportunities/{opportunity_id}', response_model=OpportunityView, operation_id='getStaffOpportunity')
async def get_staff_opportunity(opportunity_id: UUID, principal: Principal=Depends(opportunities_staff), db: AsyncSession=Depends(get_db)):
    return await service.opportunity_view(db, await service.find_opportunity(db, principal, opportunity_id, True), True)


@router.post('/coord/opportunities', response_model=OpportunityView, operation_id='createOpportunity')
async def create_opportunity(body: OpportunityCreate, request: Request, key: str=Header(alias='Idempotency-Key'), principal: Principal=Depends(opportunities_staff), db: AsyncSession=Depends(get_db)):
    return await command(db, principal, 'opportunities.create', key, body, lambda: service.create_opportunity(db, principal, body), request)


@router.patch('/coord/opportunities/{opportunity_id}', response_model=OpportunityView, operation_id='updateOpportunity')
async def update_opportunity(opportunity_id: UUID, body: OpportunityUpdate, request: Request, key: str=Header(alias='Idempotency-Key'), principal: Principal=Depends(opportunities_staff), db: AsyncSession=Depends(get_db)):
    return await command(db, principal, f'opportunities.update:{opportunity_id}', key, body, lambda: service.update_opportunity(db, principal, opportunity_id, body), request)


@router.post('/coord/opportunities/{opportunity_id}/publish', response_model=OpportunityView, operation_id='publishOpportunity')
async def publish_opportunity(opportunity_id: UUID, body: VersionCommand, request: Request, key: str=Header(alias='Idempotency-Key'), principal: Principal=Depends(opportunities_staff), db: AsyncSession=Depends(get_db)):
    return await command(db, principal, f'opportunities.publish:{opportunity_id}', key, body, lambda: service.change_opportunity_state(db, principal, opportunity_id, body, 'published'), request)


@router.post('/coord/opportunities/{opportunity_id}/pause', response_model=OpportunityView, operation_id='pauseOpportunity')
async def pause_opportunity(opportunity_id: UUID, body: VersionCommand, request: Request, key: str=Header(alias='Idempotency-Key'), principal: Principal=Depends(opportunities_staff), db: AsyncSession=Depends(get_db)):
    return await command(db, principal, f'opportunities.pause:{opportunity_id}', key, body, lambda: service.change_opportunity_state(db, principal, opportunity_id, body, 'paused'), request)


@router.post('/coord/opportunities/{opportunity_id}/close', response_model=OpportunityView, operation_id='closeOpportunity')
async def close_opportunity(opportunity_id: UUID, body: VersionCommand, request: Request, key: str=Header(alias='Idempotency-Key'), principal: Principal=Depends(opportunities_staff), db: AsyncSession=Depends(get_db)):
    return await command(db, principal, f'opportunities.close:{opportunity_id}', key, body, lambda: service.change_opportunity_state(db, principal, opportunity_id, body, 'closed'), request)



@router.post('/coord/opportunities/{opportunity_id}/reopen', response_model=OpportunityView, operation_id='reopenOpportunity')
async def reopen_opportunity(opportunity_id: UUID, body: VersionCommand, request: Request, key: str=Header(alias='Idempotency-Key'), principal: Principal=Depends(opportunities_staff), db: AsyncSession=Depends(get_db)):
    return await command(db, principal, f'opportunities.reopen:{opportunity_id}', key, body, lambda: service.change_opportunity_state(db, principal, opportunity_id, body, 'draft'), request)

@router.get('/coord/opportunities/{opportunity_id}/history', response_model=list[ActivityRevisionView], operation_id='getOpportunityHistory')
async def opportunity_history(opportunity_id: UUID, principal: Principal=Depends(opportunities_staff), db: AsyncSession=Depends(get_db)):
    await service.find_opportunity(db, principal, opportunity_id, True)
    rows = (await db.scalars(select(OpportunityVersion).where(OpportunityVersion.opportunity_id == opportunity_id).order_by(OpportunityVersion.version.desc()).limit(100))).all()
    return [ActivityRevisionView(version=r.version, snapshot=r.snapshot, created_at=r.created_at) for r in rows]

# One module export; calendar keeps the same API root and shared command boundary.
from .calendar_router import router as calendar_router
router.include_router(calendar_router)

from .assignment_router import router as assignment_router
router.include_router(assignment_router)

from .event_feed_router import router as event_feed_router
router.include_router(event_feed_router)
