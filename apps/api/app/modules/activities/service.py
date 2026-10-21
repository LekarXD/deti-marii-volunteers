from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import ApiError
from .models import Opportunity, OpportunityRoleLink, OpportunityVersion, VolunteerRole, VolunteerRoleVersion
from .schemas import MatchExplanation, OpportunityCreate, OpportunityView, RoleCreate, RoleView, normalized_title


def role_view(role: VolunteerRole, staff=True):
    return RoleView(id=role.id, title=role.title, task=role.task,
        preparation_defaults=role.preparation_defaults, approval_policy=role.approval_policy,
        archived_at=role.archived_at, version=role.version,
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
