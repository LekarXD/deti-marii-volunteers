import asyncio
import os
from datetime import datetime, date, timedelta, time
from uuid import UUID, uuid4
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import get_settings
from app.core.db import Base, get_db
from app.core.errors import install_error_handlers
from app.core.models import Foundation, User, PermissionGrant
from app.core.model_loader import load_models
from app.modules.applications.tests.test_applications import staff, post
from app.modules.auth.router import router as auth_router
from app.modules.activities.models import Opportunity, VolunteerRole, VolunteerRoleVersion
from app.modules.activities.calendar_models import EventSeries, EventOccurrence, StaffingNeed
from app.modules.activities.assignment_models import Assignment, Attendance, AttendanceEvent
from app.modules.profile.models import ServiceTimeEntry
from app.modules.profile.ledger import append_service_time
from app.modules.profile.tests.test_profile import principal_for
from app.modules.dobro.router import router
from app.modules.dobro.models import DobroActivityLink, DobroSeriesOpportunity, DobroTransfer, DobroEnrollment
from app.modules.dobro.calculation import ZONE
from app.modules.dobro import service
load_models()

@pytest_asyncio.fixture
async def world():
    url = os.getenv('OPORA_DOBRO_TEST_DATABASE_URL', '')
    if not url: pytest.skip('Dedicated OPORA_DOBRO_TEST_DATABASE_URL required')
    if not url.endswith('/opora_dobro_test'): raise RuntimeError('Refusing a non-Dobro test database')
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    async with factory() as db:
        foundation = Foundation(id=get_settings().foundation_id, name='Вымышленный тестовый фонд')
        db.add(foundation)
        await db.commit()
    app = FastAPI()
    install_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(router)
    async def override():
        async with factory() as db:
            try: yield db
            except BaseException:
                await db.rollback()
                raise
    app.dependency_overrides[get_db] = override
    coordinator = await staff(app, factory, ('hours.review', 'opportunities.manage', 'integrations.manage', 'assignments.manage', 'crm.read'))
    volunteer = await staff(app, factory, ())
    principal = await principal_for(coordinator, factory)
    own = await principal_for(volunteer, factory)
    yield app, factory, coordinator, volunteer, principal, own
    await coordinator.aclose()
    await volunteer.aclose()
    await engine.dispose()

async def link_fixture(world, title='Арт-субботы'):
    _, factory, coordinator, _, principal, _ = world
    async with factory() as db:
        opportunity = Opportunity(foundation_id=principal.foundation_id, title=title, updated_by=principal.actor_id)
        db.add(opportunity)
        await db.commit()
    response = await post(coordinator, f'/fund/opportunities/{opportunity.id}/dobro', dict(title=title + ' — сезон', url='https://dobro.ru/event/12345', kind='long_term', valid_from='2026-08-01', valid_until='2026-12-31'))
    assert response.status_code == 200, response.text
    return opportunity, response.json()

async def fact_fixture(world, opportunity, day, minutes, hour=9, duration=None, mapped=True):
    _, factory, _, _, principal, own = world
    start = datetime.combine(date.fromisoformat(day), time(hour), ZONE)
    async with factory() as db:
        role = VolunteerRole(foundation_id=principal.foundation_id, title='Роль ' + str(uuid4()), normalized_title=str(uuid4()), updated_by=principal.actor_id)
        db.add(role)
        await db.flush()
        revision = VolunteerRoleVersion(role_id=role.id, version=1, snapshot={}, actor_id=principal.actor_id)
        series = EventSeries(foundation_id=principal.foundation_id, anchor_date=start.date(), origin_time=start.time().replace(tzinfo=None), start_date=start.date(), start_time=start.time().replace(tzinfo=None), duration_minutes=duration or minutes, recurrence={'frequency':'once'}, title='Вымышленное событие', updated_by=principal.actor_id)
        db.add_all([revision, series])
        await db.flush()
        occurrence = EventOccurrence(id=uuid4(), foundation_id=principal.foundation_id, series_id=series.id, origin_local_date=start.date(), origin_local_time=start.time().replace(tzinfo=None), starts_at=start, ends_at=start + timedelta(minutes=duration or minutes), timezone='Europe/Moscow', title=series.title, series_version=1, updated_by=principal.actor_id)
        db.add(occurrence)
        await db.flush()
        need = StaffingNeed(foundation_id=principal.foundation_id, occurrence_id=occurrence.id, role_id=role.id, role_version_id=revision.id, capacity_required=1)
        db.add(need)
        await db.flush()
        assignment = Assignment(foundation_id=principal.foundation_id, user_id=own.user_id, occurrence_id=occurrence.id, staffing_need_id=need.id, conditions_version=1, conditions_snapshot={}, status='confirmed', confirmed_at=start - timedelta(days=1))
        db.add(assignment)
        await db.flush()
        attendance = Attendance(foundation_id=principal.foundation_id, assignment_id=assignment.id, outcome='attended', minutes=minutes)
        db.add(attendance)
        await db.flush()
        event = AttendanceEvent(foundation_id=principal.foundation_id, attendance_id=attendance.id, assignment_id=assignment.id, user_id=own.user_id, version=1, old_minutes=0, new_minutes=minutes, reason='Вымышленный факт', actor_id=principal.actor_id)
        db.add(event)
        await db.flush()
        await append_service_time(db, principal, own.user_id, assignment.id, event.id)
        if mapped:
            db.add(DobroSeriesOpportunity(series_id=series.id, foundation_id=principal.foundation_id, opportunity_id=opportunity.id, actor_id=principal.actor_id))
        await db.commit()
    return assignment, attendance, series

async def period(world, month='2026-08'):
    response = await world[2].get('/api/v1/fund/integrations/dobro/transfers', params={'period': month})
    assert response.status_code == 200, response.text
    return response.json()

async def enroll(world, activity, state='applied', expected=0):
    response = await post(world[3], f"/me/dobro-enrollments/{activity['id']}", {'state':state, 'expected_version':expected})
    assert response.status_code == 200, response.text
    return response.json()

def mark_body(view, row, activity_id, hours=None, note='Проверено в тестовой CRM'):
    return {'confirmed':True, 'note':note, 'rows':[{'id':row['id'], 'user_id':row['user_id'], 'activity_id':activity_id, 'period':view['period'], 'snapshot_hash':row['snapshot_hash'], 'hours_delta':row['hours_due'] if hours is None else hours}]}

@pytest.mark.asyncio
async def test_real_ledger_cap_all_linked_activities_and_unlinked_does_not_consume(world):
    first, a = await link_fixture(world)
    second, b = await link_fixture(world, 'Ярмарка')
    await fact_fixture(world, first, '2026-08-02', 120, hour=6, mapped=False)
    await fact_fixture(world, first, '2026-08-02', 360, hour=8)
    await fact_fixture(world, second, '2026-08-02', 300, hour=14)
    view = await period(world)
    rows = {group['activity']['id']:group['rows'][0] for group in view['groups']}
    assert rows[a['id']]['hours_due'] == 6
    assert rows[b['id']]['hours_due'] == 2
    assert rows[b['id']]['capped_minutes'] == 180
    assert sum(row['eligible_minutes'] for row in rows.values()) == 480
    assert not any(row['can_mark'] for row in rows.values())
    own = (await world[3].get('/api/v1/me/dobro')).json()
    assert own['total_minutes'] == 780 and own['hours_due'] == 8

@pytest.mark.asyncio
async def test_carry_applied_approval_concurrency_idempotency_and_negative_correction(world):
    opportunity, activity = await link_fixture(world)
    assignment, attendance, _ = await fact_fixture(world, opportunity, '2026-08-03', 100)
    await enroll(world, activity)
    before = await period(world)
    row = before['groups'][0]['rows'][0]
    assert row['hours_due'] == 1 and row['carry_minutes'] == 40
    payload = mark_body(before, row, activity['id'])
    results = await asyncio.gather(*[post(world[2], '/fund/integrations/dobro/transfers/mark-entered', payload, 'same-entry') for _ in range(2)])
    assert [r.status_code for r in results] == [200, 200], [r.text for r in results]
    assert results[0].json() == results[1].json()
    stored = results[0].json()['groups'][0]['rows'][0]
    assert stored['state'] == 'approved' and stored['entered_hours'] == 1 and stored['hours_due'] == 0
    assert (await post(world[2], '/fund/integrations/dobro/transfers/mark-entered', payload)).status_code == 409
    await fact_fixture(world, opportunity, '2026-09-03', 30)
    september = await period(world, '2026-09')
    sep_row = september['groups'][0]['rows'][0]
    assert sep_row['hours_due'] == 1 and sep_row['carry_minutes'] == 10
    assert (await post(world[2], '/fund/integrations/dobro/transfers/mark-entered', mark_body(september, sep_row, activity['id']))).status_code == 200
    async with world[1]() as db:
        current = await db.get(Attendance, attendance.id)
        current.minutes = 20
        current.version = 2
        event = AttendanceEvent(foundation_id=world[4].foundation_id, attendance_id=attendance.id, assignment_id=assignment.id, user_id=world[5].user_id, version=2, old_minutes=100, new_minutes=20, reason='Исправлен тестовый факт', actor_id=world[4].actor_id)
        db.add(event)
        await db.flush()
        await append_service_time(db, world[4], world[5].user_id, assignment.id, event.id)
        await db.commit()
    october = await period(world, '2026-10')
    correction = october['groups'][0]['rows'][0]
    assert correction['hours_due'] == -2 and correction['correction_hours'] == 2 and correction['carry_minutes'] == 50
    negative = mark_body(october, correction, activity['id'], note='Исправление ошибочного факта участия')
    assert (await post(world[2], '/fund/integrations/dobro/transfers/mark-entered', negative)).status_code == 200
    async with world[1]() as db:
        assert await db.scalar(select(func.count()).select_from(DobroTransfer)) == 3
        assert await db.scalar(select(func.sum(ServiceTimeEntry.delta_minutes))) == 50
    historical = (await period(world))['groups'][0]['rows'][0]
    assert historical['historical'] and not historical['can_mark']

@pytest.mark.asyncio
async def test_states_link_overlap_url_validation_scope_and_current_revoke(world):
    opportunity, activity = await link_fixture(world)
    assignment, _, series = await fact_fixture(world, opportunity, '2026-08-04', 120)
    own = world[3]
    assert (await post(own, f"/me/dobro-enrollments/{activity['id']}", {'state':'approved','expected_version':0})).status_code == 409
    state = await enroll(world, activity, 'not_needed')
    view = await period(world)
    assert view['groups'][0]['rows'][0]['state'] == 'not_needed' and view['total_hours_due'] == 0
    async with world[1]() as db:
        assert (await db.get(Assignment, assignment.id)).status == 'confirmed'
        assert await db.scalar(select(func.sum(ServiceTimeEntry.delta_minutes))) == 120
    state = await enroll(world, activity, 'none', state['version'])
    await enroll(world, activity, expected=state['version'])
    overlap = await post(world[2], f'/fund/opportunities/{opportunity.id}/dobro', {'title':'Пересечение','url':'https://dobro.ru/event/3','kind':'long_term','valid_from':'2026-12-31','valid_until':'2027-01-01'})
    assert overlap.status_code == 409
    invalid = await own.put('/api/v1/me/external-profiles/dobro', json={'profile_url':'https://dobro.ru.evil.test/volunteers/1','expected_version':0}, headers={'Idempotency-Key':uuid4().hex})
    assert invalid.status_code == 422
    assert (await own.get('/api/v1/fund/integrations/dobro/transfers?period=2026-08')).status_code == 403
    async with world[1]() as db:
        foreign = Foundation(name='Чужой фонд')
        db.add(foreign)
        await db.flush()
        external = Opportunity(foundation_id=foreign.id, title='Чужое', updated_by='fixture')
        db.add(external)
        await db.commit()
    denied = await world[2].get(f'/api/v1/fund/opportunities/{external.id}/dobro')
    assert denied.status_code == 404
    changed = await world[2].put(f'/api/v1/fund/event-series/{series.id}/dobro-opportunity', json={'opportunity_id':str(opportunity.id),'expected_version':1}, headers={'Idempotency-Key':uuid4().hex})
    assert changed.status_code == 200
    second, _ = await link_fixture(world, 'Другое направление')
    blocked = await world[2].put(f'/api/v1/fund/event-series/{series.id}/dobro-opportunity', json={'opportunity_id':str(second.id),'expected_version':1}, headers={'Idempotency-Key':uuid4().hex})
    assert blocked.status_code == 409
    current = await period(world)
    payload = mark_body(current, current['groups'][0]['rows'][0], activity['id'])
    async with world[1]() as db:
        grants = (await db.scalars(select(PermissionGrant).where(PermissionGrant.permission == 'hours.review'))).all()
        for grant in grants: grant.revoked_at = __import__('app.core.clock', fromlist=['utcnow']).utcnow()
        await db.commit()
    assert (await post(world[2], '/fund/integrations/dobro/transfers/mark-entered', payload)).status_code == 403

@pytest.mark.asyncio
async def test_edit_unused_link_then_freeze_and_resolve_crm_profile_identity(world):
    from app.modules.crm.models import CrmVolunteer
    opportunity, activity = await link_fixture(world)
    update = {key:activity[key] for key in ('url','title','kind','valid_from','valid_until')}
    update.update(expected_version=1, url='https://dobro.ru/event/67890')
    response = await world[2].put(f"/api/v1/fund/opportunities/{opportunity.id}/dobro/{activity['id']}", json=update, headers={'Idempotency-Key':uuid4().hex})
    assert response.status_code == 200 and response.json()['version'] == 2, response.text
    await fact_fixture(world, opportunity, '2026-08-05', 120)
    update['expected_version'] = 2
    assert (await world[2].put(f"/api/v1/fund/opportunities/{opportunity.id}/dobro/{activity['id']}", json=update, headers={'Idempotency-Key':uuid4().hex})).status_code == 409
    async with world[1]() as db:
        linked = CrmVolunteer(foundation_id=world[4].foundation_id, user_id=world[5].user_id, display_name='Вымышленный связанный контакт')
        historical = CrmVolunteer(foundation_id=world[4].foundation_id, display_name='Исторический контакт')
        db.add_all([linked,historical])
        await db.commit()
    path = f'/api/v1/fund/volunteers/{linked.id}/external-profiles/dobro'
    assert (await world[2].get(path)).json() == {'profile_url':'','version':0}
    save = await world[2].put(path, json={'profile_url':'https://dobro.ru/volunteers/123','expected_version':0}, headers={'Idempotency-Key':uuid4().hex})
    assert save.status_code == 200, save.text
    assert (await world[3].get('/api/v1/me/dobro')).json()['profile_url'] == 'https://dobro.ru/volunteers/123'
    assert (await world[2].get(f'/api/v1/fund/volunteers/{world[5].user_id}/external-profiles/dobro')).status_code == 404
    missing = await world[2].get(f'/api/v1/fund/volunteers/{historical.id}/external-profiles/dobro')
    assert missing.status_code == 409 and missing.json()['code'] == 'dobro_account_unlinked'

@pytest.mark.asyncio
async def test_opt_in_reminders_real_worker_source_replay_and_revocation(world):
    from app.core.models import MfaFactor, Job, OutboxMessage
    from app.core.crypto import seal
    from app.core.clock import utcnow
    from app.modules.dobro.jobs import run_reminders
    from app.modules.dobro import notifications
    from app.modules.messaging.models import Message
    from app.modules.notifications.delivery import process_internal
    from app.worker.queue import claim, complete
    from app.worker.registry import JobContext
    import json
    from app.core.crypto import unseal
    opportunity, activity = await link_fixture(world)
    await fact_fixture(world, opportunity, '2026-08-06', 90)
    await enroll(world, activity)
    async with world[1]() as db:
        db.add(MfaFactor(user_id=world[4].user_id, secret_cipher=seal('JBSWY3DPEHPK3PXP'), confirmed_at=utcnow()))
        await db.commit()
    view = (await world[2].get('/api/v1/fund/integrations/dobro/settings')).json()
    assert not view['reminders_enabled']
    setting_body = {key:view[key] for key in ('organization_url','registration_url','verified','monthly_day','hard_deadline_days','risk_days','rules_confirmed','reminder_template')}
    setting_body.update(expected_version=0, reminders_enabled=True, monthly_day=1)
    saved = await world[2].put('/api/v1/fund/integrations/dobro/settings', json=setting_body, headers={'Idempotency-Key':uuid4().hex})
    assert saved.status_code == 200, saved.text
    async with world[1]() as db:
        scan = await claim(db, ['dobro.reminders.scan'])
        result = await run_reminders(db, JobContext(scan.id, scan.claim_token, scan.foundation_id, scan.payload))
        assert result['queued'] == 1
        await complete(db, scan.id, scan.claim_token, result)
        await db.commit()
    # A second due scan cannot enqueue the monthly notice twice.
    async with world[1]() as db:
        scan = await db.scalar(select(Job).where(Job.kind == 'dobro.reminders.scan', Job.state == 'succeeded'))
        from app.modules.dobro.jobs import enqueue_once
        from app.core.auth import load_background_staff_authorization
        from app.modules.dobro.models import DobroSettings
        owner = await load_background_staff_authorization(db, scan.foundation_id, world[4].user_id)
        settings = await db.get(DobroSettings, scan.foundation_id)
        await service.foundation_lock(db, world[4])
        assert not await enqueue_once(db, settings, owner, '2026-09', 'monthly')
        await db.commit()
    async with world[1]() as db:
        job = await claim(db, ['outbox.deliver'])
        outbox = await db.get(OutboxMessage, UUID(job.payload['outbox_id']))
        payload = json.loads(unseal(outbox.payload_cipher))
        assert outbox.channel == 'in_app'
        state = await process_internal(db, job, outbox, payload)
        assert state == 'delivered'
        await complete(db, job.id, job.claim_token, {'state':state})
        await db.commit()
        assert await db.scalar(select(func.count()).select_from(Message)) == 1

    # Already queued source resolution checks current grants again, not the grant
    # snapshot that was present when the scheduler ran.
    async with world[1]() as db:
        from app.modules.messaging.consumers import enqueue_notice
        outbox = enqueue_notice(db, world[4].foundation_id, world[4].user_id, '', '', source=payload['source'])
        grant = await db.scalar(select(PermissionGrant).where(PermissionGrant.permission == 'hours.review'))
        grant.revoked_at = utcnow()
        await db.commit()
    async with world[1]() as db:
        job = await claim(db, ['outbox.deliver'])
        stored = await db.get(OutboxMessage, UUID(job.payload['outbox_id']))
        suppressed = await process_internal(db, job, stored, json.loads(unseal(stored.payload_cipher)))
        assert suppressed == 'suppressed_dobro_revoked'
        await complete(db, job.id, job.claim_token, {'state':suppressed})
        await db.commit()
        assert await db.scalar(select(func.count()).select_from(Message)) == 1

@pytest.mark.asyncio
async def test_own_export_is_scoped_and_excludes_staff_notes_and_snapshots(world):
    import json
    import io
    import zipfile
    from app.modules.dobro.data_export import own_export_section
    from app.modules.dobro.models import DobroProfile
    opportunity, activity = await link_fixture(world)
    await fact_fixture(world, opportunity, '2026-08-07', 125)
    await enroll(world, activity)
    view = await period(world)
    body = mark_body(view, view['groups'][0]['rows'][0], activity['id'], note='PRIVATE_COORDINATOR_NOTE_NOT_FOR_EXPORT')
    assert (await post(world[2], '/fund/integrations/dobro/transfers/mark-entered', body)).status_code == 200
    async with world[1]() as db:
        stranger = User(foundation_id=world[4].foundation_id, display_name='STRANGER_DISPLAY_NAME')
        db.add(stranger)
        await db.flush()
        db.add(DobroProfile(user_id=stranger.id, foundation_id=world[4].foundation_id, profile_url='https://dobro.ru/volunteers/999999', updated_by=world[4].actor_id))
        await db.commit()
    async with world[1]() as db:
        exported = await own_export_section(db, world[5])
    encoded = json.dumps(exported, ensure_ascii=False)
    assert exported['current']['total_minutes'] == 125
    assert exported['current']['entered_hours'] == 2
    assert len(exported['transfers']) == 1 and exported['transfers'][0]['hours_delta'] == 2
    assert 'PRIVATE_COORDINATOR_NOTE_NOT_FOR_EXPORT' not in encoded
    assert 'STRANGER_DISPLAY_NAME' not in encoded and '/volunteers/999999' not in encoded
    assert 'snapshot_hash' not in encoded and 'actor_id' not in encoded
    from app.modules.profile.data_requests import own_export
    async with world[1]() as db:
        archive_bytes = await own_export(db, world[5])
    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        payload = json.loads(archive.read('my-data.json'))
    assert 'dobro' in payload['included_sections']
    assert payload['dobro']['current']['total_minutes'] == 125
    assert payload['dobro']['transfers'][0]['hours_delta'] == 2
    assert 'PRIVATE_COORDINATOR_NOTE_NOT_FOR_EXPORT' not in json.dumps(payload)
    assert 'STRANGER_DISPLAY_NAME' not in json.dumps(payload)
