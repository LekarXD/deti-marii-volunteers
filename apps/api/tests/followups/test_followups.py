from datetime import datetime,timedelta
from uuid import UUID,uuid4
import pytest
import pytest_asyncio
from sqlalchemy import func,select
from app.core.auth import resolve_principal
from app.core.clock import utcnow
from app.core.models import PermissionGrant,Session,StaffMembership
from app.modules.activities.assignment_models import Attendance,AttendanceEvent
from app.modules.crm.models import CrmVolunteer,FollowUpTask
from app.modules.crm.service import ensure_user_volunteer
from app.modules.followups import service
from app.modules.followups.models import Reflection,ReflectionReviewNote,SupportSignal
from app.modules.followups.router import router
from participants.test_assignment_access import assigned
from participants.test_participants import env,mutate

@pytest_asyncio.fixture
async def prepared(assigned,monkeypatch):
    x=assigned
    x.first._transport.app.include_router(router)
    async with x.sessions() as db:
        for name in ('admin','leader'):
            member=await db.scalar(select(StaffMembership).where(StaffMembership.user_id==x.users[name]))
            for permission in ('followups.read','followups.manage'):
                db.add(PermissionGrant(membership_id=member.id,permission=permission))
            if name=='leader':
                for permission in ('signals.restricted','followups.private_notes'):db.add(PermissionGrant(membership_id=member.id,permission=permission))
        await db.commit()
    x.confirmed=await x.confirm(x.first,x.assignment_a)
    future_end=datetime.fromisoformat(x.event_a['ends_at'].replace('Z','+00:00'))
    monkeypatch.setattr(service,'utcnow',lambda:future_end+timedelta(minutes=1))
    x.root=f"/api/v1/me/assignments/{x.confirmed['id']}"
    x.specialist=x.second
    yield x

async def save_submit(x,restricted=False,key=None):
    draft=await mutate(x.first,x.root+'/reflection',{'expected_version':0,'mood':'hard','text':'Сложно вести занятие','unexpected':'Усталость в конце','help':'yes','help_text':'Хочу обсудить поддержку','continuation':'discuss','restricted':restricted},'PUT')
    assert draft.status_code==200,draft.text
    submitted=await mutate(x.first,x.root+'/reflection/submit',{'expected_version':draft.json()['version']},key=key)
    return draft,submitted

@pytest.mark.asyncio
async def test_checklist_and_question_reach_staff_with_public_answer(prepared):
    x=prepared
    prep=await x.first.get(x.root+'/preparation');assert prep.status_code==200,prep.text
    assert prep.json()['tasks']=='Поддержать участников'
    body={'expected_version':0,'checklist_version':1,'checked_keys':['group','clothes']};key=str(uuid4())
    one=await mutate(x.first,x.root+'/checklist',body,'PUT',key)
    two=await mutate(x.first,x.root+'/checklist',body,'PUT',key)
    assert one.status_code==two.status_code==200 and one.json()['version']==two.json()['version']==1
    assert sum(item['checked'] for item in two.json()['checklist'])==2
    assert (await x.second.get(x.root+'/preparation')).status_code==404
    invalid=await mutate(x.first,x.root+'/checklist',{'expected_version':1,'checked_keys':['invented']},'PUT');assert invalid.status_code==422
    asked=await mutate(x.first,x.root+'/questions',{'text':'Где встречаемся перед входом?'});assert asked.status_code==200,asked.text
    signals=(await x.admin.get('/api/v1/coord/signals')).json()['items']
    assert len(signals)==1 and signals[0]['question_id']==asked.json()['id'] and signals[0]['follow_up_task_id']
    answer=await mutate(x.admin,f"/api/v1/coord/assignment-questions/{asked.json()['id']}/answer",{'expected_version':1,'public_answer':'У главного входа за 15 минут.'})
    assert answer.status_code==200,answer.text
    own=(await x.first.get(x.root+'/preparation')).json()['questions'][0]
    assert own['public_answer']=='У главного входа за 15 минут.'
    async with x.sessions() as db:
        task=await db.get(FollowUpTask,UUID(signals[0]['follow_up_task_id']));assert task.state=='done'

@pytest.mark.asyncio
async def test_voluntary_help_review_public_decision_private_note_and_signal_history(prepared):
    x=prepared;key=str(uuid4())
    draft,submitted=await save_submit(x,key=key);assert submitted.status_code==200,submitted.text
    data=submitted.json();assert data['follow_up_registered'] is True
    retry=await mutate(x.first,x.root+'/reflection/submit',{'expected_version':draft.json()['version']},key=key)
    assert retry.status_code==200 and retry.json()['id']==data['id']
    async with x.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(FollowUpTask).where(FollowUpTask.state=='open'))==1
    review={'expected_version':data['version'],'decision':'next_date','public_message':'Обсудим следующую встречу.','assigned_user_id':str(x.users['admin']),'next_date':'2028-01-12','internal_note':'INTERNAL SUPERVISION ONLY'}
    assert (await mutate(x.admin,f"/api/v1/coord/reflections/{data['id']}/review",review)).status_code==403
    accepted=await mutate(x.specialist,f"/api/v1/coord/reflections/{data['id']}/review",review);assert accepted.status_code==200,accepted.text
    own=await x.first.get(x.root+'/reflection');assert 'INTERNAL' not in own.text and 'internal_note' not in own.text
    assert own.json()['review']['decision']=='next_date' and own.json()['review']['next_date']=='2028-01-12'
    async with x.sessions() as db:
        session=await db.scalar(select(Session).where(Session.user_id==x.users['admin']))
        projection=await service.latest_reflection_for_user(db,x.foundation,x.users['volunteer'],await resolve_principal(db,session))
        assert str(projection['id'])==data['id'] and projection['can_review'] is True
        assert projection['review']['decision']=='next_date' and projection['review']['next_date']=='2028-01-12'
        assert 'INTERNAL' not in str(projection) and 'internal_note' not in projection
    assert (await x.admin.get(f"/api/v1/coord/reflections/{data['id']}/private-notes")).status_code==403
    private=await x.specialist.get(f"/api/v1/coord/reflections/{data['id']}/private-notes");assert private.status_code==200 and private.json()[0]['text']=='INTERNAL SUPERVISION ONLY'
    row=(await x.admin.get('/api/v1/coord/signals')).json()['items'][0]
    resolved=await mutate(x.admin,f"/api/v1/coord/signals/{row['id']}/resolve",{'expected_version':row['version'],'reason':'Обсудили следующий шаг.'});assert resolved.status_code==200,resolved.text
    reopened=await mutate(x.admin,f"/api/v1/coord/signals/{row['id']}/reopen",{'expected_version':resolved.json()['version'],'reason':'Появился дополнительный вопрос.'});assert reopened.status_code==200,reopened.text
    assert [event['action'] for event in reopened.json()['history']]==['created','reviewed','resolve','reopen']
    async with x.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(FollowUpTask).where(FollowUpTask.state=='open'))==1
        assert await db.scalar(select(func.count()).select_from(ReflectionReviewNote))==1

@pytest.mark.asyncio
async def test_restricted_case_and_cached_review_receipt_revoke_are_private(prepared):
    x=prepared;_,submitted=await save_submit(x,True);assert submitted.status_code==200,submitted.text
    data=submitted.json()
    assert (await x.admin.get('/api/v1/coord/reflections')).json()['items']==[]
    assert (await x.admin.get('/api/v1/coord/signals')).json()['items']==[]
    assert (await x.admin.get(f"/api/v1/coord/reflections/{data['id']}")).status_code==404
    special=(await x.specialist.get('/api/v1/coord/signals')).json()['items'][0]
    key=str(uuid4());review={'expected_version':data['version'],'decision':'discussion','public_message':'Согласуем удобное время.','next_date':'2028-01-10','assigned_user_id':str(x.users['leader'])}
    accepted=await mutate(x.specialist,f"/api/v1/coord/reflections/{data['id']}/review",review,key=key);assert accepted.status_code==200,accepted.text
    async with x.sessions() as db:
        admin_session=await db.scalar(select(Session).where(Session.user_id==x.users['admin']))
        assert await service.latest_reflection_for_user(db,x.foundation,x.users['volunteer'],await resolve_principal(db,admin_session)) is None
        assert await service.latest_reflection_for_user(db,x.foundation,x.users['volunteer']) is None
        membership=await db.scalar(select(StaffMembership).where(StaffMembership.user_id==x.users['leader']))
        grant=await db.scalar(select(PermissionGrant).where(PermissionGrant.membership_id==membership.id,PermissionGrant.permission=='signals.restricted'))
        grant.revoked_at=utcnow();await db.commit()
    assert (await x.specialist.get(f"/api/v1/coord/signals/{special['id']}")).status_code==404
    replay=await mutate(x.specialist,f"/api/v1/coord/reflections/{data['id']}/review",review,key=key)
    assert replay.status_code==404 and 'Сложно' not in replay.text

@pytest.mark.asyncio
async def test_missing_specialist_keeps_draft_and_audio_is_truthfully_unavailable(prepared):
    x=prepared
    async with x.sessions() as db:
        grants=(await db.scalars(select(PermissionGrant).where(PermissionGrant.permission=='signals.restricted'))).all()
        for grant in grants:grant.revoked_at=utcnow()
        await db.commit()
    _,response=await save_submit(x,True)
    assert response.status_code==503 and response.json()['code']=='support_team_unconfigured'
    own=(await x.first.get(x.root+'/reflection')).json()
    assert own['text']=='Сложно вести занятие' and own['submitted_at'] is None and own['voice_available'] is False
    unavailable=await mutate(x.first,x.root+'/reflection/audio-intent',{'content_type':'audio/wav','expected_size':100,'checksum':'a'*64})
    assert unavailable.status_code==503 and unavailable.json()['code']=='transcription_unconfigured'
    async with x.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(SupportSignal))==0
        assert await db.scalar(select(func.count()).select_from(FollowUpTask))==0

@pytest.mark.asyncio
async def test_reflection_never_gates_or_rewrites_factual_attendance(prepared,monkeypatch):
    x=prepared
    from app.modules.activities import assignment_service
    monkeypatch.setattr(assignment_service,'utcnow',service.utcnow)
    attendance=await mutate(x.admin,f"/api/v1/coord/assignments/{x.confirmed['id']}/attendance",{'expected_version':x.confirmed['version'],'outcome':'attended','minutes':90,'reason':'Фактическое участие.'})
    assert attendance.status_code==200,attendance.text
    async with x.sessions() as db:assert await db.scalar(select(func.count()).select_from(Reflection))==0
    _,submitted=await save_submit(x);assert submitted.status_code==200,submitted.text
    async with x.sessions() as db:
        row=await db.scalar(select(Attendance).where(Attendance.assignment_id==UUID(x.confirmed['id'])))
        assert row.minutes==90
        assert await db.scalar(select(func.count()).select_from(AttendanceEvent))==1

@pytest.mark.asyncio
async def test_no_contact_keeps_reflection_without_creating_contact_task(prepared):
    x=prepared
    async with x.sessions() as db:
        volunteer=await ensure_user_volunteer(db,x.foundation,x.users['volunteer']);volunteer.no_contact=True;await db.commit()
    _,submitted=await save_submit(x)
    assert submitted.status_code==200 and submitted.json()['follow_up_registered'] is False
    async with x.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(SupportSignal))==1
        assert await db.scalar(select(func.count()).select_from(FollowUpTask).where(FollowUpTask.state=='open'))==0

@pytest.mark.asyncio
@pytest.mark.parametrize('decision,next_date,crm_state',[
    ('next_date','2028-01-12','contacted'),('other_role','2028-01-12','contacted'),
    ('discussion','2028-01-12','contacted'),('pause',None,'paused'),('finish',None,'closed')])
async def test_every_next_decision_is_persisted_on_both_sides(prepared,decision,next_date,crm_state):
    x=prepared;_,submitted=await save_submit(x);assert submitted.status_code==200
    row=submitted.json()
    reviewed=await mutate(x.admin,f"/api/v1/coord/reflections/{row['id']}/review",{'expected_version':row['version'],'decision':decision,'public_message':'Согласованный следующий шаг.','assigned_user_id':str(x.users['admin']),'next_date':next_date})
    assert reviewed.status_code==200,reviewed.text
    own=(await x.first.get(x.root+'/reflection')).json()
    staff=(await x.admin.get(f"/api/v1/coord/reflections/{row['id']}")).json()
    assert own['review']['decision']==staff['review']['decision']==decision
    assert own['review']['next_date']==staff['review']['next_date']==next_date
    async with x.sessions() as db:
        volunteer=await db.scalar(select(CrmVolunteer).where(CrmVolunteer.user_id==x.users['volunteer']))
        assert volunteer.relationship_state==crm_state
        open_count=await db.scalar(select(func.count()).select_from(FollowUpTask).where(FollowUpTask.state=='open'))
        assert open_count==(1 if next_date else 0)
