import asyncio
from datetime import date,timedelta
from uuid import UUID,uuid4
import pytest
from sqlalchemy import func,select,update
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.models import AuditEvent,MutationReceipt,PermissionGrant,ResourceReservation,Session,User
from app.modules.activities.assignment_models import Assignment,AssignmentEvent,Attendance,AttendanceEvent
from app.modules.activities.calendar_models import EventOccurrence
from app.modules.participants.models import GroupMembership,Participant,ParticipantGroup
from app.modules.profile.models import ServiceTimeEntry,VolunteerProfile
from .test_p07 import context,headers,post_role


def user_headers(token='self',csrf='self-csrf',key=None):return {'Cookie':f'opora_session={token}','Origin':'http://testserver','X-CSRF-Token':csrf,'Idempotency-Key':key or str(uuid4())}


async def setup(context,mandatory=False,group=False,capacity=1):
    async with context.db() as db:
        for permission in ('assignments.manage','schedule.manage','schedule.read'):
            db.add(PermissionGrant(membership_id=context.grants[0].membership_id,permission=permission,scope_type='foundation'))
        other=User(foundation_id=context.foundation.id,display_name='Invented second volunteer');db.add(other);await db.flush()
        db.add(Session(foundation_id=context.foundation.id,user_id=other.id,token_hash=digest('second'),csrf_hash=digest('second-csrf'),csrf_cipher='unused',expires_at=utcnow()+timedelta(hours=1)))
        own_session=await db.scalar(select(Session).where(Session.token_hash==digest('self')))
        first_id=own_session.user_id
        group_row=None;participant=None
        if group:
            group_row=ParticipantGroup(foundation_id=context.foundation.id,title='Группа назначения');db.add(group_row);await db.flush()
            participant=Participant(foundation_id=context.foundation.id,display_name='Invented participant');db.add(participant);await db.flush()
            db.add(GroupMembership(foundation_id=context.foundation.id,group_id=group_row.id,participant_id=participant.id,valid_from=date(2020,1,1)))
        await db.commit()
    role=await post_role(context)
    requirements=[{'key':'discussion','title':'Разобрать договорённости','level':'mandatory'},{'key':'optional','title':'Посмотреть материалы','level':'recommended'}] if mandatory else []
    created=await context.client.post('/api/v1/coord/event-occurrences',headers=headers(),json={'title':'Рабочая встреча','start_date':'2028-01-03','start_time':'14:00','timezone':'Europe/Moscow','duration_minutes':120,'location':'Мастерская','group_id':str(group_row.id) if group_row else None,'staffing_needs':[{'role_id':role['id'],'capacity_required':capacity,'preparation_requirements':requirements}]})
    assert created.status_code==200,created.text
    event=created.json();need=event['staffing_needs'][0]
    return event,need,first_id,other.id,participant


async def invite_approve(context,need,user_id):
    invited=await context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/invitations",headers=headers(),json={'expected_version':need['version'],'user_id':str(user_id)})
    assert invited.status_code==200,invited.text
    row=invited.json()
    approved=await context.client.post(f"/api/v1/coord/assignments/{row['id']}/approve",headers=headers(),json={'expected_version':row['version'],'reason':'Обсудили условия участия.'})
    assert approved.status_code==200,approved.text
    return approved.json()


@pytest.mark.asyncio
async def test_two_volunteers_last_place_race_and_separate_approval(context):
    event,need,user1,user2,_=await setup(context)
    invited=await context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/invitations",headers=headers(),json={'expected_version':1,'user_id':str(user1)})
    row=invited.json()
    blocked=await context.client.post(f"/api/v1/assignments/{row['id']}/confirm",headers=user_headers(),json={'expected_version':1})
    assert blocked.status_code==409 and blocked.json()['code']=='approval_required'
    assert (await context.client.post(f"/api/v1/coord/assignments/{row['id']}/approve",headers=user_headers(),json={'expected_version':1,'reason':'Self approval'})).status_code==403
    approved=await context.client.post(f"/api/v1/coord/assignments/{row['id']}/approve",headers=headers(),json={'expected_version':1,'reason':'Согласовано.'})
    first=approved.json();second=await invite_approve(context,need,user2)
    results=await asyncio.gather(context.client.post(f"/api/v1/assignments/{first['id']}/confirm",headers=user_headers(),json={'expected_version':2}),context.client.post(f"/api/v1/assignments/{second['id']}/confirm",headers=user_headers('second','second-csrf'),json={'expected_version':2}))
    assert sorted(r.status_code for r in results)==[200,409],[r.text for r in results]
    counts=(await context.client.get(f"/api/v1/coord/event-occurrences/{event['id']}/staffing-needs")).json()[0]
    assert counts['required']==1 and counts['confirmed']==1 and counts['invited']==1
    async with context.db() as db:
        assert await db.scalar(select(func.count()).select_from(ResourceReservation).where(ResourceReservation.active.is_(True)))==1
        assert await db.scalar(select(func.count()).select_from(Assignment).where(Assignment.status=='confirmed'))==1


@pytest.mark.asyncio
async def test_configurable_requirements_historical_snapshot_and_cancellation(context):
    event,need,user1,user2,participant=await setup(context,mandatory=True,group=True)
    item=await invite_approve(context,need,user1)
    blocked=await context.client.post(f"/api/v1/assignments/{item['id']}/confirm",headers=user_headers(),json={'expected_version':item['version']})
    assert blocked.status_code==409 and blocked.json()['code']=='preparation_pending'
    reviewed=await context.client.post(f"/api/v1/coord/assignments/{item['id']}/requirements",headers=headers(),json={'expected_version':item['version'],'requirement_key':'discussion','state':'fulfilled','reason':'Провели встречу и разобрали задачу.'})
    assert reviewed.status_code==200,reviewed.text
    confirmed=await context.client.post(f"/api/v1/assignments/{item['id']}/confirm",headers=user_headers(),json={'expected_version':reviewed.json()['version']})
    assert confirmed.status_code==200,confirmed.text
    assert confirmed.json()['readiness'][1]['state']=='pending' # recommended does not block
    safe=await context.client.get(f"/api/v1/me/assignments/{item['id']}/participants",headers={'Cookie':'opora_session=self'})
    assert safe.status_code==200,safe.text
    assert [r['id'] for r in safe.json()['items']]==[str(participant.id)]
    async with context.db() as db:
        late=Participant(foundation_id=context.foundation.id,display_name='Added after confirmation');db.add(late);await db.flush()
        db.add(GroupMembership(foundation_id=context.foundation.id,group_id=event['group_id'],participant_id=late.id,valid_from=date(2020,1,1)));await db.commit()
    safe=await context.client.get(f"/api/v1/me/assignments/{item['id']}/participants",headers={'Cookie':'opora_session=self'})
    assert [r['id'] for r in safe.json()['items']]==[str(participant.id)]
    # A confirmed team cannot silently move while its shared reservation stays at the old time.
    moved=await context.client.patch(f"/api/v1/coord/event-occurrences/{event['id']}",headers=headers(),json={'expected_version':event['version'],'title':'Другое время','group_id':event['group_id'],'starts_at':'2028-01-03T12:00:00Z','ends_at':'2028-01-03T14:00:00Z','location':'Мастерская'})
    assert moved.status_code==409 and moved.json()['code']=='reconfirmation_required'
    cancelled=await context.client.post(f"/api/v1/coord/event-occurrences/{event['id']}/cancel",headers=headers(),json={'expected_version':event['version']})
    assert cancelled.status_code==200,cancelled.text
    assert (await context.client.get(f"/api/v1/me/assignments/{item['id']}/participants",headers={'Cookie':'opora_session=self'})).status_code==403
    assert (await context.client.get(f"/api/v1/me/assignments/{item['id']}/participants/{participant.id}/photo",headers={'Cookie':'opora_session=self'})).status_code==403
    async with context.db() as db:
        assert await db.scalar(select(func.count()).select_from(ResourceReservation).where(ResourceReservation.active.is_(True)))==0
        assert (await db.get(Assignment,UUID(item['id']))).status=='cancelled'


@pytest.mark.asyncio
async def test_global_interview_overlap_rolls_back_and_revocation_closes_briefing(context):
    event,need,user1,user2,_=await setup(context,group=True)
    item=await invite_approve(context,need,user1)
    async with context.db() as db:
        reservation=ResourceReservation(foundation_id=context.foundation.id,user_id=user1,owner_key=f'user:{user1}',source_type='interview',source_id=uuid4(),starts_at=utcnow().replace(year=2028,month=1,day=3,hour=11,minute=30,second=0,microsecond=0),busy_until=utcnow().replace(year=2028,month=1,day=3,hour=12,minute=30,second=0,microsecond=0),active=True)
        db.add(reservation);await db.commit()
    blocked=await context.client.post(f"/api/v1/assignments/{item['id']}/confirm",headers=user_headers(),json={'expected_version':item['version']})
    assert blocked.status_code==409 and blocked.json()['code']=='participation_overlap',blocked.text
    async with context.db() as db:
        unchanged=await db.get(Assignment,UUID(item['id']));assert unchanged.status=='invited' and unchanged.version==item['version']
        stored=await db.get(ResourceReservation,reservation.id);stored.active=False;await db.commit()
    confirmed=await context.client.post(f"/api/v1/assignments/{item['id']}/confirm",headers=user_headers(),json={'expected_version':item['version']})
    assert confirmed.status_code==200,confirmed.text
    async with context.db() as db:
        user=await db.get(User,user1);user.account_state='paused';await db.commit()
    assert (await context.client.get(f"/api/v1/me/assignments/{item['id']}/participants",headers={'Cookie':'opora_session=self'})).status_code==401


@pytest.mark.asyncio
async def test_attendance_idempotency_correction_and_absence_zero(context):
    event,need,user1,user2,_=await setup(context)
    item=await invite_approve(context,need,user1)
    confirmed=await context.client.post(f"/api/v1/assignments/{item['id']}/confirm",headers=user_headers(),json={'expected_version':item['version']})
    item=confirmed.json()
    body={'expected_version':item['version'],'outcome':'attended','minutes':120,'reason':'Участвовал в занятии.'}
    future=await context.client.post(f"/api/v1/coord/assignments/{item['id']}/attendance",headers=headers(),json=body)
    assert future.status_code==409
    async with context.db() as db:
        event_row=await db.get(EventOccurrence,UUID(event['id']));event_row.starts_at=utcnow()-timedelta(hours=3);event_row.ends_at=utcnow()-timedelta(hours=1);await db.commit()
    key=str(uuid4())
    one,two=await asyncio.gather(*[context.client.post(f"/api/v1/coord/assignments/{item['id']}/attendance",headers=headers(key),json=body) for _ in range(2)])
    assert one.status_code==two.status_code==200,one.text
    assert one.json()['attendance']['id']==two.json()['attendance']['id']
    invalid=await context.client.post(f"/api/v1/coord/assignments/{item['id']}/attendance/correct",headers=headers(),json={'expected_version':one.json()['version'],'outcome':'absent','minutes':30,'reason':'Wrong'})
    assert invalid.status_code==422
    correction=await context.client.post(f"/api/v1/coord/assignments/{item['id']}/attendance/correct",headers=headers(),json={'expected_version':one.json()['version'],'outcome':'absent','minutes':0,'reason':'Исправлена ошибочная отметка.'})
    assert correction.status_code==200,correction.text
    assert correction.json()['attendance']['minutes']==0 and correction.json()['attendance']['ledger_state']=='posted'
    async with context.db() as db:
        events=(await db.scalars(select(AttendanceEvent).order_by(AttendanceEvent.version))).all()
        assert [(r.old_minutes,r.new_minutes) for r in events]==[(0,120),(120,0)]
        assert all(event.ledger_state=='posted' for event in events)
        entries=(await db.scalars(select(ServiceTimeEntry).order_by(ServiceTimeEntry.source_revision))).all()
        assert [entry.delta_minutes for entry in entries]==[120,-120]
        assert {entry.attendance_event_id for entry in entries}=={event.id for event in events}
        assert await db.scalar(select(func.count()).select_from(Attendance))==1


@pytest.mark.asyncio
async def test_response_review_withdraw_resubmit_and_owner_boundaries(context):
    event,need,user1,user2,_=await setup(context)
    role=await post_role(context,'Ещё одна роль')
    created=await context.client.post('/api/v1/coord/opportunities',headers=headers(),json={'title':'Направление','role_ids':[role['id']],'program':'Мастерская','audience':'Взрослые','task':'Помогать ведущей','location':'Мастерская','schedule':'Суббота'})
    item=created.json()
    path=f"/api/v1/opportunities/{item['id']}/responses"
    assert (await context.client.post(path,headers=user_headers(),json={'message':'Готов обсудить.'})).status_code==404
    assert (await context.client.post(f"/api/v1/coord/opportunities/{item['id']}/publish",headers=headers(),json={'expected_version':1})).status_code==200
    key=str(uuid4());one=await context.client.post(path,headers=user_headers(key=key),json={'message':'Готов обсудить.'});two=await context.client.post(path,headers=user_headers(key=key),json={'message':'Готов обсудить.'})
    assert one.status_code==two.status_code==200 and one.json()['id']==two.json()['id']
    response=one.json()
    bad=await context.client.post(f"/api/v1/coord/responses/{response['id']}/approve",headers=user_headers(),json={'expected_version':1,'reason':'Сам согласовал.'})
    assert bad.status_code==403
    approved=await context.client.post(f"/api/v1/coord/responses/{response['id']}/approve",headers=headers(),json={'expected_version':1,'reason':'Обсудили первое знакомство.'})
    assert approved.status_code==200,approved.text
    visible=(await context.client.get(f"/api/v1/me/responses?opportunity_id={item['id']}",headers={'Cookie':'opora_session=self'})).json()['items'][0]
    assert visible['state']=='approved' and visible['history'][-1]['reason']=='Обсудили первое знакомство.'
    withdrawn=await context.client.post(f"/api/v1/responses/{response['id']}/withdraw",headers=user_headers(),json={'expected_version':2})
    assert withdrawn.status_code==200
    other=await context.client.post(f"/api/v1/responses/{response['id']}/resubmit",headers=user_headers('second','second-csrf'),json={'expected_version':3})
    assert other.status_code==404
    again=await context.client.post(f"/api/v1/responses/{response['id']}/resubmit",headers=user_headers(),json={'expected_version':3})
    assert again.status_code==200 and again.json()['state']=='submitted' and len(again.json()['history'])==4


@pytest.mark.asyncio
async def test_ongoing_activity_never_exposes_or_accepts_attendance(context):
    event,need,user1,user2,_=await setup(context)
    item=await invite_approve(context,need,user1)
    confirmed=await context.client.post(f"/api/v1/assignments/{item['id']}/confirm",headers=user_headers(),json={'expected_version':item['version']})
    item=confirmed.json()
    async with context.db() as db:
        event_row=await db.get(EventOccurrence,UUID(event['id']))
        event_row.starts_at=utcnow()-timedelta(minutes=1)
        event_row.ends_at=utcnow()+timedelta(hours=1)
        await db.commit()
    async with context.db() as db:
        receipts_before=await db.scalar(select(func.count()).select_from(MutationReceipt))
        audit_before=await db.scalar(select(func.count()).select_from(AuditEvent))
    view=(await context.client.get(f"/api/v1/assignments/{item['id']}")).json()
    assert 'attendance' not in view['allowed_actions'] and 'correct-attendance' not in view['allowed_actions']
    denied=await context.client.post(f"/api/v1/coord/assignments/{item['id']}/attendance",headers=headers(),json={'expected_version':item['version'],'outcome':'attended','minutes':60,'reason':'Ещё идёт занятие.'})
    assert denied.status_code==409 and denied.json()['code']=='attendance_not_finished'
    async with context.db() as db:
        assert await db.scalar(select(func.count()).select_from(Attendance))==0
        assert await db.scalar(select(func.count()).select_from(AttendanceEvent))==0
        assert await db.scalar(select(func.count()).select_from(MutationReceipt))==receipts_before
        assert await db.scalar(select(func.count()).select_from(AuditEvent))==audit_before
        assert (await db.get(Assignment,UUID(item['id']))).version==item['version']
        event_row=await db.get(EventOccurrence,UUID(event['id']))
        event_row.ends_at=utcnow()-timedelta(microseconds=1)
        await db.commit()
    allowed=await context.client.post(f"/api/v1/coord/assignments/{item['id']}/attendance",headers=headers(),json={'expected_version':item['version'],'outcome':'attended','minutes':1,'reason':'Занятие завершилось.'})
    assert allowed.status_code==200,allowed.text
    async with context.db() as db:
        assert await db.scalar(select(func.count()).select_from(Attendance))==1
        assert await db.scalar(select(func.count()).select_from(AttendanceEvent))==1


@pytest.mark.asyncio
async def test_attendance_fact_prevents_cancellation_and_keeps_correction_available(context):
    event,need,user1,user2,_=await setup(context)
    item=await invite_approve(context,need,user1)
    confirmed=await context.client.post(f"/api/v1/assignments/{item['id']}/confirm",headers=user_headers(),json={'expected_version':item['version']})
    item=confirmed.json()
    async with context.db() as db:
        event_row=await db.get(EventOccurrence,UUID(event['id']))
        event_row.starts_at=utcnow()-timedelta(hours=3);event_row.ends_at=utcnow()-timedelta(hours=1)
        await db.commit()
    recorded=await context.client.post(f"/api/v1/coord/assignments/{item['id']}/attendance",headers=headers(),json={'expected_version':item['version'],'outcome':'attended','minutes':120,'reason':'Участие отмечено после занятия.'})
    assert recorded.status_code==200,recorded.text
    item=recorded.json()
    assert 'cancel' not in item['allowed_actions'] and 'correct-attendance' in item['allowed_actions']
    for path,request_headers,body in [(f"/api/v1/assignments/{item['id']}/cancel",user_headers(),{'expected_version':item['version']}),(f"/api/v1/coord/assignments/{item['id']}/cancel",headers(),{'expected_version':item['version'],'reason':'Поздняя отмена'}),(f"/api/v1/coord/event-occurrences/{event['id']}/cancel",headers(),{'expected_version':event['version']})]:
        denied=await context.client.post(path,headers=request_headers,json=body)
        assert denied.status_code==409 and denied.json()['code']=='attendance_already_recorded',denied.text
    corrected=await context.client.post(f"/api/v1/coord/assignments/{item['id']}/attendance/correct",headers=headers(),json={'expected_version':item['version'],'outcome':'attended','minutes':90,'reason':'Уточнена фактическая длительность.'})
    assert corrected.status_code==200,corrected.text
    async with context.db() as db:
        assert (await db.get(Assignment,UUID(item['id']))).status=='confirmed'
        assert (await db.get(EventOccurrence,UUID(event['id']))).status=='scheduled'
        facts=(await db.scalars(select(AttendanceEvent).order_by(AttendanceEvent.version))).all()
        assert [(row.old_minutes,row.new_minutes) for row in facts]==[(0,120),(120,90)]


@pytest.mark.asyncio
async def test_profile_pause_is_checked_for_new_invites_and_confirmation(context):
    event,need,user1,user2,_=await setup(context)
    item=await invite_approve(context,need,user1)
    async with context.db() as db:
        db.add_all([VolunteerProfile(user_id=user_id,foundation_id=context.foundation.id,lifecycle='paused',paused_until=date(2029,1,1)) for user_id in (user1,user2)])
        await db.commit()
    denied_invite=await context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/invitations",headers=headers(),json={'expected_version':need['version'],'user_id':str(user2)})
    assert denied_invite.status_code==409 and denied_invite.json()['code']=='volunteer_paused'
    denied_confirm=await context.client.post(f"/api/v1/assignments/{item['id']}/confirm",headers=user_headers(),json={'expected_version':item['version']})
    assert denied_confirm.status_code==409 and denied_confirm.json()['code']=='volunteer_paused'
    async with context.db() as db:
        profile=await db.get(VolunteerProfile,user1);profile.paused_until=utcnow().date()-timedelta(days=1)
        await db.commit()
    allowed=await context.client.post(f"/api/v1/assignments/{item['id']}/confirm",headers=user_headers(),json={'expected_version':item['version']})
    assert allowed.status_code==200,allowed.text
    async with context.db() as db:
        profile=await db.get(VolunteerProfile,user1);profile.paused_until=date(2029,1,1)
        await db.commit()
        assert (await db.get(Assignment,UUID(item['id']))).status=='confirmed'
