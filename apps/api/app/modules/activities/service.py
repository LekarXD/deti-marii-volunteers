from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import ApiError
from .models import Opportunity, OpportunityRoleLink, OpportunityVersion, VolunteerRole, VolunteerRoleVersion
from .schemas import MatchExplanation, OpportunityCreate, OpportunityView, RoleCreate, RoleView, normalized_title


def role_view(role: VolunteerRole, staff=True, volunteer_count=0):
    return RoleView(id=role.id, title=role.title, task=role.task,
        preparation_defaults=role.preparation_defaults, approval_policy=role.approval_policy,
        direction=role.direction or '', skills=role.skills or [],
        archived_at=role.archived_at, version=role.version, volunteer_count=volunteer_count,
        allowed_actions=['update', 'restore' if role.archived_at else 'archive', 'history', 'usage'] if staff else [])


def explain_match(opportunity: Opportunity) -> MatchExplanation:
    # Staff snapshots describe conditions without embedding a volunteer profile.
    constraints = [r['title'] for r in opportunity.preparation_requirements if r['level'] == 'mandatory']
    return MatchExplanation(reasons=[], missing_data=['interests', 'availability', 'preparation'], constraints=constraints)


async def opportunity_view(db, opportunity, staff=False, match_context=None):
    role_ids = list((await db.scalars(select(OpportunityRoleLink.role_id).where(OpportunityRoleLink.opportunity_id == opportunity.id).order_by(OpportunityRoleLink.role_id))).all())
    fields = {name: getattr(opportunity, name) for name in OpportunityCreate.model_fields if name != 'role_ids'}
    matching=explain_match(opportunity)
    if not staff:
        from .matching import explain_opportunity
        matching=await explain_opportunity(db,opportunity,match_context)
    return OpportunityView(**fields, role_ids=role_ids, id=opportunity.id, version=opportunity.version,
        state=opportunity.state, matching=matching,
        allowed_actions=(['update', 'history'] + {'draft':['publish'], 'published':['pause','close'], 'paused':['publish','close'], 'closed':['reopen']}[opportunity.state]) if staff else [])


async def role_volunteer_counts(db: AsyncSession, principal: Principal, role_ids: list[UUID]) -> dict[UUID, int]:
    """How many distinct volunteers have confirmed a shift in each role, past or upcoming."""
    if not role_ids:
        return {}
    from .assignment_models import Assignment
    from .calendar_models import StaffingNeed
    rows = await db.execute(select(StaffingNeed.role_id, func.count(func.distinct(Assignment.user_id)))
        .join(Assignment, Assignment.staffing_need_id == StaffingNeed.id)
        .where(StaffingNeed.foundation_id == principal.foundation_id, Assignment.foundation_id == principal.foundation_id,
               StaffingNeed.role_id.in_(role_ids), Assignment.status == 'confirmed')
        .group_by(StaffingNeed.role_id))
    return {role_id: count for role_id, count in rows.all()}


async def find_role(db: AsyncSession, principal: Principal, role_id: UUID, lock=False):
    query = select(VolunteerRole).where(VolunteerRole.id == role_id, VolunteerRole.foundation_id == principal.foundation_id)
    role = await db.scalar(query.with_for_update() if lock else query)
    if role is None:
        raise ApiError(404, 'role_not_found', 'Роль не найдена.')
    return role


async def find_opportunity(db, principal, opportunity_id, staff=False, lock=False):
    query = select(Opportunity).where(Opportunity.id == opportunity_id, Opportunity.foundation_id == principal.foundation_id)
    if not staff:
        query = query.where(Opportunity.state == 'published')
    opportunity = await db.scalar(query.with_for_update() if lock else query)
    if opportunity is None:
        raise ApiError(404, 'opportunity_not_found', 'Возможность не найдена.')
    return opportunity


def check_version(entity, expected):
    if entity.version != expected:
        raise ApiError(409, 'version_conflict', 'Данные изменились. Обновите страницу.', current_version=entity.version)


async def role_history(db, role, principal):
    await db.flush()
    db.add(VolunteerRoleVersion(role_id=role.id, version=role.version,
        snapshot=role_view(role).model_dump(mode='json'), actor_id=principal.actor_id))
    await db.flush()


async def opportunity_history(db, opportunity, principal):
    await db.flush()
    snapshot = (await opportunity_view(db, opportunity, True)).model_dump(mode='json')
    db.add(OpportunityVersion(opportunity_id=opportunity.id, version=opportunity.version,
        snapshot=snapshot, actor_id=principal.actor_id))


async def create_role(db, principal, body: RoleCreate):
    fields = body.model_dump(mode='json')
    role = VolunteerRole(**fields, normalized_title=normalized_title(body.title), foundation_id=principal.foundation_id, updated_by=principal.actor_id)
    db.add(role)
    await role_history(db, role, principal)
    return role_view(role)


async def update_role(db, principal, role_id, body):
    role = await find_role(db, principal, role_id, True)
    check_version(role, body.expected_version)
    for name, value in body.model_dump(mode='json', exclude={'expected_version'}).items():
        setattr(role, name, value)
    role.normalized_title = normalized_title(body.title)
    role.version += 1
    role.updated_at = datetime.now(timezone.utc)
    role.updated_by = principal.actor_id
    await role_history(db, role, principal)
    return role_view(role)


async def archive_role(db, principal, role_id, body, archive):
    role = await find_role(db, principal, role_id, True)
    check_version(role, body.expected_version)
    if bool(role.archived_at) == archive:
        raise ApiError(409, 'role_state_conflict', 'Состояние роли уже изменилось.', current_version=role.version)
    role.archived_at = datetime.now(timezone.utc) if archive else None
    role.updated_at = datetime.now(timezone.utc)
    role.updated_by = principal.actor_id
    role.version += 1
    await role_history(db, role, principal)
    return role_view(role)


async def role_snapshots(db, principal, role_ids):
    # Lock roles in UUID order so archive cannot race creation of new links.
    roles = list((await db.scalars(select(VolunteerRole).where(VolunteerRole.id.in_(role_ids),
        VolunteerRole.foundation_id == principal.foundation_id, VolunteerRole.archived_at.is_(None))
        .order_by(VolunteerRole.id).with_for_update())).all())
    if len(roles) != len(role_ids):
        raise ApiError(422, 'invalid_roles', 'Выберите действующие роли своего фонда.', field_errors={'role_ids': 'Роль недоступна.'})
    return roles


async def set_links(db, opportunity, roles):
    await db.execute(delete(OpportunityRoleLink).where(OpportunityRoleLink.opportunity_id == opportunity.id))
    for role in roles:
        revision = await db.scalar(select(VolunteerRoleVersion).where(VolunteerRoleVersion.role_id == role.id, VolunteerRoleVersion.version == role.version))
        if revision is None:
            raise ApiError(409, 'role_revision_missing', 'Версия роли недоступна. Обновите справочник.')
        db.add(OpportunityRoleLink(opportunity_id=opportunity.id, foundation_id=opportunity.foundation_id, role_id=role.id, role_version_id=revision.id))
    await db.flush()


async def create_opportunity(db, principal, body):
    roles = await role_snapshots(db, principal, body.role_ids)
    fields = body.model_dump(mode='json', exclude={'role_ids'})
    if fields['task'] is None:
        fields['task'] = '\n\n'.join(role.task for role in roles if role.task)
    if fields['preparation_requirements'] is None:
        fields['preparation_requirements'] = list({r['key']: r for role in roles for r in role.preparation_defaults}.values())
    if fields['approval_policy'] is None:
        fields['approval_policy'] = 'coordinator' if any(r.approval_policy == 'coordinator' for r in roles) else 'self_confirmation'
    opportunity = Opportunity(**fields, foundation_id=principal.foundation_id, updated_by=principal.actor_id)
    db.add(opportunity)
    await db.flush()
    await set_links(db, opportunity, roles)
    await opportunity_history(db, opportunity, principal)
    return await opportunity_view(db, opportunity, True)


async def update_opportunity(db, principal, opportunity_id, body):
    opportunity = await find_opportunity(db, principal, opportunity_id, True, True)
    check_version(opportunity, body.expected_version)
    current_links = set((await db.scalars(select(OpportunityRoleLink.role_id).where(OpportunityRoleLink.opportunity_id == opportunity.id))).all())
    if set(body.role_ids) != current_links:
        roles = await role_snapshots(db, principal, body.role_ids)
        await set_links(db, opportunity, roles)
    fields = body.model_dump(mode='json', exclude={'expected_version', 'role_ids'}, exclude_none=True)
    for name, value in fields.items():
        setattr(opportunity, name, value)
    opportunity.version += 1
    opportunity.updated_at = datetime.now(timezone.utc)
    opportunity.updated_by = principal.actor_id
    await opportunity_history(db, opportunity, principal)
    return await opportunity_view(db, opportunity, True)


async def change_opportunity_state(db, principal, opportunity_id, body, state):
    opportunity = await find_opportunity(db, principal, opportunity_id, True, True)
    check_version(opportunity, body.expected_version)
    if state not in {'draft':{'published'}, 'published':{'paused','closed'}, 'paused':{'published','closed'}, 'closed':{'draft'}}[opportunity.state]:
        raise ApiError(409, 'opportunity_state_conflict', 'Состояние уже изменилось.', current_version=opportunity.version)
    if state == 'published' and not all([opportunity.title, opportunity.program, opportunity.task, opportunity.audience, opportunity.location, opportunity.schedule]):
        raise ApiError(422, 'publication_incomplete', 'Укажите программу, аудиторию, задачи, место и расписание.')
    opportunity.state = state
    opportunity.version += 1
    opportunity.updated_at = datetime.now(timezone.utc)
    opportunity.updated_by = principal.actor_id
    await opportunity_history(db, opportunity, principal)
    return await opportunity_view(db, opportunity, True)


AWAITING_RESPONSE = ('submitted', 'under_review', 'preparation_requested')


async def event_responses(db, principal):
    """Counts for the events list: own sign-ups and reserve places for upcoming dates still waiting for approval, and open responses."""
    from app.core.clock import utcnow
    from .assignment_models import Assignment, OpportunityResponse
    from .calendar_models import EventOccurrence
    from .schemas import EventResponsesSummary
    sign_ups = (await db.execute(select(Assignment.occurrence_id, Assignment.staffing_need_id, func.count()).join(EventOccurrence, EventOccurrence.id == Assignment.occurrence_id).where(
        Assignment.foundation_id == principal.foundation_id, Assignment.origin.in_(('self', 'reserve')), Assignment.status == 'invited', Assignment.approved_at.is_(None),
        EventOccurrence.foundation_id == principal.foundation_id, EventOccurrence.status == 'scheduled', EventOccurrence.starts_at > utcnow()).group_by(Assignment.occurrence_id, Assignment.staffing_need_id))).all()
    responses = (await db.execute(select(OpportunityResponse.opportunity_id, func.count()).where(OpportunityResponse.foundation_id == principal.foundation_id,
        OpportunityResponse.state.in_(AWAITING_RESPONSE)).group_by(OpportunityResponse.opportunity_id))).all()
    return EventResponsesSummary(sign_ups=[{'occurrence_id': o, 'staffing_need_id': n, 'count': c} for o, n, c in sign_ups], responses=[{'opportunity_id': o, 'count': c} for o, c in responses])


async def reserve_views(db, principal, occurrence_id=None, row_ids=None):
    from app.core.models import User
    from .assignment_models import StaffingNeedReserve
    from .calendar_models import StaffingNeed
    from .schemas import StaffReserveView
    query = select(StaffingNeedReserve, User.display_name, VolunteerRoleVersion.snapshot).join(User, User.id == StaffingNeedReserve.user_id).join(StaffingNeed, StaffingNeed.id == StaffingNeedReserve.staffing_need_id).join(
        VolunteerRoleVersion, VolunteerRoleVersion.id == StaffingNeed.role_version_id).where(StaffingNeedReserve.foundation_id == principal.foundation_id, StaffingNeedReserve.state != 'closed')
    query = query.where(StaffingNeedReserve.occurrence_id == occurrence_id) if row_ids is None else query.where(StaffingNeedReserve.id.in_(row_ids))
    rows = (await db.execute(query.order_by(StaffingNeedReserve.queued_at, StaffingNeedReserve.id))).all()
    result = []
    for row, name, snapshot in rows:
        position = None
        if row.state == 'waiting':
            position = 1 + await db.scalar(select(func.count()).select_from(StaffingNeedReserve).where(StaffingNeedReserve.staffing_need_id == row.staffing_need_id, StaffingNeedReserve.state == 'waiting',
                (StaffingNeedReserve.queued_at < row.queued_at) | ((StaffingNeedReserve.queued_at == row.queued_at) & (StaffingNeedReserve.id < row.id))))
        result.append(StaffReserveView(id=row.id, version=row.version, user_id=row.user_id, display_name=name, occurrence_id=row.occurrence_id, staffing_need_id=row.staffing_need_id,
            role_title=snapshot['title'], state=row.state, position=position))
    return result


async def reserve_volunteer(db, principal, need_id, body):
    """The coordinator answers «мест нет»: the volunteer waits in the reserve queue, a pending own sign-up is withdrawn."""
    from app.core.clock import utcnow
    from app.core.models import ResourceReservation, User
    from app.modules.profile.service import active_for_invitations
    from .assignment_models import Assignment, StaffingNeedReserve
    from . import assignment_service as participation
    event, need = await participation.open_need(db, principal, need_id, body.expected_version)
    user = await db.get(User, body.user_id)
    if user is None or user.foundation_id != principal.foundation_id or user.account_state != 'active':
        raise ApiError(422, 'invalid_volunteer', 'Волонтёр недоступен.')
    if not await active_for_invitations(db, principal.foundation_id, user.id):
        raise ApiError(409, 'volunteer_paused', 'Волонтёр сейчас на паузе.')
    item = await db.scalar(select(Assignment).where(Assignment.occurrence_id == event.id, Assignment.user_id == user.id).with_for_update())
    if item is not None and item.status in ('invited', 'confirmed'):
        if item.status == 'confirmed' or item.origin != 'self' or item.approved_at is not None:
            raise ApiError(409, 'already_in_team', 'Волонтёр уже в составе или приглашён.', current_version=item.version)
        if body.expected_assignment_version is not None:
            check_version(item, body.expected_assignment_version)
    row = await db.scalar(select(StaffingNeedReserve).where(StaffingNeedReserve.staffing_need_id == need.id, StaffingNeedReserve.user_id == user.id).with_for_update())
    if row is not None and row.state != 'closed':
        raise ApiError(409, 'already_in_reserve', 'Волонтёр уже в резерве на эту роль.', current_version=row.version)
    reason = body.reason.strip() or 'Мест на эту дату нет. Вы в резерве: позовём, если кто-то отменит.'
    if item is not None and item.status == 'invited':
        item.status = 'cancelled'; item.version += 1; item.updated_at = utcnow()
        await db.execute(update(ResourceReservation).where(ResourceReservation.source_type == 'activity', ResourceReservation.source_id == item.id).values(active=False))
        await participation.assignment_event(db, principal, item, 'to_reserve', reason)
    if row is None:
        row = StaffingNeedReserve(foundation_id=principal.foundation_id, occurrence_id=event.id, staffing_need_id=need.id, user_id=user.id, state='waiting'); db.add(row)
    else:
        row.state = 'waiting'; row.version += 1; row.queued_at = utcnow(); row.updated_at = utcnow(); row.offered_assignment_id = None
    await db.flush()
    return (await reserve_views(db, principal, row_ids=[row.id]))[0]
