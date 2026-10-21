import io
import os
import zipfile
from datetime import date,timedelta
from uuid import UUID,uuid4
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport,AsyncClient
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.core.db import Base,get_db
from app.core.config import get_settings
from app.core.errors import ApiError,install_error_handlers
from app.core.models import Foundation,User,PermissionGrant,StaffMembership,OutboxMessage
from app.modules.auth.router import router as auth_router
from app.modules.applications.router import router as applications_router
from app.modules.applications.tests.test_applications import actor,staff,post,body
from app.modules.crm.router import router
from app.modules.crm.models import CrmVolunteer,FollowUpTask,FollowUpSource,ImportEffect,Agreement,ContactEvent
from app.modules.crm.imports import parse_upload
from app.modules.crm.service import schedule_follow_up,today

@pytest_asyncio.fixture
async def env():
    url=os.environ.get('OPORA_CRM_TEST_DATABASE_URL','')
    if not url:pytest.skip('Set dedicated OPORA_CRM_TEST_DATABASE_URL')
    if not url.endswith('/opora_crm_test'):raise RuntimeError('Dedicated CRM DB required')
    engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all);await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:db.add(Foundation(id=get_settings().foundation_id,name='Тестовый фонд'));await db.commit()
    app=FastAPI();install_error_handlers(app);app.include_router(auth_router);app.include_router(applications_router);app.include_router(router)
    async def override_db():
        async with factory() as db:
            try:yield db
            except BaseException:await db.rollback();raise
    app.dependency_overrides[get_db]=override_db
    yield app,factory
    await engine.dispose()

async def coordinator(app,factory):return await staff(app,factory,('crm.read','crm.write','contacts.review','candidates.read'))
async def put(client,path,payload):return await client.put('/api/v1'+path,json=payload,headers={'Idempotency-Key':str(uuid4())})
async def upload(client,content,filename='old.csv',key=None):
    return await client.post('/api/v1/coord/import-batches/upload',content=content,headers={'Idempotency-Key':key or str(uuid4()),'X-Filename':filename,'Content-Type':'application/octet-stream'})
async def prepare(client,content,mapping=None,filename='old.csv'):
    response=await upload(client,content,filename);assert response.status_code==200,response.text
    batch=response.json()
    mapped=await post(client,f"/coord/import-batches/{batch['id']}/map",dict(expected_version=batch['version'],source_system='legacy_fixture',mapping=mapping or {'name':'Имя','email':'Почта','external_id':'ID','no_contact':'Не связываться'}));assert mapped.status_code==200,mapped.text
    batch=mapped.json()
    preview=await post(client,f"/coord/import-batches/{batch['id']}/dry-run",dict(expected_version=batch['version']));assert preview.status_code==200,preview.text
    return preview.json()
CSV='ID;Имя;Почта;Не связываться\nold-1;Тест Анна;anna-old@example.test;нет\nold-2;Тест Борис;boris-old@example.test;да\n'.encode()


def test_real_xlsx_and_expansion_guards():
    from openpyxl import Workbook
    book=Workbook();sheet=book.active;sheet.append(['Имя','Почта']);sheet.append(['Тест','test@example.test']);stream=io.BytesIO();book.save(stream)
    columns,rows=parse_upload(stream.getvalue(),'contacts.xlsx');assert columns==['Имя','Почта'] and rows[0][1]['Имя']=='Тест'
    sheet['A2']='=1+1';stream=io.BytesIO();book.save(stream)
    with pytest.raises(ApiError) as error:parse_upload(stream.getvalue(),'formulas.xlsx')
    assert error.value.code=='xlsx_formulas_not_supported'
    bomb=io.BytesIO()
    with zipfile.ZipFile(bomb,'w',compression=zipfile.ZIP_DEFLATED) as archive:archive.writestr('xl/worksheets/sheet1.xml','A'*(2*1024*1024))
    with pytest.raises(ApiError) as error:parse_upload(bomb.getvalue(),'bomb.xlsx')
    assert error.value.code=='xlsx_expansion_limit'

@pytest.mark.asyncio
async def test_staged_import_no_identity_or_delivery_and_readiness(env):
    app,factory=env;coord=await coordinator(app,factory);public=await actor(app)
    try:
        assert (await public.get('/api/v1/coord/volunteers')).status_code==403
        batch=await prepare(coord,CSV)
        assert batch['counts']=={'create':2}
        async with factory() as db:assert await db.scalar(select(func.count()).select_from(CrmVolunteer))==0
        applied=await post(coord,f"/coord/import-batches/{batch['id']}/apply",dict(expected_version=batch['version']));assert applied.status_code==200,applied.text
        batch=applied.json();ids=[row['volunteer_id'] for row in batch['rows']]
        repeat=await post(coord,f"/coord/import-batches/{batch['id']}/apply",dict(expected_version=1));assert repeat.status_code==200,repeat.text
        assert (await upload(coord,CSV)).json()['id']==batch['id']
        first=(await coord.get('/api/v1/coord/volunteers/'+ids[0])).json();second=(await coord.get('/api/v1/coord/volunteers/'+ids[1])).json()
        assert first['relationship_state']=='unverified' and not first['can_invite']
        assert second['no_contact'] and not second['can_invite']
        bad=await post(coord,f"/coord/contact-reviews/{ids[0]}/record",dict(expected_version=1,outcome='ready',note='Готов'))
        assert bad.status_code==422,bad.text
        valid_until=(today()+timedelta(days=14)).isoformat()
        ready=await post(coord,f"/coord/contact-reviews/{ids[0]}/record",dict(expected_version=1,outcome='ready',note='Уточнено лично',availability={'summary':'Суббота днём','preferred_channel':'email','windows':[{'weekday':5,'start_minute':720,'end_minute':900}]},valid_until=valid_until,agreement_text='Согласовали помощь на занятии'))
        assert ready.status_code==200,ready.text
        assert ready.json()['can_invite'] and ready.json()['availability']['verified']
        changed=await put(coord,f"/coord/volunteers/{ids[0]}/availability",dict(expected_version=ready.json()['version'],summary='Теперь по воскресеньям',preferred_channel='email',windows=[]))
        assert changed.status_code==200,changed.text
        assert not changed.json()['can_invite'] and not changed.json()['availability']['verified']
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(ImportEffect))==2
            assert await db.scalar(select(func.count()).select_from(User))==1 # coordinator only
            assert await db.scalar(select(func.count()).select_from(OutboxMessage))==0
    finally:await coord.aclose();await public.aclose()

@pytest.mark.asyncio
async def test_duplicate_review_manual_resolution_and_merge_preserve_history(env):
    app,factory=env;coord=await coordinator(app,factory)
    try:
        batch=await prepare(coord,CSV)
        applied=(await post(coord,f"/coord/import-batches/{batch['id']}/apply",dict(expected_version=batch['version']))).json();first,second=[row['volunteer_id'] for row in applied['rows']]
        duplicate=await prepare(coord,'ID;Имя;Почта;Не связываться\nnew-id;Тест дубль;anna-old@example.test;нет\n'.encode())
        assert duplicate['rows'][0]['decision']=='review'
        assert (await post(coord,f"/coord/import-batches/{duplicate['id']}/apply",dict(expected_version=duplicate['version']))).status_code==422
        resolved=await post(coord,f"/coord/import-batches/{duplicate['id']}/rows/{duplicate['rows'][0]['id']}/resolve",dict(expected_version=duplicate['version'],decision='link',volunteer_id=first,reason='Координатор проверил, это тот же исторический контакт'))
        assert resolved.status_code==200,resolved.text
        assert (await post(coord,f"/coord/import-batches/{duplicate['id']}/apply",dict(expected_version=resolved.json()['version']))).status_code==200
        # A merge retains all histories and strict no-contact from either record.
        merged=await post(coord,f"/coord/volunteers/{second}/merge",dict(expected_version=1,target_id=first,target_expected_version=1,reason='Фиктивный дубль проверен координатором'))
        assert merged.status_code==200,merged.text
        detail=merged.json();assert detail['no_contact'] and second in detail['merged_record_ids']
        assert len(detail['import_provenance'])==3 and len(detail['contact_events'])>=4
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
        key=str(uuid4());result=await upload(coord,CSV,key=key);assert result.status_code==200,result.text
        batch=result.json()
        async with factory() as db:
            grant=await db.scalar(select(PermissionGrant).where(PermissionGrant.permission=='crm.write'));grant.revoked_at=__import__('app.core.clock',fromlist=['utcnow']).utcnow();await db.commit()
        denied=await upload(coord,CSV,key=key);assert denied.status_code==403,denied.text
        async with factory() as db:
            other=Foundation(name='Чужой фонд');db.add(other);await db.flush()
            batch_row=await db.get(__import__('app.modules.crm.models',fromlist=['ImportBatch']).ImportBatch,UUID(batch['id']));batch_row.foundation_id=other.id;await db.commit()
        assert (await coord.get('/api/v1/coord/import-batches/'+batch['id'])).status_code==404
    finally:await coord.aclose()
