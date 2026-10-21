from datetime import date
from uuid import UUID
from zoneinfo import ZoneInfo
from app.core.clock import utcnow

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import ApiError
from .models import GroupMembership, Participant, ParticipantBriefing, ParticipantGroup
from .schemas import SafeParticipant


def foundation_permission(principal: Principal, permission: str) -> bool:
    return principal.is_staff and principal.has_permission(permission)


def group_scope(principal: Principal, permission: str):
    """Current principal grants are rebuilt by auth on every request."""
    if not principal.is_staff:
        return ParticipantGroup.id.in_([])
    if foundation_permission(principal, permission):
        return ParticipantGroup.foundation_id == principal.foundation_id
    group_ids = [scope_id for name, scope_type, scope_id in principal.grants
                 if name == permission and scope_type == "group" and scope_id is not None]
    return and_(ParticipantGroup.foundation_id == principal.foundation_id,
                or_(ParticipantGroup.id.in_(group_ids), ParticipantGroup.leader_id == principal.user_id, ParticipantGroup.coordinator_id == principal.user_id))


def participant_scope(principal: Principal, permission: str):
    if foundation_permission(principal, permission):
        return Participant.foundation_id == principal.foundation_id
    # Historical memberships do not keep a leader's current read privilege alive.
    today = utcnow().astimezone(ZoneInfo("Europe/Moscow")).date()
    allowed_membership = exists(select(GroupMembership.id).join(
        ParticipantGroup, ParticipantGroup.id == GroupMembership.group_id).where(
            GroupMembership.participant_id == Participant.id,
            GroupMembership.foundation_id == principal.foundation_id,
            GroupMembership.valid_from <= today,
            or_(GroupMembership.valid_until.is_(None), GroupMembership.valid_until > today),
            or_(group_scope(principal, permission), group_scope(principal, permission.replace("participants.", "groups.")))))
    return and_(Participant.foundation_id == principal.foundation_id, allowed_membership)


async def get_participant(db: AsyncSession, principal: Principal, participant_id: UUID, permission="participants.read", lock=False):
    query = select(Participant).where(Participant.id == participant_id, participant_scope(principal, permission))
    if lock:
        query = query.with_for_update()
    item = await db.scalar(query)
    if item is None:
        raise ApiError(404, "participant_not_found", "Участник не найден или недоступен.")
    return item


async def get_group(db: AsyncSession, principal: Principal, group_id: UUID, permission="groups.read", lock=False):
    query = select(ParticipantGroup).where(ParticipantGroup.id == group_id, group_scope(principal, permission))
    if lock:
        query = query.with_for_update()
    item = await db.scalar(query)
    if item is None:
        raise ApiError(404, "group_not_found", "Группа не найдена или недоступна.")
    return item


def check_version(item, expected):
    if item.version != expected:
        raise ApiError(409, "version_conflict", "Карточка уже изменена. Обновите страницу.", current_version=item.version)


async def safe_participant(db: AsyncSession, participant: Participant) -> SafeParticipant:
    briefing = await db.get(ParticipantBriefing, participant.id)
    return SafeParticipant(id=participant.id, display_name=participant.display_name,
        birth_year=participant.birth_year, about=participant.about,
        communication=briefing.communication if briefing else "",
        support=briefing.support if briefing else "", interests=briefing.interests if briefing else "",
        photo_asset_id=participant.photo_asset_id, version=participant.version, lifecycle=participant.lifecycle)


async def add_membership(db: AsyncSession, principal: Principal, group_id: UUID, data):
    # All membership writes lock the group first: concurrent overlapping inserts serialize.
    group = await get_group(db, principal, group_id, "groups.write", lock=True)
    check_version(group, data.expected_version)
    if group.lifecycle != "active":
        raise ApiError(409, "group_archived", "Нельзя менять состав архивной группы.")
    participant = await get_participant(db, principal, data.participant_id, "participants.read")
    if participant.lifecycle != "active":
        raise ApiError(409, "participant_archived", "Участник находится в архиве.")
    overlap = select(GroupMembership.id).where(
        GroupMembership.foundation_id == principal.foundation_id,
        GroupMembership.group_id == group.id,
        GroupMembership.participant_id == participant.id,
        or_(GroupMembership.valid_until.is_(None), GroupMembership.valid_until > data.valid_from))
    if data.valid_until is not None:
        overlap = overlap.where(GroupMembership.valid_from < data.valid_until)
    if await db.scalar(overlap):
        raise ApiError(409, "membership_overlap", "Участник уже состоит в группе в этот период.")
    item = GroupMembership(foundation_id=principal.foundation_id, group_id=group.id,
        participant_id=participant.id, valid_from=data.valid_from, valid_until=data.valid_until)
    db.add(item)
    group.version += 1
    await db.flush()
    return item, group
