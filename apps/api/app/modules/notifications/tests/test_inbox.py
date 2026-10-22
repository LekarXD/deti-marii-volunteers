"""The bell's derived inbox. Real PostgreSQL: set OPORA_INBOX_TEST_DATABASE_URL ending in /opora_inbox_test."""
import os
from datetime import date,timedelta
from types import SimpleNamespace
from uuid import uuid4
import httpx,pytest,pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select,text
from sqlalchemy.ext.asyncio import async_sessionmaker,create_async_engine
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.db import Base,get_db
from app.core.errors import install_error_handlers
from app.core.model_loader import load_models
from app.core.models import Foundation,PermissionGrant,Session,StaffMembership,User
from app.modules.activities.assignment_models import Assignment,AssignmentEvent
from app.modules.activities.calendar_models import EventOccurrence
from app.modules.activities.router import router as activities_router
from app.modules.followups.models import AssignmentQuestion,Reflection,ReflectionReview
from app.modules.notifications.models import NotificationPreference
from app.modules.notifications.router import router
from app.modules.profile.models import Gratitude,Prize,PrizeRequest,ServiceTimeEntry
load_models()
URL=os.environ.get('OPORA_INBOX_TEST_DATABASE_URL','')
BASE='/api/v1/me/notifications'


def staff_headers():return {'Origin':'http://testserver','X-CSRF-Token':'csrf','Idempotency-Key':str(uuid4())}
def user_headers(token='self'):return {'Cookie':f'opora_session={token}','Origin':'http://testserver','X-CSRF-Token':f'{token}-csrf'}


@pytest_asyncio.fixture
async def env():
    if not URL:pytest.skip('Set dedicated OPORA_INBOX_TEST_DATABASE_URL')
    if not URL.endswith('/opora_inbox_test'):raise RuntimeError('Dedicated inbox test database required')
    engine=create_async_engine(URL);factory=async_sessionmaker(engine,expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'));await conn.run_sync(Base.metadata.drop_all);await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        foundation=Foundation(name='Вымышленный фонд');db.add(foundation);await db.flush()
        coordinator=User(foundation_id=foundation.id,display_name='Вымышленный координатор');volunteer=User(foundation_id=foundation.id,display_name='Вымышленный волонтёр');other=User(foundation_id=foundation.id,display_name='Другой волонтёр')
        db.add_all([coordinator,volunteer,other]);await db.flush()
        member=StaffMembership(foundation_id=foundation.id,user_id=coordinator.id);db.add(member);await db.flush()
        db.add_all([PermissionGrant(membership_id=member.id,permission=p,scope_type='foundation') for p in ('roles.manage','schedule.manage','schedule.read','assignments.manage')])
        expires=utcnow()+timedelta(hours=1)
        db.add_all([Session(foundation_id=foundation.id,user_id=coordinator.id,token_hash=digest('staff'),csrf_hash=digest('csrf'),csrf_cipher='unused',expires_at=expires,mfa_at=utcnow()),
            Session(foundation_id=foundation.id,user_id=volunteer.id,token_hash=digest('self'),csrf_hash=digest('self-csrf'),csrf_cipher='unused',expires_at=expires),
            Session(foundation_id=foundation.id,user_id=other.id,token_hash=digest('other'),csrf_hash=digest('other-csrf'),csrf_cipher='unused',expires_at=expires)])
        await db.commit()
    app=FastAPI();install_error_handlers(app);app.include_router(activities_router,prefix='/api/v1');app.include_router(router)
    async def override():
        async with factory() as db:
            try:yield db
            except BaseException:await db.rollback();raise
    app.dependency_overrides[get_db]=override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',cookies={'opora_session':'staff'}) as client:
        yield SimpleNamespace(client=client,db=factory,foundation=foundation,coordinator=coordinator,volunteer=volunteer,other=other)
    await engine.dispose()


async def occurrence(env,title,day,start='14:00'):
    """A real occurrence with one staffing need, created through the coordinator API."""
    if not hasattr(env,'role'):
        response=await env.client.post('/api/v1/coord/roles',headers=staff_headers(),json={'title':'Ассистент','task':'Помогать ведущей'})
        assert response.status_code==200,response.text;env.role=response.json()
    body={'title':title,'program':'Творческие мастерские','start_date':day,'start_time':start,'timezone':'Europe/Moscow','duration_minutes':120,'location':'Мастерская','audience':'Взрослые участники','group_id':None,
        'staffing_needs':[{'role_id':env.role['id'],'capacity_required':3,'approval_policy':'coordinator'}]}
    response=await env.client.post('/api/v1/coord/event-occurrences',headers=staff_headers(),json=body)
    assert response.status_code==200,response.text
    return response.json()


async def assignment(db,env,event,status,origin,user=None,confirmed_at=None,events=()):
    need=event['staffing_needs'][0]
    row=Assignment(foundation_id=env.foundation.id,user_id=(user or env.volunteer).id,occurrence_id=event['id'],staffing_need_id=need['id'],status=status,origin=origin,confirmed_at=confirmed_at,
        approved_at=confirmed_at if origin!='invitation' else None,conditions_version=need['version'],conditions_snapshot={'role_version_id':need['role_version_id'],'preparation_requirements':[],'approval_policy':'coordinator'},updated_at=utcnow())
    db.add(row);await db.flush()
    for version,(command,actor,at) in enumerate(events,start=1):
        db.add(AssignmentEvent(assignment_id=row.id,version=version,command=command,status=status,actor_id=str(actor.id),created_at=at))
    return row


async def read(env,token='self'):
    response=await env.client.get(BASE,headers=user_headers(token))
    assert response.status_code==200,response.text
    return response.json()


@pytest.mark.asyncio
async def test_each_kind_is_derived_newest_first_for_the_volunteer_only(env):
    now=utcnow();ago=lambda hours:now-timedelta(hours=hours)
    invited=await occurrence(env,'Арт-суббота','2028-01-08')
    signed=await occurrence(env,'Гончарная мастерская','2028-01-09','11:30')
    reserved=await occurrence(env,'Театральная студия','2028-01-10')
    dropped=await occurrence(env,'Кулинарный день','2028-01-11')
    own_cancel=await occurrence(env,'Прогулка в парке','2028-01-12')
    past=await occurrence(env,'Рисуем осень','2028-01-13')
    async with env.db() as db:
        a_invite=await assignment(db,env,invited,'invited','invitation',events=[('invite',env.coordinator,ago(1))])
        a_self=await assignment(db,env,signed,'confirmed','self',confirmed_at=ago(2))
        a_reserve=await assignment(db,env,reserved,'confirmed','reserve',confirmed_at=ago(3))
        # Confirmed through the volunteer's own answer to an invitation: nothing new to tell.
        await assignment(db,env,past,'confirmed','invitation',confirmed_at=ago(4))
        a_dropped=await assignment(db,env,dropped,'cancelled','invitation',confirmed_at=ago(30),events=[('invite',env.coordinator,ago(40)),('confirm',env.volunteer,ago(30)),('cancelled',env.coordinator,ago(5))])
        await assignment(db,env,own_cancel,'cancelled','invitation',events=[('invite',env.coordinator,ago(50)),('cancelled',env.volunteer,ago(45))])
        for event_id in (dropped['id'],own_cancel['id']):(await db.get(EventOccurrence,event_id)).status='cancelled'
        # Another volunteer's invitation never shows up.
        await assignment(db,env,invited,'invited','invitation',user=env.other,events=[('invite',env.coordinator,ago(1))])
        db.add_all([AssignmentQuestion(foundation_id=env.foundation.id,assignment_id=a_self.id,user_id=env.volunteer.id,text='Что взять с собой?',public_answer='Удобную обувь и  фартук.',answered_at=ago(6)),
            AssignmentQuestion(foundation_id=env.foundation.id,assignment_id=a_reserve.id,user_id=env.volunteer.id,text='Личное',restricted=True,public_answer='Личный ответ',answered_at=ago(7)),
            AssignmentQuestion(foundation_id=env.foundation.id,assignment_id=a_reserve.id,user_id=env.volunteer.id,text='Ещё не ответили')])
        reflection=Reflection(foundation_id=env.foundation.id,assignment_id=a_self.id,user_id=env.volunteer.id,submitted_at=ago(20),version=2);db.add(reflection);await db.flush()
        db.add_all([ReflectionReview(foundation_id=env.foundation.id,reflection_id=reflection.id,revision=1,decision='discussion',public_message='Старый ответ',assigned_user_id=env.coordinator.id,author_id=env.coordinator.id,created_at=ago(9)),
            ReflectionReview(foundation_id=env.foundation.id,reflection_id=reflection.id,revision=2,decision='next_date',public_message='Ждём тебя в следующую субботу.',assigned_user_id=env.coordinator.id,author_id=env.coordinator.id,created_at=ago(8))])
        prize=Prize(foundation_id=env.foundation.id,title='Термокружка',price_points=100,stock=3);db.add(prize);await db.flush()
        db.add_all([PrizeRequest(foundation_id=env.foundation.id,user_id=env.volunteer.id,prize_id=prize.id,points=100,state='issued',decided_by=env.coordinator.id,updated_at=ago(10)),
            PrizeRequest(foundation_id=env.foundation.id,user_id=env.volunteer.id,prize_id=prize.id,points=100,state='rejected',reason='Закончились',decided_by=env.coordinator.id,updated_at=ago(11)),
            PrizeRequest(foundation_id=env.foundation.id,user_id=env.volunteer.id,prize_id=prize.id,points=100,state='requested',updated_at=ago(1)),
            PrizeRequest(foundation_id=env.foundation.id,user_id=env.volunteer.id,prize_id=prize.id,points=100,state='cancelled',updated_at=ago(1))])
        for user in (env.volunteer,env.other):
            entry=ServiceTimeEntry(foundation_id=env.foundation.id,user_id=user.id,service_date=date(2027,12,1),title='Занятие',delta_minutes=120,source_kind='manual_review',source_id=uuid4(),source_revision=1,reason='',actor_id='fixture');db.add(entry);await db.flush()
            db.add(Gratitude(foundation_id=env.foundation.id,user_id=user.id,basis_entry_id=entry.id,text='Спасибо, что пришла!',author_id=env.coordinator.id,created_at=ago(12)))
            if user is env.volunteer:db.add(Gratitude(foundation_id=env.foundation.id,user_id=user.id,basis_entry_id=entry.id,text='Слишком давно',author_id=env.coordinator.id,created_at=now-timedelta(days=61)))
        await db.commit()
    body=await read(env)
    assert [(i['kind'],i['title'],i['text'],i['href']) for i in body['items']]==[
        ('invitation','Тебя приглашают','Арт-суббота, 8 января в 14:00',f'/my/assignments/{a_invite.id}'),
        ('place_confirmed','Место за тобой','Гончарная мастерская, 9 января в 11:30',f'/my/assignments/{a_self.id}'),
        ('place_confirmed','Место за тобой','Театральная студия, 10 января в 14:00',f'/my/assignments/{a_reserve.id}'),
        ('occurrence_cancelled','Занятие отменено','Кулинарный день, 11 января в 14:00',f'/my/assignments/{a_dropped.id}'),
        ('question_answered','Координатор ответил','Удобную обувь и фартук.',f'/my/assignments/{a_self.id}/preparation'),
        ('question_answered','Координатор ответил','Театральная студия',f'/my/assignments/{a_reserve.id}/preparation'),
        ('reflection_review','Что дальше после занятия','Ждём тебя в следующую субботу.',f'/my/assignments/{a_self.id}/reflection'),
        ('prize_issued','Приз выдан','Термокружка','/hours?tab=points'),
        ('prize_rejected','Заявка на приз отклонена','Термокружка: Закончились','/hours?tab=points'),
        ('gratitude','Спасибо от команды','Спасибо, что пришла!','/hours')]
    assert body['unread']==10 and len({i['key'] for i in body['items']})==10
    other=await read(env,'other')
    assert [i['kind'] for i in other['items']]==['invitation','gratitude']


@pytest.mark.asyncio
async def test_in_app_preference_off_empties_the_inbox(env):
    invited=await occurrence(env,'Арт-суббота','2028-01-08')
    async with env.db() as db:
        await assignment(db,env,invited,'invited','invitation',events=[('invite',env.coordinator,utcnow())])
        db.add(NotificationPreference(foundation_id=env.foundation.id,user_id=env.volunteer.id,in_app_enabled=False,version=2));await db.commit()
    assert await read(env)=={'items':[],'unread':0}


@pytest.mark.asyncio
async def test_seen_marker_counts_only_newer_items_and_never_moves_back(env):
    now=utcnow()
    first=await occurrence(env,'Арт-суббота','2028-01-08');second=await occurrence(env,'Гончарная мастерская','2028-01-09')
    async with env.db() as db:
        await assignment(db,env,first,'invited','invitation',events=[('invite',env.coordinator,now-timedelta(hours=3))])
        await assignment(db,env,second,'invited','invitation',events=[('invite',env.coordinator,now-timedelta(hours=1))])
        await db.commit()
    assert (await read(env))['unread']==2
    assert (await env.client.post(BASE+'/seen',headers={'Cookie':'opora_session=self','Origin':'http://testserver'},json={'at':now.isoformat()})).status_code==403
    seen=await env.client.post(BASE+'/seen',headers=user_headers(),json={'at':(now-timedelta(hours=2)).isoformat()})
    assert seen.status_code==200,seen.text
    assert seen.json()['unread']==1 and len(seen.json()['items'])==2
    async with env.db() as db:
        pref=await db.scalar(select(NotificationPreference).where(NotificationPreference.user_id==env.volunteer.id))
        # A marker-only row looks exactly like "no preferences saved yet".
        assert pref.version==0 and pref.in_app_enabled and not pref.email_enabled and not pref.no_contact
    older=await env.client.post(BASE+'/seen',headers=user_headers(),json={'at':(now-timedelta(days=1)).isoformat()})
    assert older.json()['unread']==1
    future=await env.client.post(BASE+'/seen',headers=user_headers(),json={'at':(now+timedelta(days=1)).isoformat()})
    assert future.json()['unread']==0
    async with env.db() as db:
        pref=await db.scalar(select(NotificationPreference).where(NotificationPreference.user_id==env.volunteer.id))
        assert pref.version==0 and pref.inbox_seen_at<=utcnow()
    # The other volunteer's marker is separate.
    assert (await read(env,'other'))['unread']==0 and (await read(env))['unread']==0
    naive=await env.client.post(BASE+'/seen',headers=user_headers(),json={'at':'2027-01-01T10:00:00'})
    assert naive.status_code==422


@pytest.mark.asyncio
async def test_saved_preferences_keep_their_version_when_the_marker_moves(env):
    async with env.db() as db:
        db.add(NotificationPreference(foundation_id=env.foundation.id,user_id=env.volunteer.id,email_enabled=True,version=4));await db.commit()
    response=await env.client.post(BASE+'/seen',headers=user_headers(),json={'at':utcnow().isoformat()})
    assert response.status_code==200,response.text
    async with env.db() as db:
        pref=await db.scalar(select(NotificationPreference).where(NotificationPreference.user_id==env.volunteer.id))
        assert pref.version==4 and pref.email_enabled and pref.inbox_seen_at is not None
    assert (await env.client.get(BASE,headers={'Cookie':'opora_session=missing'})).status_code==401
