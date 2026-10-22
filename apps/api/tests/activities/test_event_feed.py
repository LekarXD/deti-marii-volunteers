from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.models import PermissionGrant,Session,User
from app.modules.activities import ranking
from app.modules.activities.assignment_models import Assignment,StaffingNeedReserve
from .test_p07 import context,headers,post_role  # noqa: F401
from .test_p09 import user_headers

RANGE='from=2028-01-01&to=2028-03-01'


async def staff_and_volunteers(context,count=2):
    async with context.db() as db:
        for permission in ('assignments.manage','schedule.manage','schedule.read'):
            db.add(PermissionGrant(membership_id=context.grants[0].membership_id,permission=permission,scope_type='foundation'))
        own=await db.scalar(select(Session).where(Session.token_hash==digest('self')))
        users=[own.user_id]
        for index in range(1,count):
            user=User(foundation_id=context.foundation.id,display_name=f'Invented volunteer {index}');db.add(user);await db.flush()
            db.add(Session(foundation_id=context.foundation.id,user_id=user.id,token_hash=digest(f'v{index}'),csrf_hash=digest(f'v{index}-csrf'),csrf_cipher='unused',expires_at=utcnow()+timedelta(hours=1)))
            users.append(user.id)
        await db.commit()
    return users


def as_user(index,key=None):
    return user_headers(key=key) if index==0 else user_headers(f'v{index}',f'v{index}-csrf',key)


async def event(context,role,title,day,capacity=2,policy='self_confirmation',start='14:00',recurrence=None):
    body={'title':title,'program':'Творческие мастерские','start_date':day,'start_time':start,'timezone':'Europe/Moscow','duration_minutes':120,'location':'Мастерская',
        'audience':'Взрослые участники','staffing_needs':[{'role_id':role['id'],'capacity_required':capacity,'approval_policy':policy}]}
    if recurrence:
        response=await context.client.post('/api/v1/coord/event-series',headers=headers(),json={**body,'recurrence':recurrence})
        assert response.status_code==200,response.text
        rows=(await context.client.get(f'/api/v1/event-occurrences?{RANGE}')).json()['items']
        return sorted([row for row in rows if row['series_id']==response.json()['id']],key=lambda row:row['starts_at'])
    response=await context.client.post('/api/v1/coord/event-occurrences',headers=headers(),json=body)
    assert response.status_code==200,response.text
    return response.json()


async def trust(context,role,index,user_id):
    """A volunteer who already took part may sign up alone."""
    past=await event(context,role,f'Знакомство {index}','2028-01-02',capacity=5,policy='coordinator',start='10:00')
    need=past['staffing_needs'][0]
    invited=(await context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/invitations",headers=headers(),json={'expected_version':need['version'],'user_id':str(user_id)})).json()
    approved=(await context.client.post(f"/api/v1/coord/assignments/{invited['id']}/approve",headers=headers(),json={'expected_version':invited['version'],'reason':'Знакомы.'})).json()
    confirmed=await context.client.post(f"/api/v1/assignments/{approved['id']}/confirm",headers=as_user(index),json={'expected_version':approved['version']})
    assert confirmed.status_code==200,confirmed.text


async def feed(context,index=0):
    response=await context.client.get(f'/api/v1/me/events?{RANGE}',headers=as_user(index))
    assert response.status_code==200,response.text
    return response.json()


@pytest.mark.asyncio
async def test_newcomer_sees_feed_but_signs_up_after_meeting(context):
    await staff_and_volunteers(context)
    role=await post_role(context)
    created=await event(context,role,'Арт-суббота','2028-01-08')
    body=await feed(context)
    assert body['can_sign_up'] is False and body['locked_reason']=='meeting_required'
    card=body['items'][0]
    assert card['title']=='Арт-суббота' and card['needs'][0]['allowed_actions']==[]
    need=created['staffing_needs'][0]
    blocked=await context.client.post(f"/api/v1/staffing-needs/{need['id']}/sign-up",headers=as_user(0),json={'expected_version':need['version']})
    assert blocked.status_code==409 and blocked.json()['code']=='meeting_required'


@pytest.mark.asyncio
async def test_sign_up_waits_for_the_coordinator_and_leaves_the_feed(context):
    users=await staff_and_volunteers(context)
    role=await post_role(context)
    await trust(context,role,0,users[0])
    created=await event(context,role,'Арт-суббота','2028-01-08',capacity=2)
    need=created['staffing_needs'][0]
    card=next(item for item in (await feed(context))['items'] if item['occurrence_id']==created['id'])
    assert card['needs'][0]['allowed_actions']==['sign-up'] and card['needs'][0]['missing']==2
    assert 'score' not in str(card) and str(users[0]) not in str(card['needs'])
    signed=await context.client.post(f"/api/v1/staffing-needs/{need['id']}/sign-up",headers=as_user(0),json={'expected_version':need['version'],'message':'Возьму краски'})
    assert signed.status_code==200,signed.text
    row=signed.json()
    # Owner's rule: a volunteer's own sign-up is a request until the coordinator accepts it.
    assert row['status']=='invited' and row['approved_at'] is None and row['origin']=='self' and [h['command'] for h in row['history']]==['sign_up']
    own_confirm=await context.client.post(f"/api/v1/assignments/{row['id']}/confirm",headers=as_user(0),json={'expected_version':row['version']})
    assert own_confirm.status_code==409 and own_confirm.json()['code']=='approval_required'
    again=await context.client.post(f"/api/v1/staffing-needs/{need['id']}/sign-up",headers=as_user(0),json={'expected_version':need['version']})
    assert again.status_code==409 and again.json()['code']=='already_signed_up'
    assert created['id'] not in [item['occurrence_id'] for item in (await feed(context))['items']]
    approved=await context.client.post(f"/api/v1/coord/assignments/{row['id']}/approve",headers=headers(),json={'expected_version':row['version'],'reason':'Ждём в субботу.'})
    assert approved.status_code==200,approved.text
    assert approved.json()['status']=='confirmed' and [h['command'] for h in approved.json()['history']]==['sign_up','approve','confirm']
    detail=(await context.client.get(f"/api/v1/me/events/{created['id']}",headers=as_user(0))).json()
    assert detail['my_assignment']['status']=='confirmed' and detail['needs'][0]['confirmed']==1 and detail['needs'][0]['allowed_actions']==[]
    staff=(await context.client.get(f"/api/v1/coord/event-occurrences/{created['id']}/staffing-needs")).json()[0]
    assert staff['confirmed']==1


@pytest.mark.asyncio
async def test_coordinator_policy_request_is_confirmed_by_approval(context):
    users=await staff_and_volunteers(context)
    role=await post_role(context)
    await trust(context,role,0,users[0])
    created=await event(context,role,'Сопровождение в дороге','2028-01-08',capacity=1,policy='coordinator')
    need=created['staffing_needs'][0]
    signed=(await context.client.post(f"/api/v1/staffing-needs/{need['id']}/sign-up",headers=as_user(0),json={'expected_version':need['version']})).json()
    assert signed['status']=='invited' and signed['approved_at'] is None and signed['origin']=='self'
    own_confirm=await context.client.post(f"/api/v1/assignments/{signed['id']}/confirm",headers=as_user(0),json={'expected_version':signed['version']})
    assert own_confirm.status_code==409 and own_confirm.json()['code']=='approval_required'
    approved=await context.client.post(f"/api/v1/coord/assignments/{signed['id']}/approve",headers=headers(),json={'expected_version':signed['version'],'reason':'Ждём у метро.'})
    assert approved.status_code==200,approved.text
    assert approved.json()['status']=='confirmed' and approved.json()['history'][-1]['command']=='confirm'


@pytest.mark.asyncio
async def test_full_role_reserve_queue_and_offer_on_cancellation(context):
    users=await staff_and_volunteers(context,4)
    role=await post_role(context)
    for index,user_id in enumerate(users):await trust(context,role,index,user_id)
    created=await event(context,role,'Арт-суббота','2028-01-08',capacity=1)
    need=created['staffing_needs'][0]
    early=await context.client.post(f"/api/v1/staffing-needs/{need['id']}/reserve",headers=as_user(1),json={'expected_version':need['version']})
    assert early.status_code==409 and early.json()['code']=='places_available'
    signed=(await context.client.post(f"/api/v1/staffing-needs/{need['id']}/sign-up",headers=as_user(0),json={'expected_version':need['version']})).json()
    first=(await context.client.post(f"/api/v1/coord/assignments/{signed['id']}/approve",headers=headers(),json={'expected_version':signed['version'],'reason':'Ждём.'})).json()
    assert first['status']=='confirmed'
    full=await context.client.post(f"/api/v1/staffing-needs/{need['id']}/sign-up",headers=as_user(1),json={'expected_version':need['version']})
    assert full.status_code==409 and full.json()['code']=='capacity_full'
    card=next(item for item in (await feed(context,1))['items'] if item['occurrence_id']==created['id'])
    assert card['full'] is True and card['needs'][0]['allowed_actions']==['reserve']
    second=(await context.client.post(f"/api/v1/staffing-needs/{need['id']}/reserve",headers=as_user(1),json={'expected_version':need['version']})).json()
    third=(await context.client.post(f"/api/v1/staffing-needs/{need['id']}/reserve",headers=as_user(2),json={'expected_version':need['version']})).json()
    assert second['position']==1 and third['position']==2 and second['state']=='waiting'
    fourth=(await context.client.post(f"/api/v1/staffing-needs/{need['id']}/reserve",headers=as_user(3),json={'expected_version':need['version']})).json()
    left=await context.client.post(f"/api/v1/reserves/{fourth['id']}/leave",headers=as_user(3),json={'expected_version':fourth['version']})
    assert left.json()['state']=='closed'
    cancelled=await context.client.post(f"/api/v1/assignments/{first['id']}/cancel",headers=as_user(0),json={'expected_version':first['version']})
    assert cancelled.status_code==200,cancelled.text
    async with context.db() as db:
        offered=await db.scalar(select(Assignment).where(Assignment.occurrence_id==created['id'],Assignment.user_id==users[1]))
        assert offered.status=='invited' and offered.origin=='reserve'
        assert (await db.scalar(select(StaffingNeedReserve).where(StaffingNeedReserve.user_id==users[2]))).state=='waiting'
        offered_id,offered_version=offered.id,offered.version
    # One free place, one outstanding offer: nobody else is invited yet.
    detail=(await context.client.get(f"/api/v1/me/events/{created['id']}",headers=as_user(1))).json()
    assert detail['my_assignment']['origin']=='reserve' and detail['my_reserve']['state']=='offered'
    declined=await context.client.post(f"/api/v1/assignments/{offered_id}/decline",headers=as_user(1),json={'expected_version':offered_version})
    assert declined.status_code==200,declined.text
    async with context.db() as db:
        assert (await db.scalar(select(StaffingNeedReserve).where(StaffingNeedReserve.user_id==users[1]))).state=='closed'
        next_offer=await db.scalar(select(Assignment).where(Assignment.occurrence_id==created['id'],Assignment.user_id==users[2]))
        assert next_offer.status=='invited' and next_offer.origin=='reserve'
        next_id,next_version=next_offer.id,next_offer.version
    confirmed=await context.client.post(f"/api/v1/assignments/{next_id}/confirm",headers=as_user(2),json={'expected_version':next_version})
    assert confirmed.status_code==200,confirmed.text
    async with context.db() as db:
        assert (await db.scalar(select(StaffingNeedReserve).where(StaffingNeedReserve.user_id==users[2]))).state=='closed'
        assert await db.scalar(select(Assignment.id).where(Assignment.occurrence_id==created['id'],Assignment.user_id==users[3])) is None


@pytest.mark.asyncio
async def test_feed_order_follows_ranking_and_hides_the_score(context,monkeypatch):
    users=await staff_and_volunteers(context)
    role=await post_role(context)
    await trust(context,role,0,users[0])
    low=await event(context,role,'Ярмарка','2028-01-08',start='11:00')
    high=await event(context,role,'Арт-суббота','2028-01-15',start='14:00')
    full=await event(context,role,'Выезд','2028-01-09',capacity=1)
    taken=full['staffing_needs'][0]
    async with context.db() as db:
        db.add(Assignment(foundation_id=context.foundation.id,user_id=users[1],occurrence_id=full['id'],staffing_need_id=taken['id'],status='confirmed',confirmed_at=utcnow(),
            conditions_version=taken['version'],conditions_snapshot={'role_version_id':str(uuid4()),'preparation_requirements':[],'approval_policy':'self_confirmation'}));await db.commit()
    scores={'Ярмарка':0.2,'Арт-суббота':0.9,'Выезд':1.0}
    async def facts(db,foundation_id,user_ids,now=None):return {user_id:SimpleNamespace(user_id=user_id) for user_id in user_ids}
    monkeypatch.setattr(ranking,'load_facts',facts)
    monkeypatch.setattr(ranking,'score_need',lambda facts,occurrence,role,now=None:SimpleNamespace(score=scores.get(occurrence.title,0),familiar_visits=0,
        reasons=[ranking.Reason('direction','Творчество'),ranking.Reason('familiar',count=7)] if occurrence.title=='Арт-суббота' else []))
    body=await feed(context)
    titles=[item['title'] for item in body['items']]
    assert titles==['Арт-суббота','Ярмарка','Выезд'],titles
    top=body['items'][0]
    assert top['reasons']==['Направление «Творчество» из твоей анкеты','7 занятий с этой группой за полгода']
    assert body['items'][-1]['full'] is True and 'score' not in str(body) and body['algorithm_version']==ranking.ALGORITHM_VERSION
    assert low['id'] and high['id']


@pytest.mark.asyncio
async def test_event_page_other_dates_and_visibility(context):
    users=await staff_and_volunteers(context)
    role=await post_role(context)
    await trust(context,role,0,users[0])
    dates=await event(context,role,'Арт-суббота','2028-01-08',recurrence={'frequency':'weekly','weekdays':[5]})
    # The feed shows a series once, at its nearest open date.
    series=[item for item in (await feed(context))['items'] if item['title']=='Арт-суббота']
    assert [item['occurrence_id'] for item in series]==[dates[0]['id']]
    detail=await context.client.get(f"/api/v1/me/events/{dates[0]['id']}",headers=as_user(0))
    assert detail.status_code==200,detail.text
    body=detail.json()
    assert len(body['other_dates'])==4 and all(row['full'] is False for row in body['other_dates'])
    assert body['other_dates'][0]['occurrence_id']==dates[1]['id']
    empty=await event(context,role,'Внутренняя встреча','2028-01-10',capacity=0)
    assert (await context.client.get(f"/api/v1/me/events/{empty['id']}",headers=as_user(0))).status_code==404
    assert (await context.client.get(f"/api/v1/me/events/{uuid4()}",headers=as_user(0))).status_code==404
