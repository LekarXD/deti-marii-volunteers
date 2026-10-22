import asyncio,hashlib,io,os
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import UUID,uuid4
import httpx,jwt,pytest
from PIL import Image
from sqlalchemy import select,text,func
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.core.db import Base
from app.core.auth import Principal
from app.core.models import Foundation,User,Session,StaffMembership,PermissionGrant,MediaAsset,Job
from app.core.errors import ApiError
from app.core.config import get_settings
from app.worker.registry import JobContext
from app.worker.queue import LeaseLost,complete
from app.modules.assets.router import complete_upload
from app.modules.assets.service import asset_path
from app.modules.studio import router as routes,service,jobs
from app.modules.studio.models import StudioSession,StudioSceneEvent,WebinarEnrollment,SlidePage
from app.modules.studio.schemas import WebinarInput,StudioVersionCommand,StudioSessionCreate,StudioSceneCommand,SlideUploadInput
from app.integrations.rtc.livekit import RtcSettings,LiveKitAdapter

@pytest.fixture
async def world(tmp_path,monkeypatch):
    url=os.environ.get('OPORA_STUDIO_TEST_DATABASE_URL') or os.environ.get('OPORA_TEST_DATABASE_URL')
    if not url:pytest.skip('Set disposable OPORA_STUDIO_TEST_DATABASE_URL')
    from app.core.model_loader import load_models
    from app.modules.activities import assignment_models
    load_models()
    schema='studio_'+uuid4().hex;admin=create_async_engine(url)
    async with admin.begin() as c:await c.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'));await c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine=create_async_engine(url,connect_args={'options':f'-csearch_path={schema}'});factory=async_sessionmaker(engine,expire_on_commit=False)
    async with engine.begin() as c:await c.run_sync(Base.metadata.create_all)
    async with factory() as db:
        foundation=Foundation(name='Studio fixture');db.add(foundation);await db.flush()
        host=User(foundation_id=foundation.id,display_name='Fixture Host');viewer=User(foundation_id=foundation.id,display_name='Fixture Viewer');db.add_all([host,viewer]);await db.flush()
        membership=StaffMembership(foundation_id=foundation.id,user_id=host.id);db.add(membership);await db.flush();db.add(PermissionGrant(membership_id=membership.id,permission='studio.manage'))
        sessions=[]
        for user in (host,viewer):
            session=Session(foundation_id=foundation.id,user_id=user.id,token_hash=uuid4().hex,csrf_hash=uuid4().hex,csrf_cipher='fixture',expires_at=datetime.now(timezone.utc)+timedelta(days=1),mfa_at=datetime.now(timezone.utc) if user.id==host.id else None);db.add(session);sessions.append(session)
        await db.flush();await db.commit()
        actors=[Principal(user.id,None,foundation.id,session.id,user.id==host.id,str(user.id),frozenset({'studio.manage'}) if user.id==host.id else frozenset(),(('studio.manage','foundation',None),) if user.id==host.id else ()) for user,session in zip((host,viewer),sessions)]
    monkeypatch.setattr(get_settings(),'asset_root',str(tmp_path))
    monkeypatch.setattr(RtcSettings,'from_env',classmethod(lambda cls:RtcSettings()))
    yield SimpleNamespace(factory=factory,host=actors[0],viewer=actors[1],foundation=foundation)
    await engine.dispose()
    async with admin.begin() as c:await c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await admin.dispose()

async def webinar(w):
    async with w.factory() as db:
        value=await routes.create_webinar(WebinarInput(title='Fixture class',starts_at=datetime.now(timezone.utc)+timedelta(days=1)),db,w.host,uuid4().hex)
    async with w.factory() as db:
        return await routes.publish_webinar(UUID(value['id']),StudioVersionCommand(expected_version=1),db,w.host,uuid4().hex)
async def prepare(w,webinar):
    async with w.factory() as db:return await routes.prepare(StudioSessionCreate(resource_kind='live_event',resource_id=webinar['id']),db,w.host,uuid4().hex)

@pytest.mark.asyncio
async def test_authoritative_prepare_noop_denied_and_scene_race(world):
    w=world;event=await webinar(w);session=await prepare(w,event);session_id=UUID(session['id'])
    assert session['state']=='prepared' and not session['capabilities']['configured']
    async with w.factory() as db:
        with pytest.raises(ApiError) as unavailable:await routes.start(session_id,StudioVersionCommand(expected_version=1),db,w.host,uuid4().hex)
        assert unavailable.value.code=='rtc_unavailable'
    async with w.factory() as db:assert (await db.get(StudioSession,session_id)).state=='prepared'
    async with w.factory() as db:
        with pytest.raises(ApiError):await routes.get_session(session_id,db,w.viewer)
    async def patch(camera):
        scene=dict(session['scene']);scene['presenter_camera']=camera
        async with w.factory() as db:return await routes.patch_scene(session_id,StudioSceneCommand(expected_revision=0,scene=scene),db,w.host,uuid4().hex)
    result=await asyncio.gather(patch(True),patch(False),return_exceptions=True)
    assert sum(isinstance(value,dict) for value in result)==1
    assert next(value for value in result if isinstance(value,ApiError)).code=='scene_revision_conflict'
    async with w.factory() as db:assert await db.scalar(select(func.count()).select_from(StudioSceneEvent).where(StudioSceneEvent.session_id==session_id))==2
    forged=dict(session['scene']);forged['foundation_id']=str(uuid4())
    async with w.factory() as db:
        with pytest.raises(ApiError) as bad:await routes.patch_scene(session_id,StudioSceneCommand(expected_revision=1,scene=forged),db,w.host,uuid4().hex)
        assert bad.value.code=='scene_scope_mismatch'

@pytest.mark.asyncio
async def test_live_requires_provider_host_ack_and_current_enrollment(world,monkeypatch):
    w=world;event=await webinar(w);session=await prepare(w,event);session_id=UUID(session['id']);seen=[];host_present=False
    settings=RtcSettings(url='https://rtc.example.test',api_key='fixture',api_secret='fixture-signing-secret-long-enough-for-tests',deployment='cloud')
    monkeypatch.setattr(RtcSettings,'from_env',classmethod(lambda cls:settings))
    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200,json={'sid':'RM_fixture'} if request.url.path.endswith('CreateRoom') else {'participants':[{'identity':'opora-u'+w.host.user_id.hex}] if host_present else []})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        monkeypatch.setattr(routes,'LiveKitAdapter',lambda:LiveKitAdapter(settings,client))
        async with w.factory() as db:opening=await routes.start(session_id,StudioVersionCommand(expected_version=1),db,w.host,uuid4().hex)
        assert opening['state']=='opening'
        async with w.factory() as db:
            with pytest.raises(ApiError):await routes.join(session_id,db,w.viewer)
        async with w.factory() as db:
            token=await routes.join(session_id,db,w.host)
            claims=jwt.decode(token['token'],settings.api_secret,algorithms=['HS256'])
            assert str(w.host.session_id) in claims['metadata']
        async with w.factory() as db:
            with pytest.raises(ApiError) as waiting:await routes.ready(session_id,StudioVersionCommand(expected_version=2),db,w.host,uuid4().hex)
            assert waiting.value.code=='host_not_connected'
        host_present=True
        async with w.factory() as db:live=await routes.ready(session_id,StudioVersionCommand(expected_version=2),db,w.host,uuid4().hex)
        assert live['state']=='live'
        async with w.factory() as db:await routes.enroll(UUID(event['id']),None,db,w.viewer,uuid4().hex)
        async with w.factory() as db:audience=await routes.join(session_id,db,w.viewer)
        assert audience['role']=='audience'
        async with w.factory() as db:await routes.withdraw(UUID(event['id']),StudioVersionCommand(expected_version=1),db,w.viewer,uuid4().hex)
        async with w.factory() as db:
            with pytest.raises(ApiError):await routes.join(session_id,db,w.viewer)
        assert jwt.decode(audience['token'],settings.api_secret,algorithms=['HS256'])['sub'].endswith(w.viewer.user_id.hex)
        async with w.factory() as db:
            pending=await db.scalar(select(Job).where(Job.kind=='studio.revoke'));assert pending and pending.payload['enrollment_version']==2

@pytest.mark.asyncio
async def test_source_bound_slide_processing_and_lease_fence(world):
    w=world;event=await webinar(w);stream=io.BytesIO();Image.new('RGB',(80,60),'#dbbe62').save(stream,'PNG');data=stream.getvalue()
    body=SlideUploadInput(resource_kind='live_event',resource_id=event['id'],title='Fixture slides',content_type='image/png',expected_size=len(data),checksum=hashlib.sha256(data).hexdigest())
    async with w.factory() as db:
        with pytest.raises(ApiError):await routes.slide_intent(body,db,w.viewer,uuid4().hex)
    async with w.factory() as db:deck=await routes.slide_intent(body,db,w.host,'slide-intent')
    async with w.factory() as db:
        assert (await routes.slide_intent(body,db,w.host,'slide-intent'))['id']==deck['id']
    async with w.factory() as db:
        asset=await db.get(MediaAsset,UUID(deck['upload']['id']));path=asset_path(asset);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);asset.received_size=len(data);await db.commit()
    async with w.factory() as db:uploaded=await complete_upload(asset.id,w.host,db)
    assert uploaded['state']=='processing'
    async with w.factory() as db:
        asset=await db.get(MediaAsset,asset.id);job=await db.get(Job,asset.processing_job_id);job.state='running';job.claim_token=uuid4();job.lease_until=datetime.now(timezone.utc)+timedelta(minutes=2);await db.commit()
        context=JobContext(job.id,job.claim_token,w.foundation.id,dict(job.payload))
        with pytest.raises(LeaseLost):await jobs.convert_slides(db,JobContext(context.job_id,uuid4(),context.foundation_id,context.payload))
        await db.rollback()
        assert await db.scalar(select(func.count()).select_from(SlidePage))==0
        output=await jobs.convert_slides(db,context);await complete(db,context.job_id,context.claim_token,output);await db.commit()
        assert output['state']=='ready' and output['pages']==1
        page=await db.scalar(select(SlidePage));assert page.width==80 and page.height==60
        output_asset=await db.get(MediaAsset,page.asset_id);assert hashlib.sha256(asset_path(output_asset).read_bytes()).hexdigest()==page.sha256
    async with w.factory() as db:
        view=await routes.slide_status(UUID(deck['id']),db,w.host);assert view['state']=='ready' and view['pages'][0]['asset_id']==page.asset_id

@pytest.mark.asyncio
async def test_board_signed_token_introspection_rechecks_current_auth_session(world,monkeypatch):
    from starlette.requests import Request
    w=world;event=await webinar(w);prepared=await prepare(w,event);id=UUID(prepared['id'])
    settings=RtcSettings(board_url='wss://board.example.test',board_secret='board-fixture-secret-at-least-thirty-two-bytes')
    monkeypatch.setattr(RtcSettings,'from_env',classmethod(lambda cls:settings))
    async with w.factory() as db:grant=await routes.board_token(id,db,w.host)
    def request():return Request({'type':'http','method':'POST','path':'/api/v1/studio-board/authorize','headers':[(b'authorization',('Bearer '+grant['token']).encode())]})
    async with w.factory() as db:assert await routes.authorize_board(request(),db)=={'allowed':True,'can_draw':True}
    async with w.factory() as db:
        auth=await db.get(Session,w.host.session_id);auth.revoked_at=datetime.now(timezone.utc);await db.commit()
    async with w.factory() as db:
        with pytest.raises(ApiError) as revoked:await routes.authorize_board(request(),db)
        assert revoked.value.status_code==403

@pytest.mark.asyncio
async def test_terminal_converter_failure_is_visible_retry_cas_and_old_lease_fenced(world):
    w=world;event=await webinar(w);stream=io.BytesIO();Image.new('RGB',(20,10),'white').save(stream,'PNG');data=stream.getvalue()
    body=SlideUploadInput(resource_kind='live_event',resource_id=event['id'],title='Retry slides',content_type='image/png',expected_size=len(data),checksum=hashlib.sha256(data).hexdigest())
    async with w.factory() as db:deck=await routes.slide_intent(body,db,w.host,uuid4().hex)
    async with w.factory() as db:
        asset=await db.get(MediaAsset,UUID(deck['upload']['id']));path=asset_path(asset);path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data);asset.received_size=len(data);await db.commit()
    async with w.factory() as db:await complete_upload(asset.id,w.host,db)
    async with w.factory() as db:
        asset=await db.get(MediaAsset,asset.id);old=await db.get(Job,asset.processing_job_id);old.state='dead';old.error_code='worker_timeout';old.claim_token=uuid4();await db.commit();old_context=JobContext(old.id,old.claim_token,w.foundation.id,dict(old.payload))
    async with w.factory() as db:
        failed=await routes.slide_status(UUID(deck['id']),db,w.host);assert failed['state']=='failed' and failed['error_code']=='conversion_worker_failed'
    async def retry(key):
        async with w.factory() as db:return await routes.slide_retry(UUID(deck['id']),StudioVersionCommand(expected_version=failed['version']),db,w.host,key)
    values=await asyncio.gather(retry('retry-one'),retry('retry-two'),return_exceptions=True)
    assert sum(isinstance(value,dict) for value in values)==1
    assert next(value for value in values if isinstance(value,ApiError)).code=='version_conflict'
    async with w.factory() as db:
        assert (await jobs.convert_slides(db,old_context))['state']=='superseded'
        assert await db.scalar(select(func.count()).select_from(SlidePage))==0

@pytest.mark.asyncio
async def test_reconcile_authorized_participant_preserves_worker_fence(world,monkeypatch):
    w=world;event=await webinar(w);prepared=await prepare(w,event)
    async with w.factory() as db:
        row=await db.get(StudioSession,UUID(prepared['id']));row.state='opening';await db.commit()
    class Provider:
        async def participants(self,room):return [{'identity':'opora-u'+w.host.user_id.hex,'metadata':__import__('json').dumps({'auth_session_id':str(w.host.session_id)})}]
    monkeypatch.setattr(jobs,'LiveKitAdapter',Provider)
    fenced=[]
    async def fence(db):fenced.append(True)
    context=SimpleNamespace(foundation_id=w.foundation.id,payload={'session_id':prepared['id'],'generation':1,'identity':'opora-u'+w.host.user_id.hex},fence=fence)
    async with w.factory() as db:assert (await jobs.reconcile_participant(db,context))['state']=='authorized'
    assert fenced==[True]

@pytest.mark.asyncio
async def test_enrollment_roster_is_host_only_and_versions_survive_reload(world):
    w=world;event=await webinar(w);id=UUID(event['id']);await prepare(w,event)
    async with w.factory() as db:await routes.enroll(id,None,db,w.viewer,uuid4().hex)
    async with w.factory() as db:
        own=await routes.webinar_detail(id,db,w.viewer);assert own['enrollment_version']==1 and not own['can_host']
        with pytest.raises(ApiError):await routes.webinar_participants(id,db,w.viewer)
    async with w.factory() as db:
        rows=await routes.webinar_participants(id,db,w.host);assert rows==[{'user_id':w.viewer.user_id,'display_name':'Fixture Viewer','enrollment_state':'enrolled','enrollment_version':1,'can_draw':False}]
    async with w.factory() as db:await routes.withdraw(id,StudioVersionCommand(expected_version=1),db,w.viewer,uuid4().hex)
    async with w.factory() as db:
        own=await routes.webinar_detail(id,db,w.viewer);assert own['enrollment_version']==2 and own['enrollment_state']=='withdrawn'

@pytest.mark.asyncio
async def test_room_close_marks_event_ended_only_after_provider_and_worker_ack(world,monkeypatch):
    from app.modules.studio.models import Webinar
    from app.integrations.rtc.livekit import ProviderError
    w=world;event=await webinar(w);prepared=await prepare(w,event);provider_down=True
    async with w.factory() as db:
        row=await db.get(StudioSession,UUID(prepared['id']));row.state='closing';await db.commit()
    class Provider:
        async def close_room(self,room):
            if provider_down:raise ProviderError('DeleteRoom',503)
    monkeypatch.setattr(jobs,'LiveKitAdapter',Provider)
    fences=[]
    async def fence(db):fences.append(True)
    context=SimpleNamespace(foundation_id=w.foundation.id,payload={'session_id':prepared['id'],'generation':1},fence=fence)
    async with w.factory() as db:
        with pytest.raises(ProviderError):await jobs.close_studio(db,context)
        assert (await db.get(Webinar,UUID(event['id']))).state=='published';assert not fences
    provider_down=False
    async with w.factory() as db:
        assert await jobs.close_studio(db,context)=={'state':'closed'};await db.commit()
        assert (await db.get(Webinar,UUID(event['id']))).state=='ended';assert fences==[True]

@pytest.mark.asyncio
async def test_close_job_outlasts_provider_outage_and_dead_job_can_be_reissued(world):
    w=world;event=await webinar(w);prepared=await prepare(w,event);id=UUID(prepared['id'])
    async with w.factory() as db:
        row=await db.get(StudioSession,id);row.state='live';await db.commit()
    async with w.factory() as db:closing=await routes.close(id,StudioVersionCommand(expected_version=prepared['version']),db,w.host,uuid4().hex)
    assert closing['state']=='closing'
    async with w.factory() as db:
        first=await db.scalar(select(Job).where(Job.kind=='studio.close'));assert first.max_attempts==20
        first.state='dead';first.attempts=20;first.error_code='handler_failed';await db.commit()
    async with w.factory() as db:again=await routes.close(id,StudioVersionCommand(expected_version=closing['version']),db,w.host,uuid4().hex)
    assert again['state']=='closing' and again['version']==closing['version']+1
    async with w.factory() as db:
        retry=await db.scalar(select(Job).where(Job.kind=='studio.close',Job.state=='queued'));assert retry and retry.id!=first.id and retry.max_attempts==20

@pytest.mark.asyncio
async def test_board_draw_revoke_denies_existing_pass_and_next_grant_is_readonly(world,monkeypatch):
    from starlette.requests import Request
    from app.modules.studio.schemas import StudioBoardGrantInput
    w=world;event=await webinar(w);prepared=await prepare(w,event);id=UUID(prepared['id'])
    async with w.factory() as db:
        row=await db.get(StudioSession,id);row.state='live';await db.commit()
    settings=RtcSettings(board_url='wss://board.example.test',board_secret='board-fixture-secret-at-least-thirty-two-bytes')
    monkeypatch.setattr(RtcSettings,'from_env',classmethod(lambda cls:settings))
    async with w.factory() as db:await routes.enroll(UUID(event['id']),None,db,w.viewer,uuid4().hex)
    async with w.factory() as db:await routes.board_grant(id,StudioBoardGrantInput(expected_version=1,user_id=w.viewer.user_id,can_draw=True),db,w.host,uuid4().hex)
    async with w.factory() as db:grant=await routes.board_token(id,db,w.viewer);assert grant['can_draw']
    def request():return Request({'type':'http','method':'POST','path':'/api/v1/studio-board/authorize','headers':[(b'authorization',('Bearer '+grant['token']).encode())]})
    async with w.factory() as db:assert (await routes.authorize_board(request(),db))['can_draw']
    async with w.factory() as db:await routes.board_grant(id,StudioBoardGrantInput(expected_version=2,user_id=w.viewer.user_id,can_draw=False),db,w.host,uuid4().hex)
    async with w.factory() as db:
        with pytest.raises(ApiError) as denied:await routes.authorize_board(request(),db)
        assert denied.value.status_code==403
    async with w.factory() as db:assert not (await routes.board_token(id,db,w.viewer))['can_draw']
