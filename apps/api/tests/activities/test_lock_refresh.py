"""Real PostgreSQL stale-read races: a waiting command must recheck committed CAS."""
import asyncio
from uuid import UUID
import pytest
from sqlalchemy import select, text
from app.modules.activities import assignment_service, calendar_service
from app.modules.activities.assignment_models import Assignment, AssignmentEvent
from app.modules.activities.assignment_schemas import ParticipationDecision
from app.modules.activities.calendar_models import EventOccurrence, EventSeries, EventRevision
from app.modules.activities.schemas import VersionCommand
from app.core.auth import authz_guard
from app.modules.activities.calendar_schemas import StaffingNeedsUpdate
from .test_p07 import context, headers
from .test_p08 import seed
from .test_p09 import setup

async def wait_for_row_lock(db, pending):
    # Observe PostgreSQL's actual lock wait; elapsed time alone is not evidence.
    for _ in range(300):
        if pending.done():
            await pending
            pytest.fail('Request returned before reaching the held row lock')
        waiting = await db.scalar(text("""SELECT EXISTS (
            SELECT 1 FROM pg_locks WHERE NOT granted
            AND pg_backend_pid() = ANY(pg_blocking_pids(pid)))"""))
        if waiting: return
        await asyncio.sleep(.01)
    pytest.fail('Request did not reach its domain row lock')

@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['occurrence', 'series'])
async def test_waiting_calendar_command_rejects_committed_version(context, kind):
    created, _ = await seed(context, frequency='once')
    event = (await context.client.get('/api/v1/event-occurrences?from=2028-01-01&to=2028-01-31')).json()['items'][0]
    model = EventOccurrence if kind == 'occurrence' else EventSeries
    identity = UUID(event['id'] if kind == 'occurrence' else created['id'])
    route = f'/api/v1/coord/event-{"occurrences" if kind == "occurrence" else "series"}/{identity}/cancel'
    pending = None
    try:
        async with context.db() as held:
            await held.scalar(select(model).where(model.id == identity).with_for_update())
            pending = asyncio.create_task(context.client.post(route, json={'expected_version': 1}, headers=headers()))
            await wait_for_row_lock(held, pending)
            command = VersionCommand(expected_version=1)
            if kind == 'occurrence': await calendar_service.change_occurrence_state(held, context.principal, identity, command, 'cancelled')
            else: await calendar_service.change_series_state(held, context.principal, identity, command, 'cancelled')
            await held.commit()
        result = await asyncio.wait_for(pending, 5)
        assert result.status_code == 409, result.text
        assert result.json()['code'] == 'version_conflict'
        async with context.db() as db:
            assert (await db.get(model, identity)).version == 2
            revisions = (await db.scalars(select(EventRevision).where(EventRevision.entity_id == identity).order_by(EventRevision.version))).all()
            assert [revision.version for revision in revisions] == ([2] if kind == 'occurrence' else [1, 2])
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

@pytest.mark.asyncio
async def test_waiting_assignment_approval_rejects_committed_version(context):
    event, need, first_user, _, _ = await setup(context)
    response = await context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/invitations", headers=headers(), json={'expected_version': need['version'], 'user_id': str(first_user)})
    assert response.status_code == 200, response.text
    identity = UUID(response.json()['id'])
    async with context.db() as db:
        await authz_guard(db, context.principal)
        await db.commit()
    pending = None
    try:
        async with context.db() as held:
            await held.scalar(select(EventOccurrence).where(EventOccurrence.id == UUID(event['id'])).with_for_update())
            pending = asyncio.create_task(context.client.post(f'/api/v1/coord/assignments/{identity}/approve', headers=headers(), json={'expected_version': 1, 'reason': 'Устаревшая команда'}))
            await wait_for_row_lock(held, pending)
            await assignment_service.approve(held, context.principal, identity, ParticipationDecision(expected_version=1, reason='Первое согласование'))
            await held.commit()
        result = await asyncio.wait_for(pending, 5)
        assert result.status_code == 409, result.text
        assert result.json()['code'] == 'version_conflict'
        async with context.db() as db:
            assert (await db.get(Assignment, identity)).version == 2
            history = (await db.scalars(select(AssignmentEvent).where(AssignmentEvent.assignment_id == identity).order_by(AssignmentEvent.version))).all()
            assert [(entry.version, entry.command) for entry in history] == [(1, 'invite'), (2, 'approve')]
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

@pytest.mark.asyncio
async def test_waiting_invitation_rechecks_changed_need(context):
    event, need, first_user, _, _ = await setup(context)
    async with context.db() as db:
        await authz_guard(db, context.principal)
        await db.commit()
    pending = None
    try:
        async with context.db() as held:
            await held.scalar(select(EventOccurrence).where(EventOccurrence.id == UUID(event['id'])).with_for_update())
            pending = asyncio.create_task(context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/invitations", headers=headers(), json={'expected_version': 1, 'user_id': str(first_user)}))
            await wait_for_row_lock(held, pending)
            command = StaffingNeedsUpdate(expected_version=1, staffing_needs=[{'role_id': need['role_id'], 'capacity_required': 0}])
            await calendar_service.patch_staffing(held, context.principal, UUID(event['id']), command)
            await held.commit()
        result = await asyncio.wait_for(pending, 5)
        assert result.status_code == 409, result.text
        assert result.json()['code'] == 'version_conflict'
        async with context.db() as db:
            assert not (await db.scalars(select(Assignment).where(Assignment.occurrence_id == UUID(event['id'])))).all()
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
