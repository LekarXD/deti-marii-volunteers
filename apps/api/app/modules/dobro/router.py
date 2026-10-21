from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal, get_principal, require_permission, authz_guard
from app.core.audit import audit
from app.core.db import get_db
from app.core.idempotency import begin_command, finish_command
from . import service
from . import schemas as dto

router = APIRouter(prefix='/api/v1', tags=['dobro'])

async def command(db, principal, operation, key, body, action, permission=None):
    await authz_guard(db, principal)
    if permission: service.permission(principal, permission)
    payload = body.model_dump(mode='json')
    prior = await begin_command(db, principal, operation, key, payload)
    if prior is not None:
        await db.commit()
        return prior
    result = await action()
    if hasattr(result, 'model_dump'): result = result.model_dump(mode='json')
    audit(db, principal, operation, 'dobro', str(result.get('id', principal.user_id or principal.foundation_id)), payload.keys())
    await finish_command(db, principal, operation, key, result)
    await db.commit()
    return result

@router.get('/fund/integrations/dobro/transfers', response_model=dto.DobroTransferPeriodView)
async def transfers(period: str = Query(pattern=r'^\d{4}-(0[1-9]|1[0-2])$'), principal: Principal = Depends(require_permission('hours.review')), db: AsyncSession = Depends(get_db)):
    return await service.transfer_period(db, principal, period)

@router.post('/fund/integrations/dobro/transfers/mark-entered', response_model=dto.DobroTransferPeriodView)
async def mark_entered(body: dto.DobroMarkCommand, principal: Principal = Depends(require_permission('hours.review')), db: AsyncSession = Depends(get_db), idempotency_key: str | None = Header(default=None)):
    return await command(db, principal, 'dobro.transfers.mark', idempotency_key, body, lambda: service.mark_entered(db, principal, body), 'hours.review')

@router.get('/fund/integrations/dobro/settings', response_model=dto.DobroSettingsView)
async def settings(principal: Principal = Depends(require_permission('integrations.manage')), db: AsyncSession = Depends(get_db)):
    return await service.settings_view(db, principal)

@router.put('/fund/integrations/dobro/settings', response_model=dto.DobroSettingsView)
async def save_settings(body: dto.DobroSettingsCommand, principal: Principal = Depends(require_permission('integrations.manage')), db: AsyncSession = Depends(get_db), idempotency_key: str | None = Header(default=None)):
    return await command(db, principal, 'dobro.settings.save', idempotency_key, body, lambda: service.save_settings(db, principal, body), 'integrations.manage')

@router.get('/fund/opportunities/{opportunity_id}/dobro', response_model=list[dto.DobroActivityView])
async def links(opportunity_id: UUID, principal: Principal = Depends(require_permission('opportunities.manage')), db: AsyncSession = Depends(get_db)):
    return await service.list_links(db, principal, opportunity_id)

@router.post('/fund/opportunities/{opportunity_id}/dobro', response_model=dto.DobroActivityView)
async def create_link(opportunity_id: UUID, body: dto.DobroActivityCommand, principal: Principal = Depends(require_permission('opportunities.manage')), db: AsyncSession = Depends(get_db), idempotency_key: str | None = Header(default=None)):
    return await command(db, principal, f'dobro.activity.create:{opportunity_id}', idempotency_key, body, lambda: service.create_link(db, principal, opportunity_id, body), 'opportunities.manage')

@router.get('/fund/event-series/{series_id}/dobro-opportunity', response_model=dto.DobroSeriesView)
async def event_mapping(series_id: UUID, principal: Principal = Depends(require_permission('opportunities.manage')), db: AsyncSession = Depends(get_db)):
    return await service.series_view(db, principal, series_id)

@router.put('/fund/event-series/{series_id}/dobro-opportunity', response_model=dto.DobroSeriesView)
async def save_event_mapping(series_id: UUID, body: dto.DobroSeriesCommand, principal: Principal = Depends(require_permission('opportunities.manage')), db: AsyncSession = Depends(get_db), idempotency_key: str | None = Header(default=None)):
    return await command(db, principal, f'dobro.series.map:{series_id}', idempotency_key, body, lambda: service.save_series(db, principal, series_id, body), 'opportunities.manage')

@router.get('/fund/events/{occurrence_id}/dobro-team', response_model=dto.DobroTeamView)
async def team(occurrence_id: UUID, principal: Principal = Depends(require_permission('assignments.manage')), db: AsyncSession = Depends(get_db)):
    return await service.team_view(db, principal, occurrence_id)

@router.put('/fund/integrations/dobro/enrollments/{activity_id}/{user_id}', response_model=dto.DobroEnrollmentView)
async def enrollment(activity_id: UUID, user_id: UUID, body: dto.DobroEnrollmentCommand, principal: Principal = Depends(require_permission('hours.review')), db: AsyncSession = Depends(get_db), idempotency_key: str | None = Header(default=None)):
    return await command(db, principal, f'dobro.enrollment:{activity_id}:{user_id}', idempotency_key, body, lambda: service.change_enrollment(db, principal, activity_id, user_id, body), 'hours.review')

@router.put('/fund/volunteers/{user_id}/external-profiles/dobro', response_model=dto.DobroProfileView)
async def staff_profile(user_id: UUID, body: dto.DobroProfileCommand, principal: Principal = Depends(require_permission('hours.review')), db: AsyncSession = Depends(get_db), idempotency_key: str | None = Header(default=None)):
    return await command(db, principal, f'dobro.profile:{user_id}', idempotency_key, body, lambda: service.save_profile(db, principal, user_id, body), 'hours.review')

@router.get('/fund/volunteers/{user_id}/external-profiles/dobro', response_model=dto.DobroProfileView)
async def staff_profile_read(user_id: UUID, principal: Principal = Depends(require_permission('hours.review')), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from .models import DobroProfile
    await service.user(db, principal, user_id)
    row = await db.scalar(select(DobroProfile).where(DobroProfile.user_id == user_id, DobroProfile.foundation_id == principal.foundation_id))
    return dto.DobroProfileView(profile_url=row.profile_url if row else '', version=row.version if row else 0)

@router.get('/me/dobro', response_model=dto.DobroOwnView)
async def own(principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return await service.own_view(db, principal)

@router.put('/me/external-profiles/dobro', response_model=dto.DobroProfileView)
async def own_profile(body: dto.DobroProfileCommand, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), idempotency_key: str | None = Header(default=None)):
    async def action():
        await service.user(db, principal)
        return await service.save_profile(db, principal, principal.user_id, body)
    return await command(db, principal, 'dobro.profile.own', idempotency_key, body, action)

@router.post('/me/dobro-enrollments/{activity_id}', response_model=dto.DobroEnrollmentView)
async def own_enrollment(activity_id: UUID, body: dto.DobroEnrollmentCommand, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), idempotency_key: str | None = Header(default=None)):
    async def action():
        await service.user(db, principal)
        return await service.change_enrollment(db, principal, activity_id, principal.user_id, body, own=True)
    return await command(db, principal, f'dobro.enrollment.own:{activity_id}', idempotency_key, body, action)
