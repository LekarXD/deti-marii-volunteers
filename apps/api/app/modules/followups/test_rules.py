from datetime import timedelta,time
from uuid import UUID,uuid4
from types import SimpleNamespace
import httpx,pytest
from fastapi import FastAPI
from sqlalchemy import select,func
from app.core.auth import resolve_principal
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.db import get_db
from app.core.errors import install_error_handlers
from app.core.models import Session,StaffMembership,PermissionGrant,OutboxMessage,Job
from app.modules.staff.tests.test_staff import world
from app.modules.followups.rule_router import router
from app.modules.followups.rule_models import SignalRuleSettings,RuleSignal
from app.modules.followups.rule_jobs import evaluate_rules
from app.modules.followups.rule_sources import collect
from app.modules.activities.models import VolunteerRole,VolunteerRoleVersion
from app.modules.activities.calendar_models import EventSeries,EventOccurrence,StaffingNeed
from app.modules.activities.assignment_models import Assignment,Attendance
from app.modules.participants.models import ParticipantGroup
from app.modules.crm.models import CrmVolunteer,ContactEvent
from app.modules.learning.models import LearningTrack,LearningRelease,LearningAssignment,Lesson,LessonVersion
from app.modules.applications.models import Application
from app.worker.queue import claim,complete
from app.worker.registry import JobContext

@pytest.fixture
async def scenario(world,monkeypatch):
    w=world
    async with w.factory() as db:
        member=await db.scalar(select(StaffMembership).where(StaffMembership.user_id==w.admin.user_id))
        for name in ('followups.read','followups.manage','crm.read','assignments.manage','schedule.read','learning.read','candidates.read'):db.add(PermissionGrant(membership_id=member.id,permission=name))
        session=await db.get(Session,w.admin.session_id);session.token_hash=digest('rules-admin');session.csrf_hash=digest('rules-csrf');await db.commit()
    app=FastAPI();install_error_handlers(app);app.include_router(router,prefix='/api/v1')
    async def database():
        async with w.factory() as db:yield db
    app.dependency_overrides[get_db]=database
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(),'trusted_origins',['http://testserver'])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',cookies={'opora_session':'rules-admin'},headers={'Origin':'http://testserver','X-CSRF-Token':'rules-csrf'}) as client:yield SimpleNamespace(w=w,client=client)
async def post(f,path,body,key=None):return await f.client.post('/api/v1/coord/followups/'+path,json=body,headers={'Idempotency-Key':key or uuid4().hex})
async def facts(f):
    w=f.w;now=utcnow()
    async with w.factory() as db:
        group=ParticipantGroup(foundation_id=w.foundation.id,title='Основная группа');db.add(group);await db.flush()
        role=VolunteerRole(foundation_id=w.foundation.id,title='Помощник',normalized_title='помощник',updated_by='fixture');db.add(role);await db.flush()
        rv=VolunteerRoleVersion(role_id=role.id,version=1,snapshot={},actor_id='fixture');db.add(rv)
        series=EventSeries(foundation_id=w.foundation.id,group_id=group.id,anchor_date=now.date(),origin_time=time(12),start_date=now.date(),start_time=time(12),duration_minutes=60,recurrence={},title='Мастерская',updated_by='fixture');db.add(series);await db.flush()
        events=[]
        for days in (-4,-2,3):
            starts=now+timedelta(days=days)
            event=EventOccurrence(id=uuid4(),foundation_id=w.foundation.id,series_id=series.id,origin_local_date=starts.date(),origin_local_time=time(12),starts_at=starts,ends_at=starts+timedelta(hours=1),timezone='Europe/Moscow',group_id=group.id,title='Мастерская',status='completed' if days<0 else 'scheduled',series_version=1,updated_by='fixture');db.add(event);await db.flush()
            need=StaffingNeed(foundation_id=w.foundation.id,occurrence_id=event.id,role_id=role.id,role_version_id=rv.id,capacity_required=1);db.add(need);await db.flush()
            if days<0:
                assignment=Assignment(foundation_id=w.foundation.id,user_id=w.recipient.user_id,occurrence_id=event.id,staffing_need_id=need.id,group_id_snapshot=group.id,status='confirmed',confirmed_at=now-timedelta(days=10),conditions_version=1,conditions_snapshot={});db.add(assignment);await db.flush();db.add(Attendance(foundation_id=w.foundation.id,assignment_id=assignment.id,outcome='absent',minutes=0))
            events.append(event)
        person=CrmVolunteer(foundation_id=w.foundation.id,user_id=w.recipient.user_id,display_name='Получатель',relationship_state='active');db.add(person);await db.flush();db.add(ContactEvent(volunteer_id=person.id,kind='email',direction='incoming',text='PRIVATE CONTACT TEXT',author_id='fixture',occurred_at=now-timedelta(days=30)))
        track=LearningTrack(foundation_id=w.foundation.id,key='rules-fixture',title='Трек');db.add(track);await db.flush();lesson=Lesson(foundation_id=w.foundation.id,track_id=track.id,key='lesson');db.add(lesson);await db.flush();lv=LessonVersion(lesson_id=lesson.id,number=1,title='Урок');db.add(lv);await db.flush()
        release=LearningRelease(foundation_id=w.foundation.id,track_id=track.id,number=1,title='Трек',lesson_version_ids=[str(lv.id)]);db.add(release);await db.flush();learning=LearningAssignment(foundation_id=w.foundation.id,release_id=release.id,user_id=w.recipient.user_id,assigned_at=now-timedelta(days=20));db.add(learning)
        application=Application(foundation_id=w.foundation.id,user_id=w.recipient.user_id,submitted_at=now-timedelta(days=5));db.add(application);await db.commit()
    return SimpleNamespace(group=group,events=events,person=person,learning=learning,application=application)
async def run(f):
    async with f.w.factory() as db:
        job=await claim(db,kinds=['followups.rules']);assert job;await db.commit();context=JobContext(job.id,job.claim_token,job.foundation_id,dict(job.payload));result=await evaluate_rules(db,context);await complete(db,job.id,job.claim_token,result);await db.commit();return result

@pytest.mark.asyncio
async def test_defaults_save_and_real_five_source_evaluation_idempotency(scenario):
    f=scenario;await facts(f);initial=(await f.client.get('/api/v1/coord/followups/rules')).json();assert initial['thresholds']=={'miss':2,'quiet':21,'learn':14,'app':3,'shift':7} and initial['version']==0
    body={'expected_version':0,'thresholds':initial['thresholds']};saved=await post(f,'rules',body,'save-once');assert saved.status_code==200,saved.text
    assert (await post(f,'rules',body,'save-once')).json()==saved.json()
    result=await run(f);assert all(result[name]['matched']==1 for name in ('miss','quiet','learn','app','shift')),result
    queue=(await f.client.get('/api/v1/coord/followups/rule-signals')).json();assert len(queue)==5 and 'PRIVATE CONTACT TEXT' not in str(queue)
    async with f.w.factory() as db:
        assert await db.scalar(select(func.count()).select_from(OutboxMessage))==0
        next_job=await db.scalar(select(Job).where(Job.kind=='followups.rules',Job.state=='queued'));assert next_job.available_at>utcnow()
    current=(await f.client.get('/api/v1/coord/followups/rules')).json();assert (await post(f,'rules/evaluate',{'expected_version':current['version']})).status_code==200;assert (await run(f))['quiet']['matched']==1
    async with f.w.factory() as db:assert await db.scalar(select(func.count()).select_from(RuleSignal))==5

@pytest.mark.asyncio
async def test_configuration_changes_actual_detection_and_reset_is_cas(scenario):
    f=scenario;await facts(f)
    response=await post(f,'rules',{'expected_version':0,'thresholds':{'miss':3,'quiet':31,'learn':21,'app':6,'shift':1}});assert response.status_code==200
    result=await run(f);assert all(result[name]['matched']==0 for name in result),result
    reset=await post(f,'rules/reset',{'expected_version':1});assert reset.status_code==200 and reset.json()['thresholds']['quiet']==21
    assert (await post(f,'rules/reset',{'expected_version':1})).status_code==409
    result=await run(f);assert all(result[name]['matched']==1 for name in result)
    bad=await post(f,'rules',{'expected_version':2,'thresholds':{'miss':0}});assert bad.status_code==422

@pytest.mark.asyncio
async def test_unknown_facts_and_current_permissions_do_not_infer_absence(scenario):
    f=scenario
    async with f.w.factory() as db:db.add(CrmVolunteer(foundation_id=f.w.foundation.id,display_name='Нет истории',relationship_state='active'));await db.commit()
    assert (await post(f,'rules/evaluate',{'expected_version':0})).status_code==200
    result=await run(f);assert result['miss']['state']=='unknown' and result['quiet']['unknown']==1
    async with f.w.factory() as db:
        grant=await db.scalar(select(PermissionGrant).join(StaffMembership).where(StaffMembership.user_id==f.w.admin.user_id,PermissionGrant.permission=='followups.manage'));grant.revoked_at=utcnow();await db.commit()
    assert (await post(f,'rules/evaluate',{'expected_version':0})).status_code==403

@pytest.mark.asyncio
async def test_queue_and_receipt_current_scope_revoke_and_foreign_foundation(scenario):
    f=scenario;data=await facts(f);assert (await post(f,'rules/evaluate',{'expected_version':0})).status_code==200;await run(f)
    queue=(await f.client.get('/api/v1/coord/followups/rule-signals')).json();quiet=next(x for x in queue if x['rule']=='quiet')
    body={'expected_version':quiet['version'],'reason':'Обсудили следующий контакт'};dismiss=await post(f,f"rule-signals/{quiet['id']}/dismiss",body,'dismiss');assert dismiss.status_code==200
    async with f.w.factory() as db:
        crm=await db.scalar(select(PermissionGrant).join(StaffMembership).where(StaffMembership.user_id==f.w.admin.user_id,PermissionGrant.permission=='crm.read'));crm.revoked_at=utcnow();await db.commit()
        foreign=RuleSignal(foundation_id=f.w.foreign.id,rule='quiet',entity_id=uuid4(),title='FOREIGN SECRET',details={},source_hash='a'*64,settings_version=1);db.add(foreign);await db.commit()
    assert (await post(f,f"rule-signals/{quiet['id']}/dismiss",body,'dismiss')).status_code==404
    queue=(await f.client.get('/api/v1/coord/followups/rule-signals')).json();assert all(x['rule']!='quiet' for x in queue) and 'FOREIGN SECRET' not in str(queue)
    current=(await f.client.get('/api/v1/coord/followups/rules')).json();assert current['last_result']['quiet']=={'state':'unknown','reason':'source_permission_required'}

@pytest.mark.asyncio
async def test_missing_attendance_is_unknown_and_revoked_owner_blocks_queued_evaluation(scenario):
    f=scenario;data=await facts(f)
    async with f.w.factory() as db:
        latest=await db.scalar(select(Attendance).join(Assignment,Assignment.id==Attendance.assignment_id).join(EventOccurrence,EventOccurrence.id==Assignment.occurrence_id).where(Assignment.foundation_id==f.w.foundation.id).order_by(EventOccurrence.ends_at.desc()));await db.delete(latest);await db.commit()
    assert (await post(f,'rules/evaluate',{'expected_version':0})).status_code==200
    result=await run(f);assert result['miss']['unknown']==1 and result['miss']['matched']==0
    current=(await f.client.get('/api/v1/coord/followups/rules')).json();assert (await post(f,'rules/evaluate',{'expected_version':current['version']})).status_code==200
    async with f.w.factory() as db:
        grant=await db.scalar(select(PermissionGrant).join(StaffMembership).where(StaffMembership.user_id==f.w.admin.user_id,PermissionGrant.permission=='followups.manage'));grant.revoked_at=utcnow();await db.commit()
    assert await run(f)=={'state':'blocked','reason':'owner_access_revoked'}

@pytest.mark.asyncio
async def test_group_reader_only_sees_its_derived_signals_and_cannot_configure(scenario):
    f=scenario;data=await facts(f);assert (await post(f,'rules/evaluate',{'expected_version':0})).status_code==200;await run(f)
    async with f.w.factory() as db:
        member=StaffMembership(foundation_id=f.w.foundation.id,user_id=f.w.wrong.user_id);db.add(member);await db.flush()
        db.add(PermissionGrant(membership_id=member.id,permission='followups.read',scope_type='group',scope_id=data.group.id));db.add(PermissionGrant(membership_id=member.id,permission='assignments.manage'));db.add(PermissionGrant(membership_id=member.id,permission='schedule.read'))
        session=await db.get(Session,f.w.wrong.session_id);session.mfa_at=utcnow();session.token_hash=digest('rules-group-reader');session.csrf_hash=digest('rules-csrf');await db.commit()
    f.client.cookies.set('opora_session','rules-group-reader');rows=(await f.client.get('/api/v1/coord/followups/rule-signals')).json();assert {x['rule'] for x in rows}=={'miss','shift'}
    assert (await f.client.get('/api/v1/coord/followups/rules')).status_code==403
    assert (await post(f,'rules/reset',{'expected_version':1})).status_code==403


@pytest.mark.asyncio
async def test_explicit_source_corrections_resolve_all_five_conditions(scenario):
    f=scenario;data=await facts(f);assert (await post(f,'rules/evaluate',{'expected_version':0})).status_code==200;await run(f)
    async with f.w.factory() as db:
        for attendance in (await db.scalars(select(Attendance).where(Attendance.foundation_id==f.w.foundation.id))).all():attendance.outcome='attended';attendance.minutes=60;attendance.version+=1
        db.add(ContactEvent(volunteer_id=data.person.id,kind='phone',direction='outgoing',text='Уточнили планы',author_id='fixture',occurred_at=utcnow()))
        learning=await db.get(LearningAssignment,data.learning.id);learning.completed_at=utcnow()
        application=await db.get(Application,data.application.id);application.review_state='closed';application.version+=1
        event=await db.get(EventOccurrence,data.events[-1].id);event.status='cancelled';event.version+=1
        await db.commit()
    assert (await post(f,'rules/evaluate',{'expected_version':1})).status_code==200;result=await run(f);assert all(result[name]['matched']==0 for name in result),result
    assert (await f.client.get('/api/v1/coord/followups/rule-signals')).json()==[]


@pytest.mark.asyncio
async def test_dismissed_observation_stays_closed_until_source_facts_change(scenario):
    f=scenario;data=await facts(f);assert (await post(f,'rules/evaluate',{'expected_version':0})).status_code==200;await run(f)
    quiet=next(x for x in (await f.client.get('/api/v1/coord/followups/rule-signals')).json() if x['rule']=='quiet')
    assert (await post(f,f"rule-signals/{quiet['id']}/dismiss",{'expected_version':quiet['version'],'reason':'Решение принято'})).status_code==200
    assert (await post(f,'rules/evaluate',{'expected_version':1})).status_code==200;await run(f)
    assert all(x['rule']!='quiet' for x in (await f.client.get('/api/v1/coord/followups/rule-signals')).json())
    async with f.w.factory() as db:db.add(ContactEvent(volunteer_id=data.person.id,kind='phone',direction='incoming',text='Дополнительный исходный факт',author_id='fixture',occurred_at=utcnow()-timedelta(days=25)));await db.commit()
    assert (await post(f,'rules/evaluate',{'expected_version':2})).status_code==200;await run(f)
    reopened=next(x for x in (await f.client.get('/api/v1/coord/followups/rule-signals')).json() if x['rule']=='quiet');assert reopened['id']==quiet['id'] and reopened['version']>quiet['version']

@pytest.mark.asyncio
async def test_quiet_rule_respects_the_volunteers_own_no_contact_preference(scenario):
    from app.modules.notifications.models import NotificationPreference
    f=scenario;data=await facts(f)
    async with f.w.factory() as db:
        alias=CrmVolunteer(foundation_id=f.w.foundation.id,display_name='Старая карточка',relationship_state='active',merged_into_id=data.person.id);db.add(alias);await db.commit()
        assert len((await collect(db,f.w.foundation.id,'quiet',21,utcnow()))[0])==1
        db.add(NotificationPreference(foundation_id=f.w.foundation.id,user_id=f.w.recipient.user_id,no_contact=True));await db.commit()
        found,result=await collect(db,f.w.foundation.id,'quiet',21,utcnow());assert found==[] and result['matched']==0
