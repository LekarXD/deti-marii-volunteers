"""Coordinator events list: what waits for an answer, and «мест нет, в резерв»."""
import pytest
from sqlalchemy import delete, select
from app.core.models import PermissionGrant
from app.modules.activities.assignment_models import Assignment, AssignmentEvent, StaffingNeedReserve
from .test_p07 import context, headers, post_role  # noqa: F401
from .test_event_feed import as_user, event, staff_and_volunteers, trust


async def opportunity(context, role, title='Арт-суббота'):
    created = await context.client.post('/api/v1/coord/opportunities', headers=headers(), json={'title': title, 'role_ids': [role['id']], 'program': 'Творчество', 'task': 'Помогать на занятии',
        'audience': 'Подростки', 'location': 'Мастерская', 'schedule': 'По субботам'})
    assert created.status_code == 200, created.text
    published = await context.client.post(f"/api/v1/coord/opportunities/{created.json()['id']}/publish", headers=headers(), json={'expected_version': created.json()['version']})
    assert published.status_code == 200, published.text
    return published.json()


@pytest.mark.asyncio
async def test_summary_counts_own_sign_ups_and_open_responses(context):
    users = await staff_and_volunteers(context, 3)
    role = await post_role(context)
    for index, user_id in enumerate(users): await trust(context, role, index, user_id)
    first, second = await opportunity(context, role), await opportunity(context, role, 'Ярмарка')
    for index in range(2):
        assert (await context.client.post(f"/api/v1/opportunities/{first['id']}/responses", headers=as_user(index), json={'message': 'Хочу помочь'})).status_code == 200
    answered = (await context.client.post(f"/api/v1/opportunities/{second['id']}/responses", headers=as_user(2), json={})).json()
    assert (await context.client.post(f"/api/v1/coord/responses/{answered['id']}/decline", headers=headers(), json={'expected_version': answered['version'], 'reason': 'Набор закрыт.'})).status_code == 200
    created = await event(context, role, 'Арт-суббота', '2028-01-08', capacity=3, policy='coordinator')
    need = created['staffing_needs'][0]
    for index in range(2):
        signed = await context.client.post(f"/api/v1/staffing-needs/{need['id']}/sign-up", headers=as_user(index), json={'expected_version': need['version']})
        assert signed.status_code == 200 and signed.json()['approved_at'] is None, signed.text
    await context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/invitations", headers=headers(), json={'expected_version': need['version'], 'user_id': str(users[2])})
    summary = await context.client.get('/api/v1/coord/event-responses')
    assert summary.status_code == 200, summary.text
    assert summary.json()['sign_ups'] == [{'occurrence_id': created['id'], 'staffing_need_id': need['id'], 'count': 2}]
    assert summary.json()['responses'] == [{'opportunity_id': first['id'], 'count': 2}]
    filtered = (await context.client.get(f"/api/v1/coord/responses?opportunity_id={second['id']}")).json()['items']
    assert [item['id'] for item in filtered] == [answered['id']]
    assert (await context.client.get(f"/api/v1/coord/responses?opportunity_id={second['id']}&awaiting=true")).json()['items'] == []
    assert len((await context.client.get('/api/v1/coord/responses?awaiting=true')).json()['items']) == 2


@pytest.mark.asyncio
async def test_pending_sign_up_moves_to_reserve(context):
    users = await staff_and_volunteers(context, 3)
    role = await post_role(context)
    for index, user_id in enumerate(users): await trust(context, role, index, user_id)
    created = await event(context, role, 'Арт-суббота', '2028-01-08', capacity=1, policy='coordinator')
    need = created['staffing_needs'][0]
    signed = (await context.client.post(f"/api/v1/staffing-needs/{need['id']}/sign-up", headers=as_user(0), json={'expected_version': need['version']})).json()
    invited = (await context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/invitations", headers=headers(), json={'expected_version': need['version'], 'user_id': str(users[1])})).json()
    taken = await context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/reserve", headers=headers(), json={'expected_version': need['version'], 'user_id': str(users[1])})
    assert taken.status_code == 409 and taken.json()['code'] == 'already_in_team'
    moved = await context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/reserve", headers=headers(), json={'expected_version': need['version'], 'user_id': str(users[0]), 'expected_assignment_version': signed['version']})
    assert moved.status_code == 200, moved.text
    assert moved.json()['state'] == 'waiting' and moved.json()['position'] == 1 and moved.json()['role_title'] == role['title']
    again = await context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/reserve", headers=headers(), json={'expected_version': need['version'], 'user_id': str(users[0])})
    assert again.status_code == 409 and again.json()['code'] == 'already_in_reserve'
    queued = await context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/reserve", headers=headers(), json={'expected_version': need['version'], 'user_id': str(users[2])})
    assert queued.status_code == 200 and queued.json()['position'] == 2
    listed = (await context.client.get(f"/api/v1/coord/event-occurrences/{created['id']}/reserve")).json()
    assert [(row['user_id'], row['position']) for row in listed] == [(str(users[0]), 1), (str(users[2]), 2)]
    assert (await context.client.get('/api/v1/coord/event-responses')).json()['sign_ups'] == []
    async with context.db() as db:
        row = await db.get(Assignment, signed['id'])
        assert row.status == 'cancelled'
        assert (await db.scalars(select(AssignmentEvent.command).where(AssignmentEvent.assignment_id == row.id).order_by(AssignmentEvent.version))).all()[-1] == 'to_reserve'
    # A freed place becomes an invitation for the first in the queue.
    cancelled = await context.client.post(f"/api/v1/coord/assignments/{invited['id']}/cancel", headers=headers(), json={'expected_version': invited['version'], 'reason': 'Заболел.'})
    assert cancelled.status_code == 200, cancelled.text
    async with context.db() as db:
        offered = await db.scalar(select(Assignment).where(Assignment.occurrence_id == created['id'], Assignment.user_id == users[0]))
        assert offered.status == 'invited' and offered.origin == 'reserve'
        assert (await db.scalar(select(StaffingNeedReserve).where(StaffingNeedReserve.user_id == users[0]))).state == 'offered'


@pytest.mark.asyncio
async def test_reserve_and_summary_need_assignment_rights(context):
    users = await staff_and_volunteers(context, 1)
    role = await post_role(context)
    created = await event(context, role, 'Арт-суббота', '2028-01-08', capacity=1)
    need = created['staffing_needs'][0]
    async with context.db() as db:
        await db.execute(delete(PermissionGrant).where(PermissionGrant.permission == 'assignments.manage'));await db.commit()
    assert (await context.client.get('/api/v1/coord/event-responses')).status_code == 403
    assert (await context.client.get(f"/api/v1/coord/event-occurrences/{created['id']}/reserve")).status_code == 403
    denied = await context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/reserve", headers=headers(), json={'expected_version': need['version'], 'user_id': str(users[0])})
    assert denied.status_code == 403
