import os
from datetime import timedelta
from uuid import UUID,uuid4
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select,func,text
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.core.db import Base,get_db
from app.core.config import get_settings
from app.core.errors import ApiError,install_error_handlers
from app.core.models import Foundation,User,PermissionGrant,OutboxMessage
from app.modules.auth.router import router as auth_router
from app.modules.applications.router import router as applications_router
from app.modules.applications.tests.test_applications import actor,anonymous_actor,staff,post,body
from app.modules.crm.router import router
from app.modules.crm.models import CrmVolunteer,FollowUpTask,FollowUpSource
from app.modules.crm.service import schedule_follow_up,today

@pytest_asyncio.fixture
async def env():
    url=os.environ.get('OPORA_CRM_TEST_DATABASE_URL','')
    if not url:pytest.skip('Set dedicated OPORA_CRM_TEST_DATABASE_URL')
    if not url.endswith('/opora_crm_test'):raise RuntimeError('Dedicated CRM DB required')
    engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
        await conn.run_sync(Base.metadata.drop_all);await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:db.add(Foundation(id=get_settings().foundation_id,name='Тестовый фонд'));await db.commit()
    app=FastAPI();install_error_handlers(app);app.include_router(auth_router);app.include_router(applications_router);app.include_router(router)
    async def override_db():
        async with factory() as db:
            try:yield db
            except BaseException:await db.rollback();raise
    app.state.test_factory=factory;app.dependency_overrides[get_db]=override_db
    yield app,factory
    await engine.dispose()

async def coordinator(app,factory):return await staff(app,factory,('crm.read','crm.write','contacts.review','candidates.read'))
async def put(client,path,payload):return await client.put('/api/v1'+path,json=payload,headers={'Idempotency-Key':str(uuid4())})
async def card(factory,name,no_contact=False,contacts=None):
    """A volunteer card stored directly; cards no longer arrive through a contact import."""
    async with factory() as db:
        value=CrmVolunteer(foundation_id=get_settings().foundation_id,display_name=name,contacts=contacts or {},context='Тестовая карточка',no_contact=no_contact)
        db.add(value);await db.commit();return str(value.id)
async def count(factory,model):
    async with factory() as db:return await db.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_readiness_requires_reviewed_availability_and_agreement_without_delivery(env):
    app,factory=env;coord=await coordinator(app,factory);public=await anonymous_actor(app);writer=await staff(app,factory,('crm.read','crm.write'))
    try:
        assert (await public.get('/api/v1/coord/volunteers')).status_code==403
        person=await card(factory,'Тест Анна',contacts={'email':'anna@example.test'});outbox=await count(factory,OutboxMessage)
        detail=(await coord.get('/api/v1/coord/volunteers/'+person)).json()
        assert detail['relationship_state']=='unverified' and not detail['can_invite']
        early=await post(coord,f"/coord/volunteers/{person}/agreements",dict(expected_version=1,text='Готов',relationship_state='ready'))
        assert early.status_code==422 and early.json()['code']=='availability_required',early.text
        saved=await put(coord,f"/coord/volunteers/{person}/availability",dict(expected_version=1,summary='Суббота днём',preferred_channel='email',windows=[{'weekday':5,'start_minute':720,'end_minute':900}]))
        assert saved.status_code==200,saved.text
        valid_until=(today()+timedelta(days=14)).isoformat()
        # Confirming availability and no-contact stay behind contacts.review, not crm.write.
        assert (await post(writer,f"/coord/volunteers/{person}/availability-verifications",dict(expected_version=saved.json()['version'],valid_until=valid_until,source='Разговор с волонтёром'))).status_code==403
        assert (await post(writer,f"/coord/volunteers/{person}/contact-preference",dict(expected_version=saved.json()['version'],no_contact=True,reason='Попросил не звонить'))).status_code==403
        verified=await post(coord,f"/coord/volunteers/{person}/availability-verifications",dict(expected_version=saved.json()['version'],valid_until=valid_until,source='Разговор с волонтёром'))
        assert verified.status_code==200 and verified.json()['availability']['verified'],verified.text
        ready=await post(coord,f"/coord/volunteers/{person}/agreements",dict(expected_version=verified.json()['version'],text='Согласовали помощь на занятии',relationship_state='ready'))
        assert ready.status_code==200,ready.text
        assert ready.json()['can_invite'] and ready.json()['relationship_state']=='ready'
        changed=await put(coord,f"/coord/volunteers/{person}/availability",dict(expected_version=ready.json()['version'],summary='Теперь по воскресеньям',preferred_channel='email',windows=[]))
        assert changed.status_code==200,changed.text
        assert not changed.json()['can_invite'] and not changed.json()['availability']['verified']
        assert await count(factory,OutboxMessage)==outbox
    finally:await coord.aclose();await public.aclose();await writer.aclose()

@pytest.mark.asyncio
async def test_merge_preserves_history_and_strict_no_contact(env):
    app,factory=env;coord=await coordinator(app,factory)
    try:
        first=await card(factory,'Тест Анна',contacts={'email':'anna@example.test'});second=await card(factory,'Тест дубль',no_contact=True,contacts={'phone':'+70000000000'})
        for person,note in ((first,'Звонок Анне'),(second,'Письмо от дубля')):
            recorded=await post(coord,f"/coord/volunteers/{person}/contact-events",dict(expected_version=1,kind='phone',direction='recorded',text=note));assert recorded.status_code==200,recorded.text
        # A merge retains all histories and strict no-contact from either record.
        merged=await post(coord,f"/coord/volunteers/{second}/merge",dict(expected_version=2,target_id=first,target_expected_version=2,reason='Фиктивный дубль проверен координатором'))
        assert merged.status_code==200,merged.text
        detail=merged.json();assert detail['no_contact'] and second in detail['merged_record_ids']
        assert {'Звонок Анне','Письмо от дубля'}<={event['text'] for event in detail['contact_events']} and any(event['kind']=='merged' for event in detail['contact_events'])
        assert detail['contacts']=={'email':'anna@example.test','phone':'+70000000000'}
        assert (await coord.get('/api/v1/coord/volunteers/'+second)).status_code==409
        outgoing=await post(coord,f"/coord/volunteers/{first}/contact-events",dict(expected_version=detail['version'],kind='phone',direction='outgoing',text='Звонок'))
        assert outgoing.status_code==409
    finally:await coord.aclose()

@pytest.mark.asyncio
async def test_follow_up_revision_fencing_no_contact_and_cas(env):
    app,factory=env;coord=await coordinator(app,factory);candidate=await actor(app)
    try:
        application=(await post(candidate,'/applications/submit',body())).json()
        owner=UUID((await coord.get('/api/v1/auth/session')).json()['user_id']);source_id=uuid4()
        async with factory() as db:
            first=await schedule_follow_up(db,get_settings().foundation_id,UUID(application['id']),owner,today(),'interview_result',source_id,1,'fixture')
            replay=await schedule_follow_up(db,get_settings().foundation_id,UUID(application['id']),owner,today(),'interview_result',source_id,1,'fixture')
            assert first.id==replay.id
            assert await schedule_follow_up(db,get_settings().foundation_id,UUID(application['id']),owner,None,'interview_result',source_id,2,'fixture') is None
            await db.commit();task=await db.get(FollowUpTask,first.id);assert task.state=='cancelled'
            with pytest.raises(ApiError) as error:await schedule_follow_up(db,get_settings().foundation_id,UUID(application['id']),owner,today(),'interview_result',source_id,1,'fixture')
            assert error.value.code=='stale_follow_up_source'
        volunteer=(await coord.get('/api/v1/coord/volunteers')).json()['items'][0]
        task=await post(coord,f"/coord/volunteers/{volunteer['id']}/follow-up-tasks",dict(expected_version=volunteer['version'],title='Уточнить первый выход',due_on=today().isoformat(),assigned_user_id=str(owner)));assert task.status_code==200,task.text
        latest=(await coord.get('/api/v1/coord/volunteers/'+volunteer['id'])).json()
        no_contact=await post(coord,f"/coord/volunteers/{volunteer['id']}/contact-preference",dict(expected_version=latest['version'],no_contact=True,reason='Человек попросил не связываться'));assert no_contact.status_code==200,no_contact.text
        assert all(t['state']!='open' for t in no_contact.json()['follow_up_tasks'])
        forbidden=await post(coord,f"/coord/volunteers/{volunteer['id']}/follow-up-tasks",dict(expected_version=no_contact.json()['version'],title='Позвонить',due_on=today().isoformat(),assigned_user_id=str(owner)))
        assert forbidden.status_code==409
        stale=await post(coord,f"/coord/volunteers/{volunteer['id']}/agreements",dict(expected_version=1,text='Устаревшая версия'));assert stale.status_code==409
    finally:await coord.aclose();await candidate.aclose()

@pytest.mark.asyncio
async def test_revoked_permission_blocks_receipt_replay_and_cross_foundation(env):
    app,factory=env;coord=await coordinator(app,factory)
    try:
        person=await card(factory,'Тест Анна');key=str(uuid4())
        result=await post(coord,f"/coord/volunteers/{person}/agreements",dict(expected_version=1,text='Договорились о знакомстве'),key);assert result.status_code==200,result.text
        async with factory() as db:
            grant=await db.scalar(select(PermissionGrant).where(PermissionGrant.permission=='crm.write'));grant.revoked_at=__import__('app.core.clock',fromlist=['utcnow']).utcnow();await db.commit()
        denied=await post(coord,f"/coord/volunteers/{person}/agreements",dict(expected_version=1,text='Договорились о знакомстве'),key);assert denied.status_code==403,denied.text
        async with factory() as db:
            other=Foundation(name='Чужой фонд');db.add(other);await db.flush()
            row=await db.get(CrmVolunteer,UUID(person));row.foundation_id=other.id;await db.commit()
        assert (await coord.get('/api/v1/coord/volunteers/'+person)).status_code==404
    finally:await coord.aclose()

@pytest.mark.asyncio
async def test_concurrent_create_and_self_availability_are_scoped(env):
    import asyncio
    app,factory=env;coord=await coordinator(app,factory);applicant=await actor(app);candidate=await actor(app);other=await actor(app)
    try:
        submitted=(await post(applicant,'/applications/submit',body())).json()
        results=await asyncio.gather(*(post(coord,'/coord/volunteers',dict(application_id=submitted['id'])) for _ in range(2)))
        assert [result.status_code for result in results]==[200,200],[result.text for result in results]
        assert results[0].json()['id']==results[1].json()['id'] and await count(factory,CrmVolunteer)==1
        application=(await post(candidate,'/applications/submit',body())).json()
        first=await put(candidate,'/me/availability',dict(expected_version=0,summary='В субботу с 12 до 15',preferred_channel='email',windows=[dict(weekday=5,start_minute=720,end_minute=900)]))
        assert first.status_code==200,first.text
        own=first.json();assert not own['availability']['verified']
        assert (await other.get('/api/v1/me/availability')).json()['volunteer_id'] is None
        stale=await put(candidate,'/me/availability',dict(expected_version=0,summary='Устаревшее изменение',preferred_channel='phone'));assert stale.status_code==409
        detail=(await coord.get('/api/v1/coord/volunteers/'+own['volunteer_id'])).json()
        outcome=await post(coord,f"/coord/volunteers/{own['volunteer_id']}/first-visit-outcomes",dict(expected_version=detail['version'],outcome='pause',note='Попросил вернуться к обсуждению позже'))
        assert outcome.status_code==200,outcome.text
        assert outcome.json()['relationship_state']=='paused' and any(event['kind']=='first_visit_outcome' for event in outcome.json()['contact_events'])
    finally:await coord.aclose();await applicant.aclose();await candidate.aclose();await other.aclose()

@pytest.mark.asyncio
async def test_merged_follow_up_remains_actionable_without_rewriting_identity(env):
    app,factory=env;coord=await coordinator(app,factory)
    try:
        target=await card(factory,'Тест Анна');source=await card(factory,'Тест Борис')
        owner=(await coord.get('/api/v1/auth/session')).json()['user_id']
        task=(await post(coord,f"/coord/volunteers/{source}/follow-up-tasks",dict(expected_version=1,title='Обсудить доступность',due_on=today().isoformat(),assigned_user_id=owner))).json()
        merged=await post(coord,f"/coord/volunteers/{source}/merge",dict(expected_version=2,target_id=target,target_expected_version=1,reason='Проверенный фиктивный дубль'))
        assert merged.status_code==200,merged.text
        assert merged.json()['next_task']['id']==task['id']
        completed=await post(coord,f"/coord/follow-up-tasks/{task['id']}",dict(expected_version=task['version'],state='done',reason='Разговор состоялся'))
        assert completed.status_code==200,completed.text
        assert completed.json()['volunteer_id']==source and completed.json()['state']=='done'
    finally:await coord.aclose()

@pytest.mark.asyncio
async def test_user_follow_up_reuses_shared_store_without_application(env):
    from app.modules.crm.service import schedule_user_follow_up
    app,factory=env;coord=await coordinator(app,factory)
    try:
        owner=UUID((await coord.get('/api/v1/auth/session')).json()['user_id'])
        async with factory() as db:
            user=User(foundation_id=get_settings().foundation_id,display_name='Участник без анкеты');db.add(user);await db.flush()
            source=uuid4();first=await schedule_user_follow_up(db,get_settings().foundation_id,user.id,owner,today(),'assignment',source,1,'fixture')
            replay=await schedule_user_follow_up(db,get_settings().foundation_id,user.id,owner,today(),'assignment',source,1,'fixture')
            assert first.id==replay.id and first.application_id is None
            await db.commit()
            assert await db.scalar(select(func.count()).select_from(FollowUpTask))==1
            assert await db.scalar(select(func.count()).select_from(FollowUpSource))==1
            with pytest.raises(ApiError) as error:await schedule_user_follow_up(db,uuid4(),user.id,owner,today(),'assignment',uuid4(),1,'fixture')
            assert error.value.status_code==404
    finally:await coord.aclose()

def test_ten_digit_import_phone_is_stored_as_russian_number():
    from app.modules.crm.imports import normalize
    mapping={'name':'Имя','phone':'Телефон'}
    for raw in ('(916) 123-45-67','8 916 123-45-67','+7 916 123 45 67'):assert normalize({'Имя':'Тест','Телефон':raw},mapping)==({'name':'Тест','phone':'+79161234567','email':'','telegram':'','no_contact':False},[])
    assert normalize({'Имя':'Тест','Телефон':'+353 123 4567'},mapping)[0]['phone']=='+3531234567'

@pytest.mark.asyncio
async def test_ten_digit_import_phone_matches_existing_card(env):
    app,factory=env;coord=await coordinator(app,factory)
    try:
        async with factory() as db:db.add(CrmVolunteer(foundation_id=get_settings().foundation_id,display_name='Анна Тестовая',contacts={'phone':'+79991234567'},context='Анкета волонтёра',relationship_state='unverified'));await db.commit()
        preview=await prepare(coord,'Имя;Телефон\nАнна из таблицы;(999) 123-45-67\n'.encode(),{'name':'Имя','phone':'Телефон'})
        assert preview['rows'][0]['decision']=='review' and preview['rows'][0]['normalized']['phone']=='+79991234567',preview
    finally:await coord.aclose()

@pytest.mark.asyncio
async def test_own_no_contact_preference_blocks_staff_follow_ups(env):
    from app.modules.notifications.models import NotificationPreference
    app,factory=env;coord=await coordinator(app,factory);candidate=await actor(app)
    try:
        application=(await post(candidate,'/applications/submit',body())).json()
        owner=UUID((await coord.get('/api/v1/auth/session')).json()['user_id']);user_id=UUID((await candidate.get('/api/v1/auth/session')).json()['user_id'])
        async with factory() as db:
            db.add(NotificationPreference(foundation_id=get_settings().foundation_id,user_id=user_id,no_contact=True));await db.flush()
            assert await schedule_follow_up(db,get_settings().foundation_id,UUID(application['id']),owner,today(),'interview_result',uuid4(),1,'fixture') is None
            # The volunteer's own help request still reaches staff.
            assert await schedule_follow_up(db,get_settings().foundation_id,None,owner,today(),'support_signal',uuid4(),1,'fixture',user_id=user_id) is not None
            await db.commit()
        volunteer=(await coord.get('/api/v1/coord/volunteers')).json()['items'][0]
        assert not volunteer['no_contact'] and not volunteer['can_invite'] and 'Человек попросил не связываться' in volunteer['blocked_reasons']
        task=await post(coord,f"/coord/volunteers/{volunteer['id']}/follow-up-tasks",dict(expected_version=volunteer['version'],title='Позвонить',due_on=today().isoformat(),assigned_user_id=str(owner)))
        assert task.status_code==409 and task.json()['code']=='no_contact',task.text
        call=await post(coord,f"/coord/volunteers/{volunteer['id']}/contact-events",dict(expected_version=volunteer['version'],kind='phone',direction='outgoing',text='Звонок'))
        assert call.status_code==409 and call.json()['code']=='no_contact',call.text
    finally:await coord.aclose();await candidate.aclose()
