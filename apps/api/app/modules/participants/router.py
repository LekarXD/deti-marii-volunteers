from datetime import date
from uuid import UUID
from zoneinfo import ZoneInfo
from app.core.clock import utcnow

from fastapi import APIRouter, Depends, Header, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import audit
from app.core.auth import Principal, authz_guard, get_principal
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.idempotency import begin_command, finish_command
from app.core.models import MediaAsset, StaffMembership, User
from .access import AssignmentAccess, get_assignment_access
from .models import GroupMembership, Participant, ParticipantBriefing, ParticipantGroup, ParticipantPrivateNote
from .schemas import AssignmentGroupBriefing, ParticipantStaffOptions, AssignmentParticipantList, GroupDetail, GroupList, MembershipResult, ParticipantList, PrivateNoteList, PrivateNoteView, SafeParticipant, GroupInput, GroupUpdate, GroupView, MembershipEnd, MembershipInput, ParticipantInput, ParticipantUpdate, PrivateNoteInput
from .service import add_membership, check_version, foundation_permission, get_group, get_participant, group_scope, participant_scope, safe_participant

router = APIRouter(prefix="/api/v1", tags=["participants"])


def denied():
    raise ApiError(403, "permission_denied", "Недостаточно прав для этого действия.")


async def validate_leader(db, principal, leader_id):
    if leader_id is None:
        return
    active = await db.scalar(select(User.id).join(StaffMembership, StaffMembership.user_id == User.id).where(
        User.id == leader_id, User.foundation_id == principal.foundation_id, User.account_state == "active",
        StaffMembership.foundation_id == principal.foundation_id, StaffMembership.revoked_at.is_(None)))
    if not active:
        raise ApiError(422, "leader_not_staff", "Ведущий должен быть действующим сотрудником фонда.")


async def validate_photo(db, principal, asset_id):
    if asset_id is None:
        return
    from app.modules.assets.service import require_asset
    asset = await require_asset(db, principal, asset_id, ready=True)
    asset.access_permission = "participants.read"
    if asset.content_type not in ("image/png", "image/jpeg", "image/webp") or asset.expected_size > 5 * 1024 * 1024:
        raise ApiError(422, "invalid_participant_photo", "Выберите PNG, JPEG или WebP до 5 МБ.")


async def complete(db, principal, operation, key, result, entity_type, entity_id, fields):
    audit(db, principal, operation, entity_type, entity_id, fields=fields)
    await finish_command(db, principal, operation, key, result)
    await db.commit()
    return result


def membership_view(item):
    return {"id": str(item.id), "participant_id": str(item.participant_id), "valid_from": item.valid_from.isoformat(),
            "valid_until": item.valid_until.isoformat() if item.valid_until else None}


@router.get("/coord/participants", response_model=ParticipantList)
async def list_participants(query: str = Query(default="", max_length=200), archived: bool = False,
                            limit: int = Query(default=100, ge=1, le=200), offset: int = Query(default=0, ge=0),
                            db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal)):
    if not principal.is_staff:
        denied()
    stmt = select(Participant).where(participant_scope(principal, "participants.read"),
        Participant.lifecycle == ("archived" if archived else "active"))
    if query.strip():
        # Search only the display name; notes and briefings never enter a search projection.
        stmt = stmt.where(Participant.display_name.icontains(query.strip(), autoescape=True))
    rows = (await db.scalars(stmt.order_by(Participant.display_name, Participant.id).limit(limit).offset(offset))).all()
    return {"items": [(await safe_participant(db, row)).model_dump(mode="json") for row in rows], "limit": limit, "offset": offset}


@router.get("/coord/participants/{participant_id}", response_model=SafeParticipant)
async def read_participant(participant_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal)):
    return await safe_participant(db, await get_participant(db, principal, participant_id))


@router.post("/coord/participants", response_model=SafeParticipant)
async def create_participant(data: ParticipantInput, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal), key: str | None = Header(default=None, alias="Idempotency-Key")):
    await authz_guard(db, principal)
    if not foundation_permission(principal, "participants.write"):
        denied()
    operation = "participants.create"
    if cached := await begin_command(db, principal, operation, key, data.model_dump(mode="json")):
        return cached
    await validate_photo(db, principal, data.photo_asset_id)
    values = data.model_dump(exclude={"communication", "support", "interests"})
    item = Participant(foundation_id=principal.foundation_id, **values)
    db.add(item)
    await db.flush()
    db.add(ParticipantBriefing(participant_id=item.id, communication=data.communication, support=data.support, interests=data.interests))
    await db.flush()
    result = (await safe_participant(db, item)).model_dump(mode="json")
    return await complete(db, principal, operation, key, result, "participant", item.id, list(values))


@router.patch("/coord/participants/{participant_id}", response_model=SafeParticipant)
async def update_participant(participant_id: UUID, data: ParticipantUpdate, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal), key: str | None = Header(default=None, alias="Idempotency-Key")):
    await authz_guard(db, principal)
    item = await get_participant(db, principal, participant_id, "participants.write", lock=True)
    operation = f"participants.update:{participant_id}"
    if cached := await begin_command(db, principal, operation, key, data.model_dump(mode="json")):
        return cached
    check_version(item, data.expected_version)
    if data.photo_asset_id != item.photo_asset_id:
        await validate_photo(db, principal, data.photo_asset_id)
    values = data.model_dump(exclude={"communication", "support", "interests", "expected_version"})
    for field, value in values.items():
        setattr(item, field, value)
    briefing = await db.get(ParticipantBriefing, item.id)
    if briefing is None:
        briefing = ParticipantBriefing(participant_id=item.id)
        db.add(briefing)
    for field in ("communication", "support", "interests"):
        setattr(briefing, field, getattr(data, field))
    briefing.version = item.version + 1
    item.version += 1
    await db.flush()
    return await complete(db, principal, operation, key, (await safe_participant(db, item)).model_dump(mode="json"), "participant", item.id, list(values) + ["briefing"])


async def private_permission(db, principal, item):
    if foundation_permission(principal, "participants.private_notes"):
        return
    today = utcnow().astimezone(ZoneInfo("Europe/Moscow")).date()
    groups = (await db.scalars(select(GroupMembership.group_id).where(GroupMembership.participant_id == item.id,
        GroupMembership.foundation_id == principal.foundation_id, GroupMembership.valid_from <= today,
        or_(GroupMembership.valid_until.is_(None), GroupMembership.valid_until > today)))).all()
    if not any(principal.has_permission("participants.private_notes", "group", group_id) for group_id in groups):
        denied()


@router.get("/coord/participants/{participant_id}/private-notes", response_model=PrivateNoteList)
async def private_notes(participant_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal)):
    item = await get_participant(db, principal, participant_id)
    await private_permission(db, principal, item)
    rows = (await db.scalars(select(ParticipantPrivateNote).where(ParticipantPrivateNote.participant_id == item.id,
        ParticipantPrivateNote.foundation_id == principal.foundation_id).order_by(ParticipantPrivateNote.created_at.desc(), ParticipantPrivateNote.id.desc()))).all()
    return {"items": [{"id": str(row.id), "text": row.text, "author_id": str(row.author_id), "created_at": row.created_at.isoformat()} for row in rows]}


@router.post("/coord/participants/{participant_id}/private-notes", response_model=PrivateNoteView)
async def add_private_note(participant_id: UUID, data: PrivateNoteInput, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal), key: str | None = Header(default=None, alias="Idempotency-Key")):
    await authz_guard(db, principal)
    item = await get_participant(db, principal, participant_id)
    await private_permission(db, principal, item)
    operation = f"participants.private_note:{participant_id}"
    if cached := await begin_command(db, principal, operation, key, data.model_dump(mode="json")):
        return cached
    note = ParticipantPrivateNote(foundation_id=principal.foundation_id, participant_id=item.id, author_id=principal.user_id, text=data.text)
    db.add(note)
    await db.flush()
    return await complete(db, principal, operation, key, {"id": str(note.id), "text": note.text, "author_id": str(note.author_id), "created_at": note.created_at.isoformat()}, "participant", item.id, ["private_note"])


@router.get("/coord/groups/staff-options", response_model=ParticipantStaffOptions)
async def staff_options(db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal)):
    if not principal.is_staff or not (foundation_permission(principal, "groups.write") or await db.scalar(select(ParticipantGroup.id).where(group_scope(principal, "groups.write")).limit(1))):
        denied()
    rows = (await db.scalars(select(User).join(StaffMembership, StaffMembership.user_id == User.id).where(
        User.foundation_id == principal.foundation_id, User.account_state == "active",
        StaffMembership.foundation_id == principal.foundation_id, StaffMembership.revoked_at.is_(None)).order_by(User.display_name, User.id).limit(200))).all()
    return {"items": [{"id": row.id, "display_name": row.display_name} for row in rows]}


@router.get("/coord/groups", response_model=GroupList)
async def list_groups(archived: bool = False, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal)):
    if not principal.is_staff:
        denied()
    rows = (await db.scalars(select(ParticipantGroup).where(group_scope(principal, "groups.read"),
        ParticipantGroup.lifecycle == ("archived" if archived else "active")).order_by(ParticipantGroup.title, ParticipantGroup.id).limit(200))).all()
    return {"items": [GroupView.model_validate(row).model_dump(mode="json") for row in rows]}


@router.post("/coord/groups", response_model=GroupView)
async def create_group(data: GroupInput, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal), key: str | None = Header(default=None, alias="Idempotency-Key")):
    await authz_guard(db, principal)
    if not foundation_permission(principal, "groups.write"):
        denied()
    operation = "groups.create"
    if cached := await begin_command(db, principal, operation, key, data.model_dump(mode="json")):
        return cached
    await validate_leader(db, principal, data.leader_id)
    await validate_leader(db, principal, data.coordinator_id)
    item = ParticipantGroup(foundation_id=principal.foundation_id, **data.model_dump())
    db.add(item)
    await db.flush()
    return await complete(db, principal, operation, key, GroupView.model_validate(item).model_dump(mode="json"), "group", item.id, list(data.model_fields_set))


@router.get("/coord/groups/{group_id}", response_model=GroupDetail)
async def read_group(group_id: UUID, at: date | None = None, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal)):
    group = await get_group(db, principal, group_id)
    effective = at or utcnow().astimezone(ZoneInfo("Europe/Moscow")).date()
    rows = (await db.scalars(select(GroupMembership).where(GroupMembership.group_id == group.id,
        GroupMembership.foundation_id == principal.foundation_id, GroupMembership.valid_from <= effective,
        or_(GroupMembership.valid_until.is_(None), GroupMembership.valid_until > effective)).order_by(GroupMembership.valid_from, GroupMembership.id))).all()
    members = []
    for row in rows:
        person = await db.get(Participant, row.participant_id)
        members.append({**membership_view(row), "participant": (await safe_participant(db, person)).model_dump(mode="json")})
    return {**GroupView.model_validate(group).model_dump(mode="json"), "at": effective.isoformat(), "members": members}


@router.patch("/coord/groups/{group_id}", response_model=GroupView)
async def update_group(group_id: UUID, data: GroupUpdate, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal), key: str | None = Header(default=None, alias="Idempotency-Key")):
    await authz_guard(db, principal)
    item = await get_group(db, principal, group_id, "groups.write", lock=True)
    operation = f"groups.update:{group_id}"
    if cached := await begin_command(db, principal, operation, key, data.model_dump(mode="json")):
        return cached
    check_version(item, data.expected_version)
    # A scoped leader cannot appoint a new leader or broaden their own authority.
    if (data.leader_id != item.leader_id or data.coordinator_id != item.coordinator_id) and not foundation_permission(principal, "groups.write"):
        denied()
    await validate_leader(db, principal, data.leader_id)
    await validate_leader(db, principal, data.coordinator_id)
    for field, value in data.model_dump(exclude={"expected_version"}).items():
        setattr(item, field, value)
    item.version += 1
    await db.flush()
    return await complete(db, principal, operation, key, GroupView.model_validate(item).model_dump(mode="json"), "group", item.id, list(data.model_fields_set))


@router.post("/coord/groups/{group_id}/memberships", response_model=MembershipResult)
async def create_membership(group_id: UUID, data: MembershipInput, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal), key: str | None = Header(default=None, alias="Idempotency-Key")):
    await authz_guard(db, principal)
    await get_group(db, principal, group_id, "groups.write")
    operation = f"groups.membership.add:{group_id}"
    if cached := await begin_command(db, principal, operation, key, data.model_dump(mode="json")):
        return cached
    item, group = await add_membership(db, principal, group_id, data)
    return await complete(db, principal, operation, key, {**membership_view(item), "group_version": group.version}, "group", group.id, ["membership"])


@router.patch("/coord/groups/{group_id}/memberships/{membership_id}", response_model=MembershipResult)
async def end_membership(group_id: UUID, membership_id: UUID, data: MembershipEnd, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal), key: str | None = Header(default=None, alias="Idempotency-Key")):
    await authz_guard(db, principal)
    group = await get_group(db, principal, group_id, "groups.write", lock=True)
    operation = f"groups.membership.end:{membership_id}"
    if cached := await begin_command(db, principal, operation, key, data.model_dump(mode="json")):
        return cached
    check_version(group, data.expected_version)
    item = await db.scalar(select(GroupMembership).where(GroupMembership.id == membership_id, GroupMembership.group_id == group.id, GroupMembership.foundation_id == principal.foundation_id))
    if item is None:
        raise ApiError(404, "membership_not_found", "Участие в группе не найдено.")
    if data.valid_until <= item.valid_from or (item.valid_until and data.valid_until > item.valid_until):
        raise ApiError(422, "invalid_membership_end", "Можно только сократить период участия после даты начала.")
    item.valid_until = data.valid_until
    group.version += 1
    await db.flush()
    return await complete(db, principal, operation, key, {**membership_view(item), "group_version": group.version}, "group", group.id, ["membership"])


async def photo_response(db, participant):
    from app.modules.assets.service import asset_content
    asset = await db.get(MediaAsset, participant.photo_asset_id) if participant.photo_asset_id else None
    if asset is None or asset.foundation_id != participant.foundation_id or asset.state != "ready":
        raise ApiError(404, "photo_not_found", "Фотография недоступна.")
    return await asset_content(db, asset)


@router.get("/coord/participants/{participant_id}/photo")
async def staff_photo(participant_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal)):
    return await photo_response(db, await get_participant(db, principal, participant_id))


async def assignment_projection(db, principal, assignment_id, access):
    # Authorization is evaluated from current P09 state on every request. Never infer
    # membership from the caller's staff flag, uploaded-file ownership or group today.
    grant = await access.participants(db, principal, assignment_id)
    if grant.assignment_id != assignment_id:
        denied()
    people = (await db.scalars(select(Participant).where(
        Participant.id.in_(grant.participant_ids), Participant.foundation_id == principal.foundation_id
    ).order_by(Participant.display_name, Participant.id))).all()
    return grant, [(await safe_participant(db, item)).model_dump(mode="json") for item in people]


@router.get("/me/assignments/{assignment_id}/participants", response_model=AssignmentParticipantList)
async def assignment_participants(assignment_id: UUID, response: Response, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal), access: AssignmentAccess = Depends(get_assignment_access)):
    _, people = await assignment_projection(db, principal, assignment_id, access)
    response.headers["Cache-Control"] = "private, no-store"
    return {"assignment_id": str(assignment_id), "items": people}


@router.get("/me/assignments/{assignment_id}/group-briefing", response_model=AssignmentGroupBriefing)
async def assignment_group_briefing(assignment_id: UUID, response: Response, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal), access: AssignmentAccess = Depends(get_assignment_access)):
    grant, people = await assignment_projection(db, principal, assignment_id, access)
    groups = (await db.scalars(select(ParticipantGroup).where(
        ParticipantGroup.id.in_(grant.group_ids), ParticipantGroup.foundation_id == principal.foundation_id
    ).order_by(ParticipantGroup.title, ParticipantGroup.id))).all()
    response.headers["Cache-Control"] = "private, no-store"
    # Current generic schedules/team grants are not event conditions. P09 owns those;
    # this projection exposes only the authorized group's name and captured roster.
    return {"assignment_id": str(assignment_id), "groups": [{"id": str(group.id), "title": group.title} for group in groups], "items": people}


@router.get("/me/assignments/{assignment_id}/participants/{participant_id}/photo")
async def assignment_photo(assignment_id: UUID, participant_id: UUID, db: AsyncSession = Depends(get_db), principal: Principal = Depends(get_principal), access: AssignmentAccess = Depends(get_assignment_access)):
    grant = await access.participants(db, principal, assignment_id)
    if grant.assignment_id != assignment_id or participant_id not in grant.participant_ids:
        denied()
    item = await db.scalar(select(Participant).where(Participant.id == participant_id, Participant.foundation_id == principal.foundation_id))
    if item is None:
        raise ApiError(404, "participant_not_found", "Участник недоступен.")
    return await photo_response(db, item)
