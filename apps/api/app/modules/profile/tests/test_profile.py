import io,os,zipfile,json,asyncio
from datetime import date,time,timedelta,datetime,timezone
from uuid import UUID,uuid4
import pytest,pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select,func,text
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from httpx import ASGITransport,AsyncClient
from pypdf import PdfReader
from app.core.model_loader import load_models
from app.core.db import Base,get_db
from app.core.config import get_settings
from app.core.errors import ApiError,install_error_handlers
from app.core.models import Foundation,User,MediaAsset,PermissionGrant
from app.core.auth import get_principal,resolve_principal
from app.modules.auth.router import router as auth_router
from app.modules.assets.router import router as asset_router
from app.modules.applications.tests.test_applications import staff,anonymous_actor,post
from app.modules.applications.consents import newsletter_consent
from app.modules.profile.router import router
from app.modules.profile.models import ServiceTimeEntry,ProfileRevision,ProfileChangeSuggestion
from app.modules.profile.service import public_snapshot,create_suggestion
from app.modules.profile.ledger import append_service_time
load_models()

@pytest_asyncio.fixture
async def env():
    url=os.environ.get('OPORA_PROFILE_TEST_DATABASE_URL','')
    if not url:pytest.skip('Dedicated OPORA_PROFILE_TEST_DATABASE_URL required')
    if not url.endswith('/opora_profile_test'):raise RuntimeError('Dedicated profile DB required')
    engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
        await conn.run_sync(Base.metadata.drop_all);await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:db.add(Foundation(id=get_settings().foundation_id,name='Фонд «Дети Марии»'));await db.commit()
    app=FastAPI();install_error_handlers(app)
    for routes in (auth_router,router,asset_router):app.include_router(routes)
    async def override():
        async with factory() as db:
            try:yield db
            except BaseException:await db.rollback();raise
    app.dependency_overrides[get_db]=override
    yield app,factory
    await engine.dispose()
async def volunteer(app,factory):return await staff(app,factory,())
async def coord(app,factory):return await staff(app,factory,('hours.review','recognition.manage','profile.requests.review'))
async def principal_for(client,factory):
    from app.core.crypto import digest
    from app.core.models import Session
    async with factory() as db:
        row=await db.scalar(select(Session).where(Session.token_hash==digest(client.cookies.get('opora_session'))))
        return await resolve_principal(db,row)
def update(version=0,**kw):
    return dict(expected_version=version,display_name='Анна Тестовая',about='Рисую акварелью',tags=[dict(kind='skill',label='Акварель',level='sure')],ai_about=True,ai_skills=True,ai_interests=True,**kw)
async def put(client,body,key=None):return await client.put('/api/v1/me/profile',json=body,headers={'Idempotency-Key':key or str(uuid4())})

@pytest.mark.asyncio
async def test_versioned_self_profile_and_verified_scope(env):
    app,factory=env;own=await volunteer(app,factory);other=await volunteer(app,factory);limited=await anonymous_actor(app)
    try:
        assert (await limited.get('/api/v1/me/profile')).status_code==403
        assert (await own.get('/api/v1/me/profile')).json()['version']==0
        payload=update();key=str(uuid4());first,second=await asyncio.gather(put(own,payload,key),put(own,payload,key))
        assert first.status_code==second.status_code==200,first.text
        assert first.json()==second.json();view=first.json();assert view['version']==1 and view['tags'][0]['level']=='sure'
        assert (await put(own,payload)).status_code==409
        assert (await other.get('/api/v1/me/profile')).json()['version']==0
        assert 'normalized_contact' not in first.text
        async with factory() as db:assert await db.scalar(select(func.count()).select_from(ProfileRevision))==1
    finally:await own.aclose();await other.aclose();await limited.aclose()

@pytest.mark.asyncio
async def test_manual_minutes_corrections_pdf_and_download_acl(env):
    app,factory=env;own=await volunteer(app,factory);other=await volunteer(app,factory);reviewer=await coord(app,factory)
    try:
        response=await post(own,'/me/hours/requests',dict(title='Помощь в мастерской',service_date=date.today().isoformat(),requested_minutes=125),'request')
        assert response.status_code==200,response.text
        manual=response.json();assert (await post(own,'/me/hours/requests',dict(title='Помощь в мастерской',service_date=date.today().isoformat(),requested_minutes=125),'request')).json()['id']==manual['id']
        assert (await own.get('/api/v1/me/hours')).json()['total_minutes']==0
        reviewed=await post(reviewer,f"/coord/hours/requests/{manual['id']}/review",dict(expected_version=1,decision='approved',approved_minutes=125,reason='Проверено координатором'))
        assert reviewed.status_code==200,reviewed.text
        document=await post(own,'/me/profile/documents',dict(kind='certificate',period_from=date.today().isoformat(),period_to=date.today().isoformat(),recipient='По месту требования'),'document')
        assert document.status_code==200,document.text
        value=document.json();assert value['total_minutes']==125 and value['state']=='ready'
        content=await own.get('/api/v1/assets/'+value['asset_id']+'/content');assert content.status_code==200,content.text
        extracted='\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(content.content)).pages)
        assert '125 минут' in extracted and '2 ч 05 мин' in extracted and date.today().strftime('%d.%m.%Y') in extracted
        assert (await other.get('/api/v1/assets/'+value['asset_id']+'/content')).status_code==404
        corrected=await post(reviewer,f"/coord/hours/requests/{manual['id']}/review",dict(expected_version=2,decision='approved',approved_minutes=60,reason='Уточнено время работы'))
        assert corrected.status_code==200,corrected.text
        hours=(await own.get('/api/v1/me/hours')).json();assert hours['total_minutes']==60 and sorted(e['delta_minutes'] for e in hours['entries'])==[-65,125]
        assert hours['confirmed_assignments']==0 and not any(a['earned'] for a in hours['achievements'])
        async with factory() as db:
            grants=(await db.scalars(select(PermissionGrant).where(PermissionGrant.permission=='hours.review'))).all()
            for grant in grants:grant.revoked_at=__import__('app.core.clock',fromlist=['utcnow']).utcnow()
            await db.commit()
        assert (await post(reviewer,f"/coord/hours/requests/{manual['id']}/review",dict(expected_version=2,decision='approved',approved_minutes=60,reason='Уточнено время работы'))).status_code==403
    finally:await own.aclose();await other.aclose();await reviewer.aclose()

@pytest.mark.asyncio
async def test_suggestion_diff_accept_revert_and_stale_version(env):
    app,factory=env;own=await volunteer(app,factory)
    try:
        assert (await put(own,update())).status_code==200
        principal=await principal_for(own,factory)
        async with factory() as db:
            snap=await public_snapshot(db,principal);assert set(snap['fields'])=={'about','skills','interests'} and 'contacts' not in str(snap)
            suggestion=await create_suggestion(db,principal,expected_profile_version=1,patch={'about':'Рисую акварелью и помогаю в мастерской','skills':['Акварель','Керамика']},source_refs=[{'source_id':str(uuid4()),'version':1,'fragment':'Рассказала о занятиях керамикой'}],producer={'model':'contract-fixture','prompt_version':'1','run_id':str(uuid4())});await db.commit()
        decision=await post(own,f'/me/profile/suggestions/{suggestion.id}/decision',dict(expected_version=1,decision='accept'),'accept')
        assert decision.status_code==200,decision.text
        assert (await post(own,f'/me/profile/suggestions/{suggestion.id}/decision',dict(expected_version=1,decision='accept'),'accept')).json()==decision.json()
        profile=(await own.get('/api/v1/me/profile')).json();assert profile['version']==2 and next(t for t in profile['tags'] if t['label']=='Керамика')['level']=='learn'
        reverted=await post(own,f'/me/profile/suggestions/{suggestion.id}/decision',dict(expected_version=2,decision='revert'));assert reverted.status_code==200,reverted.text
        restored=(await own.get('/api/v1/me/profile')).json();assert restored['version']==3 and restored['about']=='Рисую акварелью' and len(restored['revisions'])==3
        async with factory() as db:
            with pytest.raises(ApiError):await create_suggestion(db,principal,expected_profile_version=1,patch={'about':'Старый текст'},source_refs=[{}],producer={})
    finally:await own.aclose()

@pytest.mark.asyncio
async def test_consents_export_and_deletion_request_workflow(env):
    app,factory=env;own=await volunteer(app,factory);other=await volunteer(app,factory);reviewer=await coord(app,factory)
    try:
        consent=await post(own,'/me/profile/consents',dict(purpose='news',granted=True,document_version='4'));assert consent.status_code==200,consent.text
        principal=await principal_for(own,factory)
        async with factory() as db:assert await newsletter_consent(db,principal.foundation_id,principal.user_id)
        unsubscribe=await post(own,'/me/profile/consents',dict(purpose='news',granted=False,document_version='1'));assert unsubscribe.status_code==200
        async with factory() as db:assert not await newsletter_consent(db,principal.foundation_id,principal.user_id)
        archive=await post(own,'/me/profile/data-requests',dict(kind='export'));assert archive.status_code==200,archive.text
        value=archive.json();assert value['state']=='ready'
        blob=await own.get('/api/v1/assets/'+value['asset_id']+'/content');assert blob.status_code==200,blob.text
        with zipfile.ZipFile(io.BytesIO(blob.content)) as z:data=json.loads(z.read('my-data.json'))
        assert data['profile']['user_id']==str(principal.user_id) and 'private_notes' not in str(data)
        assert (await other.get('/api/v1/assets/'+value['asset_id']+'/content')).status_code==404
        deletion=await post(own,'/me/profile/data-requests',dict(kind='deletion',reason='Хочу завершить участие'));assert deletion.status_code==200
        row=deletion.json()
        assert (await post(reviewer,f"/coord/profile/data-requests/{row['id']}/review",dict(expected_version=1,decision='completed',public_response='Готово'))).status_code==409
        accepted=await post(reviewer,f"/coord/profile/data-requests/{row['id']}/review",dict(expected_version=1,decision='approved',public_response='Запрос рассмотрен, согласуем сохраняемые факты',retention_note='Учёт подтверждённой помощи хранится по правилам фонда',scheduled_for=date.today().isoformat()));assert accepted.status_code==200,accepted.text
        cancelled=await post(own,f"/me/profile/data-requests/{row['id']}/cancel",dict(expected_version=2));assert cancelled.status_code==200,cancelled.text
        assert (await own.get('/api/v1/me/profile')).status_code==200
    finally:await own.aclose();await other.aclose();await reviewer.aclose()

async def attendance_fixture(factory,user_id,day=None,minutes=120,multiplier=1):
    from app.core.clock import utcnow
    from app.modules.activities.models import VolunteerRole,VolunteerRoleVersion
    from app.modules.activities.calendar_models import EventSeries,EventOccurrence,StaffingNeed
    from app.modules.activities.assignment_models import Assignment,Attendance,AttendanceEvent
    foundation_id=get_settings().foundation_id;day=day or date.today()-timedelta(days=1)
    async with factory() as db:
        role=VolunteerRole(foundation_id=foundation_id,title='Мастерская',normalized_title='мастерская-'+str(uuid4()),task='',updated_by='fixture');db.add(role);await db.flush()
        role_version=VolunteerRoleVersion(role_id=role.id,version=1,snapshot={},actor_id='fixture');db.add(role_version)
        series=EventSeries(foundation_id=foundation_id,anchor_date=day,origin_time=time(12),start_date=day,start_time=time(12),duration_minutes=120,recurrence={},title='Занятие',updated_by='fixture');db.add(series);await db.flush()
        occurrence=EventOccurrence(id=uuid4(),foundation_id=foundation_id,series_id=series.id,origin_local_date=day,origin_local_time=time(12),starts_at=datetime.combine(day,time(9),tzinfo=timezone.utc),ends_at=datetime.combine(day,time(11),tzinfo=timezone.utc),timezone='Europe/Moscow',title='Занятие',series_version=1,updated_by='fixture');db.add(occurrence);await db.flush()
        need=StaffingNeed(foundation_id=foundation_id,occurrence_id=occurrence.id,role_id=role.id,role_version_id=role_version.id,capacity_required=1);db.add(need);await db.flush()
        assignment=Assignment(foundation_id=foundation_id,user_id=user_id,occurrence_id=occurrence.id,staffing_need_id=need.id,status='confirmed',confirmed_at=utcnow()-timedelta(days=2),conditions_version=1,conditions_snapshot={},points_multiplier=multiplier);db.add(assignment);await db.flush()
        attendance=Attendance(foundation_id=foundation_id,assignment_id=assignment.id,outcome='attended',minutes=minutes,version=1);db.add(attendance);await db.flush()
        event=AttendanceEvent(foundation_id=foundation_id,attendance_id=attendance.id,assignment_id=assignment.id,user_id=user_id,version=1,old_minutes=0,new_minutes=minutes,reason='Подтверждено посещение',actor_id='fixture');db.add(event);await db.flush();await db.commit()
        return assignment.id,attendance.id,event.id

@pytest.mark.asyncio
async def test_actual_attendance_projection_once_and_correction_delta(env):
    from app.modules.activities.assignment_models import AttendanceEvent
    app,factory=env;own=await volunteer(app,factory);principal=await principal_for(own,factory)
    try:
        assignment_id,attendance_id,event_id=await attendance_fixture(factory,principal.user_id)
        async def consume():
            async with factory() as db:
                row=await append_service_time(db,principal,principal.user_id,assignment_id,event_id);await db.commit();return row.id
        one,two=await asyncio.gather(consume(),consume());assert one==two
        async with factory() as db:
            correction=AttendanceEvent(foundation_id=principal.foundation_id,attendance_id=attendance_id,assignment_id=assignment_id,user_id=principal.user_id,version=2,old_minutes=120,new_minutes=0,reason='Исправлена ошибочная отметка',actor_id='fixture');db.add(correction);await db.flush()
            with pytest.raises(ApiError):await append_service_time(db,principal,principal.user_id,assignment_id,correction.id,delta_minutes=120)
            row=await append_service_time(db,principal,principal.user_id,assignment_id,correction.id,delta_minutes=-120)
            assert row.delta_minutes==-120 and correction.ledger_state=='posted';await db.commit()
            assert await db.scalar(select(func.count()).select_from(ServiceTimeEntry))==2
        hours=(await own.get('/api/v1/me/hours')).json();assert hours['total_minutes']==0 and hours['confirmed_assignments']==0 and hours['ledger_pending']==0
    finally:await own.aclose()

@pytest.mark.asyncio
async def test_month_milestone_requires_all_actual_confirmed_visits(env):
    from app.modules.activities.assignment_models import AttendanceEvent,Attendance
    app,factory=env;own=await volunteer(app,factory);principal=await principal_for(own,factory)
    try:
        facts=[]
        for offset in (40,33,26,19):
            assignment_id,attendance_id,event_id=await attendance_fixture(factory,principal.user_id,date.today()-timedelta(days=offset));facts.append((assignment_id,attendance_id,event_id))
            async with factory() as db:await append_service_time(db,principal,principal.user_id,assignment_id,event_id);await db.commit()
        hours=(await own.get('/api/v1/me/hours')).json();assert next(a for a in hours['achievements'] if a['key']=='month')['earned']
        assignment_id,attendance_id,_=facts[1]
        async with factory() as db:
            attendance=await db.get(Attendance,attendance_id);attendance.outcome='absent';attendance.minutes=0;attendance.version=2
            correction=AttendanceEvent(foundation_id=principal.foundation_id,attendance_id=attendance_id,assignment_id=assignment_id,user_id=principal.user_id,version=2,old_minutes=120,new_minutes=0,reason='Проверено отсутствие',actor_id='fixture');db.add(correction);await db.flush();await append_service_time(db,principal,principal.user_id,assignment_id,correction.id);await db.commit()
        hours=(await own.get('/api/v1/me/hours')).json();assert not next(a for a in hours['achievements'] if a['key']=='month')['earned']
    finally:await own.aclose()

@pytest.mark.asyncio
async def test_gratitude_uses_actual_confirmed_basis_and_rejects_invalidated_time(env):
    app,factory=env;own=await volunteer(app,factory);reviewer=await coord(app,factory)
    try:
        request=(await post(own,'/me/hours/requests',dict(title='Помощь на ярмарке',service_date=date.today().isoformat(),requested_minutes=90))).json()
        approved=await post(reviewer,f"/coord/hours/requests/{request['id']}/review",dict(expected_version=1,decision='approved',approved_minutes=90,reason='Проверена помощь на ярмарке'));assert approved.status_code==200
        bases=(await reviewer.get('/api/v1/coord/profile/recognition-bases')).json();assert bases[0]['confirmed_minutes']==90
        basis=bases[0];thank=await post(reviewer,'/coord/gratitudes',dict(user_id=basis['user_id'],basis_entry_id=basis['entry_id'],text='Спасибо за помощь на ярмарке'));assert thank.status_code==200,thank.text
        assert (await own.get('/api/v1/me/hours')).json()['gratitudes'][0]['basis_current']
        rejected=await post(reviewer,f"/coord/hours/requests/{request['id']}/review",dict(expected_version=2,decision='rejected',approved_minutes=0,reason='Исправлено ошибочное подтверждение'));assert rejected.status_code==200
        assert not (await own.get('/api/v1/me/hours')).json()['gratitudes'][0]['basis_current']
        assert (await reviewer.get('/api/v1/coord/profile/recognition-bases')).json()==[]
        assert (await post(reviewer,'/coord/gratitudes',dict(user_id=basis['user_id'],basis_entry_id=basis['entry_id'],text='Повтор без подтверждённого основания'))).status_code==409
    finally:await own.aclose();await reviewer.aclose()

@pytest.mark.asyncio
async def test_matching_context_is_self_selected_and_has_actual_version_provenance(env):
    from app.modules.profile.service import matching_context
    from app.modules.crm.service import save_own_availability
    from app.modules.crm.schemas import SelfAvailabilityCommand
    app,factory=env;own=await volunteer(app,factory);other=await volunteer(app,factory)
    try:
        values=update();values['tags']+=[dict(kind='interest',label='Керамика',level='learn')];values['lifecycle']='paused'
        saved=await put(own,values);assert saved.status_code==200,saved.text
        principal=await principal_for(own,factory);another=await principal_for(other,factory)
        async with factory() as db:
            await save_own_availability(db,principal,SelfAvailabilityCommand(expected_version=0,summary='Суббота днём',preferred_channel='email',windows=[dict(weekday=5,start_minute=720,end_minute=900)]));await db.commit()
        async with factory() as db:
            context=await matching_context(db,principal)
            assert context['profile_version']==1 and context['paused'] and not context['no_contact']
            assert context['skills']==[dict(label='Акварель',normalized='акварель',level='sure')]
            assert context['interests'][0]['label']=='Керамика' and context['availability']['windows'][0]['weekday']==5
            assert context['evidence'][-1]['field']=='availability' and context['evidence'][-1]['version']==1
            assert 'contacts' not in context and 'email' not in str(context) and 'about' not in context
            blank=await matching_context(db,another);assert blank['profile_version']==0 and blank['skills']==[] and blank['availability'] is None
            from app.modules.crm.models import CrmVolunteer
            from app.modules.profile.models import VolunteerProfile
            assert await db.scalar(select(func.count()).select_from(CrmVolunteer))==1
            stored=await db.get(VolunteerProfile,principal.user_id);stored.paused_until=date.today()-timedelta(days=1);await db.flush()
            assert not (await matching_context(db,principal))['paused']
    finally:await own.aclose();await other.aclose()

def test_profile_calendar_day_uses_moscow_at_utc_boundary(monkeypatch):
    from app.modules.profile import dates
    monkeypatch.setattr(dates,'utcnow',lambda:datetime(2026,10,20,22,30,tzinfo=timezone.utc))
    assert dates.local_today()==date(2026,10,21)

@pytest.mark.asyncio
async def test_producer_run_is_idempotent_and_never_recreates_rejected_proposal(env):
    from app.modules.profile.service import ai_snapshot,suggestion_for_run
    app,factory=env;own=await volunteer(app,factory)
    try:
        assert (await put(own,update())).status_code==200
        p=await principal_for(own,factory);run_id=str(uuid4());payload=dict(expected_profile_version=1,patch={'about':'Предложенный текст'},source_refs=[dict(source_id=str(uuid4()),version=1,fragment='Источник')],producer=dict(run_id=run_id,model='contract-fixture',prompt_version='1'))
        async def deliver():
            async with factory() as db:
                proposal=await create_suggestion(db,p,**payload);await db.commit();return proposal
        one,two=await asyncio.gather(deliver(),deliver());assert one.id==two.id
        rejected=await post(own,f'/me/profile/suggestions/{one.id}/decision',dict(expected_version=1,decision='reject'));assert rejected.status_code==200
        assert (await put(own,update(1))).status_code==200
        async with factory() as db:
            assert (await ai_snapshot(db,p,lock=True))['version']==2
            replay=await create_suggestion(db,p,**payload);assert replay.id==one.id and replay.state=='rejected'
            assert (await suggestion_for_run(db,p,run_id)).id==one.id
            assert await db.scalar(select(func.count()).select_from(ProfileChangeSuggestion))==1
            with pytest.raises(ApiError):await create_suggestion(db,p,**dict(payload,patch={'about':'Подменённый результат'}))
    finally:await own.aclose()

@pytest.mark.asyncio
async def test_ai_snapshot_refreshes_cached_profile_after_owner_lock(env):
    from app.modules.profile.service import ai_snapshot
    from app.modules.profile.models import VolunteerProfile
    app,factory=env;own=await volunteer(app,factory)
    try:
        assert (await put(own,update())).status_code==200
        p=await principal_for(own,factory)
        async with factory() as db:
            cached=await db.get(VolunteerProfile,p.user_id);assert cached.version==1
            changed=update(1);changed['about']='Новый текст после сохранения';assert (await put(own,changed)).status_code==200
            fresh=await ai_snapshot(db,p,lock=True);assert fresh['version']==2 and fresh['fields']['about']=='Новый текст после сохранения'
            with pytest.raises(ApiError):await create_suggestion(db,p,expected_profile_version=2,patch={'about':'Предложение'},source_refs=[dict(source_id=str(uuid4()),version=2,fragment='public_profile')],producer=dict(run_id=str(uuid4()),model='contract-fixture',prompt_version='1'))
    finally:await own.aclose()

def png_bytes():
    from PIL import Image
    buffer=io.BytesIO();Image.new('RGB',(4,4),(240,200,60)).save(buffer,format='PNG');return buffer.getvalue()

@pytest.mark.asyncio
async def test_levels_and_points_follow_ledger_with_multiplier_and_corrections(env):
    from app.modules.activities.assignment_models import AttendanceEvent,Attendance
    app,factory=env;own=await volunteer(app,factory);reviewer=await coord(app,factory);principal=await principal_for(own,factory)
    try:
        hours=(await own.get('/api/v1/me/hours')).json()
        assert hours['level']['key'] is None and hours['level']['next_title']=='Первые шаги' and hours['points']['balance']==0 and not hours['points']['can_request']
        assignment_id,attendance_id,event_id=await attendance_fixture(factory,principal.user_id,minutes=90,multiplier=1.5)
        async with factory() as db:await append_service_time(db,principal,principal.user_id,assignment_id,event_id);await db.commit()
        hours=(await own.get('/api/v1/me/hours')).json()
        assert hours['level']['key']=='first_steps' and hours['level']['next_title']=='В команде' and hours['level']['next_minutes']==1200
        assert [(s['key'],s['reached'],s['current']) for s in hours['level']['steps']]==[('first_steps',True,True),('team',False,False),('friend',False,False),('pillar',False,False)]
        assert hours['points']['balance']==23 and hours['points']['history'][0]['multiplier']==1.5
        request=(await post(own,'/me/hours/requests',dict(title='Помощь на ярмарке',service_date=date.today().isoformat(),requested_minutes=1200))).json()
        assert (await post(reviewer,f"/coord/hours/requests/{request['id']}/review",dict(expected_version=1,decision='approved',approved_minutes=1200,reason='Проверено координатором'))).status_code==200
        hours=(await own.get('/api/v1/me/hours')).json()
        assert hours['total_minutes']==1290 and hours['level']['key']=='team' and not hours['level']['letter_hint'] and hours['points']['balance']==223
        async with factory() as db:
            attendance=await db.get(Attendance,attendance_id);attendance.minutes=60;attendance.version=2
            correction=AttendanceEvent(foundation_id=principal.foundation_id,attendance_id=attendance_id,assignment_id=assignment_id,user_id=principal.user_id,version=2,old_minutes=90,new_minutes=60,reason='Уточнено время',actor_id='fixture');db.add(correction);await db.flush()
            await append_service_time(db,principal,principal.user_id,assignment_id,correction.id);await db.commit()
            kinds=set((await db.scalars(select(ServiceTimeEntry.source_kind))).all());assert kinds=={'attendance','manual_review'}
        hours=(await own.get('/api/v1/me/hours')).json()
        assert hours['points']['balance']==215 and [item['points'] for item in hours['points']['history'] if item['kind']=='attendance']==[15]
        for minutes in (1440,1440,1440,1440):
            row=(await post(own,'/me/hours/requests',dict(title='Мастерская',service_date=date.today().isoformat(),requested_minutes=minutes))).json()
            assert (await post(reviewer,f"/coord/hours/requests/{row['id']}/review",dict(expected_version=1,decision='approved',approved_minutes=minutes,reason='Проверено'))).status_code==200
        hours=(await own.get('/api/v1/me/hours')).json();assert hours['level']['key']=='pillar' and hours['level']['letter_hint'] and hours['level']['next_title'] is None
    finally:await own.aclose();await reviewer.aclose()

@pytest.mark.asyncio
async def test_introduction_bonus_is_paid_once_across_releases(env):
    from app.core.clock import utcnow
    from app.modules.learning.seed import seed_introduction
    from app.modules.learning.models import LearningAssignment,LearningRelease
    from app.modules.profile.models import PointsEntry
    app,factory=env;own=await volunteer(app,factory);principal=await principal_for(own,factory)
    try:
        async with factory() as db:
            track_id=await seed_introduction(db,principal.foundation_id);await db.commit()
            releases=(await db.scalars(select(LearningRelease).where(LearningRelease.track_id==track_id).order_by(LearningRelease.number))).all();assert len(releases)>=2
            db.add(LearningAssignment(foundation_id=principal.foundation_id,release_id=releases[0].id,user_id=principal.user_id,completed_at=utcnow()-timedelta(days=30),acknowledged_at=utcnow()-timedelta(days=30)));await db.commit()
        first=(await own.get('/api/v1/me/hours')).json()['points'];assert first['balance']==100 and first['history'][0]['kind']=='bonus'
        async with factory() as db:
            db.add(LearningAssignment(foundation_id=principal.foundation_id,release_id=releases[-1].id,user_id=principal.user_id,completed_at=utcnow(),acknowledged_at=utcnow()));await db.commit()
        prize=(await post(await coord(app,factory),'/coord/prizes',dict(title='Открытка мастерской',price_points=10,stock=5))).json()
        assert (await post(own,'/me/prize-requests',dict(prize_id=prize['id']))).status_code==200
        assert (await own.get('/api/v1/me/hours')).json()['points']['earned']==100
        async with factory() as db:assert await db.scalar(select(func.count()).select_from(PointsEntry))==1
    finally:await own.aclose()

@pytest.mark.asyncio
async def test_prize_catalog_requests_reserve_points_and_review_rules(env):
    app,factory=env;own=await volunteer(app,factory);reviewer=await coord(app,factory);second=await coord(app,factory);principal=await principal_for(own,factory);reviewer_principal=await principal_for(reviewer,factory)
    try:
        assert (await post(own,'/coord/prizes',dict(title='Чашка',price_points=100,stock=1))).status_code==403
        created=await post(reviewer,'/coord/prizes',dict(title='Чашка из мастерской',description='Ручная работа',price_points=100,stock=1));assert created.status_code==200,created.text
        prize=created.json();hidden=(await post(reviewer,'/coord/prizes',dict(title='Скрытый',price_points=10,stock=3,visible=False))).json()
        assert [row['id'] for row in (await own.get('/api/v1/prizes')).json()]==[prize['id']]
        assert (await post(own,'/me/prize-requests',dict(prize_id=hidden['id']))).status_code==404
        denied=await post(own,'/me/prize-requests',dict(prize_id=prize['id']));assert denied.status_code==409 and denied.json()['code']=='points_insufficient'
        assert (await post(reviewer,'/coord/points/adjustments',dict(user_id=str(reviewer_principal.user_id),points=500,reason='Себе'))).status_code==403
        assert (await post(reviewer,'/coord/points/adjustments',dict(user_id=str(principal.user_id),points=150,reason='Помощь на выезде без отметки'))).status_code==200
        key=str(uuid4());one,two=await asyncio.gather(post(own,'/me/prize-requests',dict(prize_id=prize['id']),key),post(own,'/me/prize-requests',dict(prize_id=prize['id']),key))
        assert one.status_code==two.status_code==200 and one.json()==two.json(),one.text
        claim=one.json();points=(await own.get('/api/v1/me/hours')).json()['points'];assert points['balance']==50 and points['reserved']==100
        assert (await post(own,'/me/prize-requests',dict(prize_id=prize['id']))).json()['code']=='prize_out_of_stock'
        cancelled=await post(own,f"/me/prize-requests/{claim['id']}/cancel",dict(expected_version=1));assert cancelled.status_code==200 and cancelled.json()['state']=='cancelled'
        assert (await own.get('/api/v1/prizes')).json()[0]['stock']==1 and (await own.get('/api/v1/me/hours')).json()['points']['balance']==150
        claim=(await post(own,'/me/prize-requests',dict(prize_id=prize['id']))).json()
        assert (await post(reviewer,f"/coord/prize-requests/{claim['id']}/decision",dict(expected_version=1,decision='rejected',reason='x'))).status_code==422
        issued=await post(reviewer,f"/coord/prize-requests/{claim['id']}/decision",dict(expected_version=1,decision='issued'));assert issued.status_code==200 and issued.json()['state']=='issued',issued.text
        assert (await post(own,f"/me/prize-requests/{claim['id']}/cancel",dict(expected_version=2))).status_code==409
        assert (await post(reviewer,'/coord/points/adjustments',dict(user_id=str(principal.user_id),points=-120,reason='Исправлена ошибочная отметка'))).status_code==200
        points=(await own.get('/api/v1/me/hours')).json()['points'];assert points['balance']==-70 and points['spent']==100 and not points['can_request']
        assert (await own.get('/api/v1/me/prize-requests')).json()[0]['state']=='issued'
        assert (await post(second,'/coord/points/adjustments',dict(user_id=str(reviewer_principal.user_id),points=50,reason='Помощь на ярмарке'))).status_code==200
        own_claim=(await post(reviewer,'/me/prize-requests',dict(prize_id=hidden['id'])))
        assert own_claim.status_code==404
        updated=await client_put(reviewer,f"/coord/prizes/{hidden['id']}",dict(expected_version=1,title='Скрытый',price_points=10,stock=3,visible=True));assert updated.status_code==200,updated.text
        own_claim=(await post(reviewer,'/me/prize-requests',dict(prize_id=hidden['id']))).json()
        forbidden=await post(reviewer,f"/coord/prize-requests/{own_claim['id']}/decision",dict(expected_version=1,decision='issued'));assert forbidden.status_code==403 and forbidden.json()['code']=='self_prize_review_forbidden'
        queue=(await second.get('/api/v1/coord/prize-requests')).json();assert {row['state'] for row in queue}=={'requested','issued','cancelled'}
    finally:await own.aclose();await reviewer.aclose();await second.aclose()

async def client_put(client,path,body):return await client.put('/api/v1'+path,json=body,headers={'Idempotency-Key':str(uuid4())})

@pytest.mark.asyncio
async def test_prize_photo_purpose_is_staff_bound_and_visible_through_catalog(env):
    import hashlib
    app,factory=env;own=await volunteer(app,factory);reviewer=await coord(app,factory)
    try:
        prize=(await post(reviewer,'/coord/prizes',dict(title='Приглашение на праздник',price_points=50,stock=10))).json()
        assert (await own.get(f"/api/v1/prizes/{prize['id']}/photo")).status_code==404
        data=png_bytes();body=dict(content_type='image/png',expected_size=len(data),checksum=hashlib.sha256(data).hexdigest())
        assert (await post(own,f"/coord/prizes/{prize['id']}/photo-intents",body)).status_code==403
        intent=await post(reviewer,f"/coord/prizes/{prize['id']}/photo-intents",body);assert intent.status_code==200,intent.text
        asset=intent.json()
        assert (await own.patch(f"/api/v1/assets/{asset['id']}/upload",content=data,headers={'X-Upload-Offset':'0'})).status_code==404
        assert (await reviewer.patch(f"/api/v1/assets/{asset['id']}/upload",content=data,headers={'X-Upload-Offset':'0'})).status_code==200
        assert (await reviewer.post(f"/api/v1/assets/{asset['id']}/complete-upload")).json()['state']=='ready'
        other=(await post(reviewer,'/coord/prizes',dict(title='Другой',price_points=5,stock=1))).json()
        assert (await client_put(reviewer,f"/coord/prizes/{other['id']}",dict(expected_version=1,title='Другой',price_points=5,stock=1,photo_asset_id=asset['id']))).status_code==422
        saved=await client_put(reviewer,f"/coord/prizes/{prize['id']}",dict(expected_version=1,title=prize['title'],price_points=50,stock=10,photo_asset_id=asset['id']));assert saved.status_code==200,saved.text
        photo=await own.get(f"/api/v1/prizes/{prize['id']}/photo");assert photo.status_code==200 and photo.content==data
        assert (await own.get(f"/api/v1/assets/{asset['id']}/content")).status_code==404
@pytest.mark.asyncio
async def test_review_queues_keep_actionable_rows_ahead_of_settled_history(env):
    from app.core.clock import utcnow
    from app.modules.profile.models import ManualTimeRequest,ProfileDocument,ProfileDataRequest
    app,factory=env;own=await volunteer(app,factory);reviewer=await coord(app,factory)
    try:
        deletion=(await post(own,'/me/profile/data-requests',dict(kind='deletion',reason='Хочу завершить участие'))).json()
        letter=(await post(own,'/me/profile/documents',dict(kind='letter',period_from=date.today().isoformat(),period_to=date.today().isoformat(),recipient='Для университета'))).json()
        hours=(await post(own,'/me/hours/requests',dict(title='Помощь в мастерской',service_date=date.today().isoformat(),requested_minutes=60))).json()
        p=await principal_for(own,factory)
        async with factory() as db:
            for index in range(201):
                later=utcnow()+timedelta(minutes=1,seconds=index)
                db.add_all([ProfileDataRequest(foundation_id=p.foundation_id,user_id=p.user_id,kind='export',state='ready',created_at=later),ProfileDocument(foundation_id=p.foundation_id,user_id=p.user_id,kind='certificate',period_from=date.today(),period_to=date.today(),recipient='Архив',state='ready',created_at=later),ManualTimeRequest(foundation_id=p.foundation_id,user_id=p.user_id,title='Решено',service_date=date.today(),requested_minutes=60,approved_minutes=60,state='approved',created_at=later)])
            await db.commit()
        for path,row in [('/coord/profile/data-requests',deletion),('/coord/profile/documents',letter),('/coord/hours/requests',hours)]:
            queue=(await reviewer.get('/api/v1'+path)).json();assert len(queue)==200 and queue[0]['id']==row['id'],path
    finally:await own.aclose();await reviewer.aclose()
