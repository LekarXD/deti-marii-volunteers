from collections import defaultdict
from datetime import date, datetime, time, timedelta
from uuid import UUID, uuid5, NAMESPACE_URL
from sqlalchemy import select, func, text
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.idempotency import payload_hash
from app.core.models import User
from app.modules.activities.models import Opportunity
from app.modules.activities.calendar_models import EventSeries, EventOccurrence
from app.modules.activities.assignment_models import Assignment, Attendance
from app.modules.profile.models import ServiceTimeEntry
from app.modules.profile.ledger import subject_lock
from app.modules.profile.dates import local_today
from app.modules.applications.models import Application, ApplicationRevision
from .models import DobroActivityLink, DobroSeriesOpportunity, DobroProfile, DobroEnrollment, DobroEnrollmentEvent, DobroTransfer, DobroSettings
from . import schemas as dto
from .calculation import Fact, allocate, month_start, next_month, ZONE


def permission(principal, name):
    if not principal.has_permission(name): raise ApiError(403, 'permission_denied', 'Недостаточно прав.')

async def foundation_lock(db, principal):
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'), {'key': f'dobro:{principal.foundation_id}'})

async def user(db, principal, user_id=None):
    identity = user_id or principal.user_id
    if not identity: raise ApiError(403, 'verified_account_required', 'Войдите в подтверждённый аккаунт.')
    result = await db.scalar(select(User).where(User.id == identity, User.foundation_id == principal.foundation_id, User.account_state == 'active'))
    if result is None: raise ApiError(404, 'volunteer_not_found', 'Человек не найден.')
    return result

async def crm_identity(db, principal, volunteer_id):
    from app.modules.crm.service import scoped_volunteer
    permission(principal, 'crm.read')
    volunteer = await scoped_volunteer(db, principal.foundation_id, volunteer_id)
    if not volunteer.user_id:
        raise ApiError(409, 'dobro_account_unlinked', 'У этого контакта ещё нет связанного аккаунта Опоры. Профиль Добро.рф можно добавить после подтверждения аккаунта; исторический контакт не становится волонтёром автоматически.')
    await user(db, principal, volunteer.user_id)
    return volunteer.user_id

def version(actual, expected):
    if actual != expected: raise ApiError(409, 'version_conflict', 'Данные изменились. Обновите страницу и проверьте изменения.')

def activity_view(row):
    return dto.DobroActivityView(id=row.id, opportunity_id=row.opportunity_id, url=row.url, kind=row.kind, title=row.title, valid_from=row.valid_from, valid_until=row.valid_until, version=row.version)

async def activity(db, principal, activity_id):
    row = await db.scalar(select(DobroActivityLink).where(DobroActivityLink.id == activity_id, DobroActivityLink.foundation_id == principal.foundation_id))
    if not row: raise ApiError(404, 'dobro_activity_not_found', 'Доброе дело не найдено.')
    return row

async def settings_view(db, principal):
    row = await db.get(DobroSettings, principal.foundation_id)
    if not row: return dto.DobroSettingsView()
    return dto.DobroSettingsView(**{key: getattr(row, key) for key in dto.DobroSettingsView.model_fields if key != 'rules_note'})

async def save_settings(db, principal, command):
    permission(principal, 'integrations.manage')
    await foundation_lock(db, principal)
    row = await db.get(DobroSettings, principal.foundation_id)
    version(row.version if row else 0, command.expected_version)
    if command.reminders_enabled:
        permission(principal, 'hours.review')
    if not row:
        row = DobroSettings(foundation_id=principal.foundation_id, version=0, updated_by=principal.actor_id)
        db.add(row)
    for key, value in command.model_dump(exclude={'expected_version'}).items(): setattr(row, key, value)
    row.version += 1
    row.updated_by = principal.actor_id
    row.reminder_owner_user_id = principal.user_id if command.reminders_enabled else None
    await db.flush()
    if row.reminders_enabled:
        from app.worker.queue import enqueue_job
        enqueue_job(db, principal.foundation_id, 'dobro.reminders.scan', {'settings_version': row.version, 'scheduled_for': utcnow().isoformat()})
    return await settings_view(db, principal)

async def list_links(db, principal, opportunity_id):
    opportunity = await db.scalar(select(Opportunity).where(Opportunity.id == opportunity_id, Opportunity.foundation_id == principal.foundation_id))
    if not opportunity: raise ApiError(404, 'opportunity_not_found', 'Возможность не найдена.')
    rows = (await db.scalars(select(DobroActivityLink).where(DobroActivityLink.foundation_id == principal.foundation_id, DobroActivityLink.opportunity_id == opportunity_id).order_by(DobroActivityLink.valid_from.desc()))).all()
    return [activity_view(row).model_copy(update={'can_edit': not await link_used(db, row)}) for row in rows]

async def link_used(db, row, command=None):
    enrollment = await db.scalar(select(DobroEnrollment.id).where(DobroEnrollment.activity_id == row.id).limit(1))
    transferred = await db.scalar(select(DobroTransfer.id).where(DobroTransfer.activity_id == row.id).limit(1))
    if enrollment or transferred: return True
    earliest = min(row.valid_from, command.valid_from) if command else row.valid_from
    latest = max(row.valid_until, command.valid_until) if command else row.valid_until
    return bool(await db.scalar(select(ServiceTimeEntry.id).join(Assignment, ServiceTimeEntry.assignment_id == Assignment.id).join(EventOccurrence, Assignment.occurrence_id == EventOccurrence.id).join(DobroSeriesOpportunity, DobroSeriesOpportunity.series_id == EventOccurrence.series_id).where(ServiceTimeEntry.foundation_id == row.foundation_id, DobroSeriesOpportunity.foundation_id == row.foundation_id, DobroSeriesOpportunity.opportunity_id == row.opportunity_id, ServiceTimeEntry.service_date >= earliest, ServiceTimeEntry.service_date <= latest).limit(1)))

async def update_link(db, principal, opportunity_id, activity_id, command):
    permission(principal, 'opportunities.manage')
    await foundation_lock(db, principal)
    row = await activity(db, principal, activity_id)
    if row.opportunity_id != opportunity_id: raise ApiError(404, 'dobro_activity_not_found', 'Доброе дело не найдено.')
    version(row.version, command.expected_version)
    if await link_used(db, row, command): raise ApiError(409, 'dobro_activity_has_history', 'По этой ссылке уже есть отклики или факты участия. Изменять её нельзя: добавьте ссылку на следующий период.')
    overlapping = await db.scalar(select(DobroActivityLink.id).where(DobroActivityLink.foundation_id == principal.foundation_id, DobroActivityLink.opportunity_id == opportunity_id, DobroActivityLink.id != row.id, DobroActivityLink.valid_from <= command.valid_until, DobroActivityLink.valid_until >= command.valid_from))
    if overlapping: raise ApiError(409, 'dobro_activity_overlap', 'Периоды двух добрых дел одной возможности пересекаются.')
    for key, value in command.model_dump(exclude={'expected_version'}).items(): setattr(row, key, value)
    row.version += 1
    row.actor_id = principal.actor_id
    await db.flush()
    return activity_view(row).model_copy(update={'can_edit': True})

async def create_link(db, principal, opportunity_id, command):
    permission(principal, 'opportunities.manage')
    await foundation_lock(db, principal)
    await list_links(db, principal, opportunity_id)
    overlapping = await db.scalar(select(DobroActivityLink.id).where(DobroActivityLink.foundation_id == principal.foundation_id, DobroActivityLink.opportunity_id == opportunity_id, DobroActivityLink.valid_from <= command.valid_until, DobroActivityLink.valid_until >= command.valid_from))
    if overlapping: raise ApiError(409, 'dobro_activity_overlap', 'У этой возможности уже есть доброе дело на выбранные даты. Ссылки сохраняют историю; выберите следующий период.')
    row = DobroActivityLink(foundation_id=principal.foundation_id, opportunity_id=opportunity_id, actor_id=principal.actor_id, **command.model_dump())
    db.add(row)
    await db.flush()
    return activity_view(row).model_copy(update={'can_edit': True})

async def series_view(db, principal, series_id):
    series = await db.scalar(select(EventSeries).where(EventSeries.id == series_id, EventSeries.foundation_id == principal.foundation_id))
    if not series: raise ApiError(404, 'event_not_found', 'Событие не найдено.')
    row = await db.scalar(select(DobroSeriesOpportunity).where(DobroSeriesOpportunity.series_id == series_id, DobroSeriesOpportunity.foundation_id == principal.foundation_id))
    has_facts = bool(await db.scalar(select(ServiceTimeEntry.id).join(Assignment, ServiceTimeEntry.assignment_id == Assignment.id).join(EventOccurrence, Assignment.occurrence_id == EventOccurrence.id).where(ServiceTimeEntry.foundation_id == principal.foundation_id, EventOccurrence.series_id == series_id).limit(1)))
    opportunity = await db.get(Opportunity, row.opportunity_id) if row else None
    return dto.DobroSeriesView(series_id=series_id, opportunity_id=row.opportunity_id if row else None, opportunity_title=opportunity.title if opportunity else '', version=row.version if row else 0, locked=has_facts)

async def save_series(db, principal, series_id, command):
    permission(principal, 'opportunities.manage')
    await foundation_lock(db, principal)
    current = await series_view(db, principal, series_id)
    version(current.version, command.expected_version)
    await list_links(db, principal, command.opportunity_id)
    if current.locked and current.opportunity_id != command.opportunity_id:
        raise ApiError(409, 'dobro_series_has_history', 'У события уже есть факты участия. Менять возможность нельзя: это изменит историю часов. Создайте новую серию.')
    row = await db.get(DobroSeriesOpportunity, series_id)
    if not row:
        row = DobroSeriesOpportunity(series_id=series_id, foundation_id=principal.foundation_id, opportunity_id=command.opportunity_id, version=1, actor_id=principal.actor_id)
        db.add(row)
    elif row.opportunity_id != command.opportunity_id:
        row.opportunity_id = command.opportunity_id
        row.version += 1
        row.actor_id = principal.actor_id
    await db.flush()
    return await series_view(db, principal, series_id)

async def accessible_activity(db, principal, link, user_id):
    """Own enrollment is available only for a confirmed/past linked assignment."""
    found = await db.scalar(select(Assignment.id).join(EventOccurrence, Assignment.occurrence_id == EventOccurrence.id).join(DobroSeriesOpportunity, EventOccurrence.series_id == DobroSeriesOpportunity.series_id).where(Assignment.foundation_id == principal.foundation_id, Assignment.user_id == user_id, Assignment.status == 'confirmed', DobroSeriesOpportunity.foundation_id == principal.foundation_id, DobroSeriesOpportunity.opportunity_id == link.opportunity_id, EventOccurrence.starts_at >= datetime.combine(link.valid_from, time.min, ZONE), EventOccurrence.starts_at < datetime.combine(link.valid_until + timedelta(days=1), time.min, ZONE)).limit(1))
    return bool(found)

async def change_enrollment(db, principal, activity_id, user_id, command, own=False):
    await foundation_lock(db, principal)
    await user(db, principal, user_id)
    link = await activity(db, principal, activity_id)
    if own and (user_id != principal.user_id or not await accessible_activity(db, principal, link, user_id)):
        raise ApiError(404, 'dobro_activity_not_found', 'Доброе дело недоступно.')
    row = await db.scalar(select(DobroEnrollment).where(DobroEnrollment.activity_id == activity_id, DobroEnrollment.user_id == user_id).with_for_update())
    old = row.state if row else 'none'
    version(row.version if row else 0, command.expected_version)
    allowed = {'none': {'applied', 'not_needed'}, 'applied': {'not_needed'}, 'approved': {'not_needed'}, 'not_needed': {'none'}} if own else {'none': {'approved', 'not_needed'}, 'applied': {'approved', 'not_needed'}, 'approved': {'not_needed'}, 'not_needed': {'none'}}
    if command.state != old and command.state not in allowed[old]:
        raise ApiError(409, 'dobro_transition_rejected', 'Проверьте текущее состояние отклика.')
    if old == command.state:
        return {'state': old, 'version': row.version if row else 0}
    if not row:
        row = DobroEnrollment(foundation_id=principal.foundation_id, user_id=user_id, activity_id=activity_id, version=0)
        db.add(row)
    row.state = command.state
    row.version += 1
    row.updated_at = utcnow()
    await db.flush()
    db.add(DobroEnrollmentEvent(enrollment_id=row.id, version=row.version, state=row.state, actor_id=principal.actor_id, reason='Изменение отклика'))
    await db.flush()
    return {'state': row.state, 'version': row.version}

async def save_profile(db, principal, user_id, command):
    await user(db, principal, user_id)
    await foundation_lock(db, principal)
    row = await db.scalar(select(DobroProfile).where(DobroProfile.user_id == user_id, DobroProfile.foundation_id == principal.foundation_id).with_for_update())
    version(row.version if row else 0, command.expected_version)
    if not row:
        row = DobroProfile(user_id=user_id, foundation_id=principal.foundation_id, version=0, updated_by=principal.actor_id)
        db.add(row)
    row.profile_url = command.profile_url
    row.version += 1
    row.updated_by = principal.actor_id
    row.updated_at = utcnow()
    await db.flush()
    return {'profile_url': row.profile_url, 'version': row.version}

async def projections(db, principal, end):
    """One bulk read per source; corrections recompute the cumulative projection."""
    links = (await db.scalars(select(DobroActivityLink).where(DobroActivityLink.foundation_id == principal.foundation_id, DobroActivityLink.valid_from < end))).all()
    mappings = {row.series_id: row for row in (await db.scalars(select(DobroSeriesOpportunity).where(DobroSeriesOpportunity.foundation_id == principal.foundation_id))).all()}
    ledger = (await db.execute(select(ServiceTimeEntry, Assignment, EventOccurrence).join(Assignment, ServiceTimeEntry.assignment_id == Assignment.id).join(EventOccurrence, Assignment.occurrence_id == EventOccurrence.id).where(ServiceTimeEntry.foundation_id == principal.foundation_id, Assignment.foundation_id == principal.foundation_id, EventOccurrence.foundation_id == principal.foundation_id, ServiceTimeEntry.source_kind == 'attendance', ServiceTimeEntry.service_date < end, EventOccurrence.ends_at <= utcnow()))).all()
    totals = defaultdict(int)
    sources = []
    pairs = {}
    for entry, assignment, occurrence in ledger:
        totals[assignment.id] += entry.delta_minutes
        pairs[assignment.id] = (assignment, occurrence)
        sources.append((str(entry.id), entry.delta_minutes, str(entry.service_date)))
    by_opportunity = defaultdict(list)
    for link in links: by_opportunity[link.opportunity_id].append(link)
    facts = []
    for assignment_id, minutes in totals.items():
        assignment, occurrence = pairs[assignment_id]
        if minutes <= 0: continue
        mapping = mappings.get(occurrence.series_id)
        local_date = occurrence.starts_at.astimezone(ZONE).date()
        link = next((link for link in by_opportunity.get(mapping.opportunity_id if mapping else None, []) if link.valid_from <= local_date <= link.valid_until), None)
        if link:
            facts.append(Fact(assignment_id, assignment.user_id, occurrence.starts_at, occurrence.ends_at, minutes, link.id))
    allocations = allocate(facts)
    enrollments = (await db.scalars(select(DobroEnrollment).where(DobroEnrollment.foundation_id == principal.foundation_id))).all()
    transfers = (await db.scalars(select(DobroTransfer).where(DobroTransfer.foundation_id == principal.foundation_id).order_by(DobroTransfer.entered_at, DobroTransfer.id))).all()
    # All valid current users, never another foundation's account, even if a broken
    # foreign source was inserted outside supported application writes.
    users = {row.id: row for row in (await db.scalars(select(User).where(User.foundation_id == principal.foundation_id))).all()}
    profiles = {row.user_id: row.profile_url for row in (await db.scalars(select(DobroProfile).where(DobroProfile.foundation_id == principal.foundation_id))).all()}
    fingerprint = payload_hash({'sources': sorted(sources), 'facts': [(str(f.assignment_id), str(f.starts_at), str(f.ends_at), f.minutes, str(f.activity_id)) for f in facts], 'links': [(str(l.id), l.version) for l in links], 'mappings': sorted((str(key), str(value.opportunity_id), value.version) for key, value in mappings.items())})
    return links, allocations, enrollments, transfers, users, profiles, fingerprint

async def transfer_period(db, principal, period, only_user=None):
    start = month_start(period)
    end = next_month(start)
    settings = await settings_view(db, principal)
    links, allocations, enrollments, transfers, users, profiles, fingerprint = await projections(db, principal, end)
    structured_names = (await db.execute(select(Application.user_id, ApplicationRevision.answers).join(ApplicationRevision, Application.submitted_revision_id == ApplicationRevision.id).where(Application.foundation_id == principal.foundation_id, Application.user_id.is_not(None)))).all()
    sort_names = {identity: (str(answers.get('lastName', '')).strip() + ' ' + str(answers.get('firstName', '')).strip()).strip().casefold() for identity, answers in structured_names}
    enrollment_map = {(row.activity_id, row.user_id): row for row in enrollments}
    allocation_map = defaultdict(list)
    history_map = defaultdict(list)
    for item in allocations:
        if item.activity_id: allocation_map[(item.activity_id, item.user_id)].append(item)
    for item in transfers: history_map[(item.activity_id, item.user_id)].append(item)
    keys = set(allocation_map) | set(history_map) | set(enrollment_map)
    groups = []
    for link in sorted(links, key=lambda value: (value.title.casefold(), str(value.id))):
        rows = []
        for activity_id, user_id in keys:
            if activity_id != link.id or user_id not in users or (only_user and user_id != only_user): continue
            values = allocation_map[(activity_id, user_id)]
            current = [item for item in values if start <= item.day < end]
            eligible = sum(item.eligible_minutes for item in values if item.day < end)
            raw = sum(item.raw_minutes for item in current)
            enrolled = enrollment_map.get((activity_id, user_id))
            state = enrolled.state if enrolled else 'none'
            history = history_map[(activity_id, user_id)]
            historical = any(item.period > start for item in history)
            entered = sum(item.hours_delta for item in history)
            target = eligible // 60
            due = 0 if historical else target - entered
            hard = link.valid_until + timedelta(days=settings.hard_deadline_days)
            deadline_state = 'complete' if not due else 'overdue' if hard < local_today() else 'risk' if hard <= local_today() + timedelta(days=settings.risk_days) else 'open'
            row_id = uuid5(NAMESPACE_URL, f'opora-dobro:{principal.foundation_id}:{activity_id}:{user_id}:{period}')
            snapshot_hash = payload_hash({'source': fingerprint, 'settings': settings.model_dump(mode='json'), 'activity': str(activity_id), 'user': str(user_id), 'period': period, 'state': state, 'version': enrolled.version if enrolled else 0, 'eligible': eligible, 'entered': [(str(item.id), item.hours_delta, str(item.period)) for item in history], 'due': due})
            rows.append(dto.DobroTransferRowView(id=row_id, user_id=user_id, display_name=users[user_id].display_name, profile_url=profiles.get(user_id) or None, state=state, enrollment_version=enrolled.version if enrolled else 0, minutes_in_period=raw, eligible_minutes=eligible, capped_minutes=sum(item.capped_minutes for item in current), overlap_minutes=sum(item.overlap_minutes for item in current), duration_trimmed_minutes=sum(item.duration_trimmed_minutes for item in current), carry_minutes=eligible % 60, entered_hours=entered, hours_due=due, target_total_hours=target, correction_hours=max(0, -due), hard_deadline=hard, deadline_state=deadline_state, can_mark=not historical and start <= local_today().replace(day=1) and state in ('applied', 'approved') and due != 0, historical=historical, snapshot_hash=snapshot_hash, history=[dto.DobroTransferHistoryView(id=item.id, period=item.period.strftime('%Y-%m'), hours_delta=item.hours_delta, minutes_due_snapshot=item.minutes_due_snapshot, note=item.note, entered_at=item.entered_at) for item in history], reminder_text=settings.reminder_template.replace('{имя}', users[user_id].display_name.split()[0] if users[user_id].display_name else '').replace('{ссылка}', link.url)))
        if rows:
            rows.sort(key=lambda item: (sort_names.get(item.user_id) or item.display_name.casefold(), str(item.user_id)))
            groups.append(dto.DobroTransferGroupView(activity=activity_view(link), rows=rows))
    active = [row for group in groups for row in group.rows if row.state != 'not_needed' and row.hours_due]
    return dto.DobroTransferPeriodView(period=period, groups=groups, total_hours_due=sum(max(0, row.hours_due) for row in active), total_people=len({row.user_id for row in active}), work_deadline=end.replace(day=settings.monthly_day), at_risk_count=sum(row.deadline_state in ('risk', 'overdue') for row in active), rules_note=settings.rules_note)

async def mark_entered(db, principal, command):
    permission(principal, 'hours.review')
    # Attendance writes take the minute-ledger subject lock before their Dobro
    # mapping trigger takes the foundation lock. Preserve that order here too.
    for user_id in sorted({item.user_id for item in command.rows}, key=str):
        await user(db, principal, user_id)
        await subject_lock(db, principal.foundation_id, user_id)
    await foundation_lock(db, principal)
    period = command.rows[0].period
    current = await transfer_period(db, principal, period)
    current_rows = {row.id: (group.activity, row) for group in current.groups for row in group.rows}
    for command_row in command.rows:
        pair = current_rows.get(command_row.id)
        if not pair or pair[0].id != command_row.activity_id or pair[1].user_id != command_row.user_id:
            raise ApiError(404, 'dobro_transfer_not_found', 'Строка переноса не найдена.')
        link, row = pair
        if row.snapshot_hash != command_row.snapshot_hash:
            raise ApiError(409, 'dobro_snapshot_changed', 'Часы или отклик изменились. Обновите расчёт и ещё раз сверьте внесённое в Добро.рф.')
        if not row.can_mark or not command_row.hours_delta or command_row.hours_delta * row.hours_due <= 0 or abs(command_row.hours_delta) > abs(row.hours_due):
            raise ApiError(409, 'dobro_mark_rejected', 'Сверьте отклик и сумму. Подтвердить можно только часы из актуального расчёта.')
        db.add(DobroTransfer(foundation_id=principal.foundation_id, user_id=row.user_id, activity_id=link.id, period=month_start(period), minutes_due_snapshot=row.hours_due * 60, hours_delta=command_row.hours_delta, snapshot_hash=row.snapshot_hash, snapshot=row.model_dump(mode='json'), actor_id=principal.actor_id, note=command.note.strip()))
        enrollment = await db.scalar(select(DobroEnrollment).where(DobroEnrollment.activity_id == link.id, DobroEnrollment.user_id == row.user_id).with_for_update())
        if enrollment.state == 'applied':
            enrollment.state = 'approved'
            enrollment.version += 1
            enrollment.updated_at = utcnow()
            db.add(DobroEnrollmentEvent(enrollment_id=enrollment.id, version=enrollment.version, state='approved', actor_id=principal.actor_id, reason='Координатор подтвердил ручное внесение часов в CRM Добро.рф'))
    await db.flush()
    return await transfer_period(db, principal, period)

async def own_view(db, principal):
    own = await user(db, principal)
    current = await transfer_period(db, principal, local_today().strftime('%Y-%m'), own.id)
    settings = await settings_view(db, principal)
    profile = await db.scalar(select(DobroProfile).where(DobroProfile.foundation_id == principal.foundation_id, DobroProfile.user_id == own.id))
    items = []
    seen = set()
    for group in current.groups:
        for row in group.rows:
            seen.add(group.activity.id)
            link = await activity(db, principal, group.activity.id)
            items.append(dto.DobroOwnActivityView(activity=group.activity, state=row.state, enrollment_version=row.enrollment_version, eligible_minutes=row.eligible_minutes, entered_hours=row.entered_hours, hours_due=row.hours_due, carry_minutes=row.carry_minutes, can_apply=await accessible_activity(db, principal, link, own.id)))
    links = (await db.scalars(select(DobroActivityLink).where(DobroActivityLink.foundation_id == principal.foundation_id, DobroActivityLink.valid_until >= local_today()))).all()
    for link in links:
        if link.id not in seen and await accessible_activity(db, principal, link, own.id):
            items.append(dto.DobroOwnActivityView(activity=activity_view(link), state='none', enrollment_version=0, eligible_minutes=0, entered_hours=0, hours_due=0, carry_minutes=0, can_apply=True))
    total = await db.scalar(select(func.coalesce(func.sum(ServiceTimeEntry.delta_minutes), 0)).where(ServiceTimeEntry.foundation_id == principal.foundation_id, ServiceTimeEntry.user_id == own.id))
    return dto.DobroOwnView(profile_url=profile.profile_url if profile else '', profile_version=profile.version if profile else 0, registration_url=settings.registration_url, verified_organization=settings.verified, total_minutes=max(0, total), entered_hours=sum(item.entered_hours for item in items), hours_due=sum(max(0, item.hours_due) for item in items if item.state != 'not_needed'), activities=items, rules_note=settings.rules_note)

async def team_view(db, principal, occurrence_id):
    occurrence = await db.scalar(select(EventOccurrence).where(EventOccurrence.id == occurrence_id, EventOccurrence.foundation_id == principal.foundation_id))
    if not occurrence: raise ApiError(404, 'event_not_found', 'Событие не найдено.')
    mapping = await db.scalar(select(DobroSeriesOpportunity).where(DobroSeriesOpportunity.series_id == occurrence.series_id, DobroSeriesOpportunity.foundation_id == principal.foundation_id))
    if not mapping: return dto.DobroTeamView()
    day = occurrence.starts_at.astimezone(ZONE).date()
    link = await db.scalar(select(DobroActivityLink).where(DobroActivityLink.opportunity_id == mapping.opportunity_id, DobroActivityLink.foundation_id == principal.foundation_id, DobroActivityLink.valid_from <= day, DobroActivityLink.valid_until >= day))
    if not link: return dto.DobroTeamView()
    settings = await settings_view(db, principal)
    rows = (await db.execute(select(User, DobroEnrollment).join(Assignment, User.id == Assignment.user_id).outerjoin(DobroEnrollment, (DobroEnrollment.user_id == User.id) & (DobroEnrollment.activity_id == link.id)).where(Assignment.occurrence_id == occurrence_id, Assignment.foundation_id == principal.foundation_id, User.foundation_id == principal.foundation_id, Assignment.status.in_(('confirmed', 'invited'))).order_by(User.display_name, User.id))).all()
    preparation = [dto.DobroPreparationView(key='publish_activity', title='Опубликовать мероприятие на Добро.рф', date=link.valid_from-timedelta(days=21), note='Рекомендуемый срок подготовки. Фактический срок модерации уточните в Добро.рф.'), dto.DobroPreparationView(key='enter_hours', title='Внести часы в CRM Добро.рф', date=link.valid_until+timedelta(days=settings.hard_deadline_days), note='Жёсткий срок из настроек фонда. Перенос выполняет координатор вручную.')] if link.kind == 'one_off' else []
    return dto.DobroTeamView(activity=activity_view(link), people=[dto.DobroTeamPersonView(user_id=person.id, display_name=person.display_name, state=enrollment.state if enrollment else 'none', enrollment_version=enrollment.version if enrollment else 0, reminder_text=settings.reminder_template.replace('{имя}', person.display_name.split()[0] if person.display_name else '').replace('{ссылка}', link.url)) for person, enrollment in rows], preparation=preparation)
