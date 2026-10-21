"""PostgreSQL command/lease/privacy proofs; native browser acceptance is a separate opt-in smoke."""
from datetime import timedelta
from uuid import UUID,uuid4
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from app.cli import fixtures
from app.core.clock import utcnow
from app.core.db import SessionLocal
from app.core.models import Job
from app.core.platform import install_platform
from app.modules.auth.router import router as auth
from app.modules.recordings.router import router as recordings
from app.modules.recordings.models import RecordingTake,RecordingProject,RecordingRenderVersion
from app.modules.recordings.capture import CaptureSettings
from app.modules.recordings.jobs import capture_take
from app.integrations.rtc.livekit import LiveKitAdapter,identity
from app.worker.queue import claim,LeaseLost
from app.worker.registry import JobContext
from test_messaging import actor

@pytest.fixture
def app():
    value=FastAPI();install_platform(value);value.include_router(auth);value.include_router(recordings);return value

async def prepared(client):
    await fixtures();me,headers=await actor(client,'coordinator@example.test',True)
    async def post(path,body):
        headers['Idempotency-Key']=uuid4().hex
        return await client.post('/api/v1'+path,json=body,headers=headers)
    project=(await post('/recording-projects',{'title':'Synthetic command privacy fixture'})).json()
    project=(await post(f"/recording-projects/{project['id']}/prepare",{'expected_version':project['version']})).json()
    take=(await post(f"/recording-projects/{project['id']}/takes",{'expected_version':project['version'],'expected_scene_revision':0})).json()
    assert take['max_duration_seconds']==1190 and take['stop_reason'] is None
    return me,headers,post,take

@pytest.mark.asyncio
async def test_policy_authority_exact_tracks_and_start_stop_receipts(app,monkeypatch):
    monkeypatch.setattr(CaptureSettings,'configured',classmethod(lambda cls,**kwargs:object()))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
        me,headers,post,take=await prepared(client);path=f"/recording-takes/{take['id']}"
        assert (await post(path+'/start',{'expected_version':1})).status_code==409
        own=identity(UUID(me['user_id']));track={'identity':own,'track_id':'TR_synthetic','source':'microphone','kind':'audio','required':True}
        async def participants(self,room):return [{'identity':own,'tracks':[{'sid':'TR_synthetic','source':'MICROPHONE'}]}]
        monkeypatch.setattr(LiveKitAdapter,'participants',participants)
        body={'expected_version':1,'expected_scene_revision':1,'approved':True,'tracks':[]}
        assert (await post(path+'/policy',body)).status_code==409
        assert (await post(path+'/policy',body|{'tracks':[track|{'identity':'outsider'}]})).status_code==422
        approved=await post(path+'/policy',body|{'tracks':[track]});assert approved.status_code==200,approved.text
        headers['Idempotency-Key']=uuid4().hex;start_body={'expected_version':approved.json()['version']}
        first=await client.post('/api/v1'+path+'/start',json=start_body,headers=headers)
        replay=await client.post('/api/v1'+path+'/start',json=start_body,headers=headers)
        assert first.json()==replay.json() and first.json()['state']=='starting' and first.json()['started_at'] is None
        assert (await post(path+'/policy',body|{'expected_version':first.json()['version'],'tracks':[track]})).status_code==409
        stopped=await post(path+'/stop',{'expected_version':first.json()['version']});assert stopped.json()['state']=='stopping'
        async with SessionLocal() as db:
            job=await db.get(Job,UUID(first.json()['capture_job_id']));assert job.kind=='recording.capture'
            # Narrow claim kind unique to this synthetic fixture avoids any neighboring jobs.
            job.kind='capture.fixture.'+uuid4().hex;await db.commit();job=await claim(db,kinds=[job.kind]);await db.commit()
            context=JobContext(job.id,job.claim_token,job.foundation_id,job.payload)
            result=await capture_take(db,context);assert result=={'state':'failed','error_code':'capture_stopped_before_start'};await db.commit()
            row=await db.get(RecordingTake,UUID(take['id']),populate_existing=True);assert row.state=='failed' and row.started_at is None
            assert not await db.scalar(select(RecordingRenderVersion.id).where(RecordingRenderVersion.take_id==UUID(take['id'])))

@pytest.mark.asyncio
async def test_restart_unknown_capture_outcome_and_stale_lease_never_publish(app,monkeypatch):
    monkeypatch.setattr(CaptureSettings,'configured',classmethod(lambda cls,**kwargs:object()))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
        me,headers,post,take=await prepared(client);path=f"/recording-takes/{take['id']}"
        async with SessionLocal() as db:
            row=await db.get(RecordingTake,UUID(take['id']));owner=await db.get(RecordingProject,row.project_id)
            owner.privacy_state='approved';row.projection={**row.projection,'capture_plan':{**row.projection['capture_plan'],'privacy_state':'approved','allowed_tracks':[{'identity':identity(UUID(me['user_id'])),'track_id':'TR_restart_audio','source':'microphone','kind':'audio','required':True}]}}
            await db.commit()
        started=await post(path+'/start',{'expected_version':1});assert started.status_code==200
        async with SessionLocal() as db:
            row=await db.get(RecordingTake,UUID(take['id']));row.capture_checkpoint={'phase':'capturing','job_id':started.json()['capture_job_id']};row.state='capturing'
            job=await db.get(Job,row.capture_job_id);job.kind='capture.restart.'+uuid4().hex;await db.commit();job=await claim(db,kinds=[job.kind]);await db.commit()
            old=JobContext(job.id,job.claim_token,job.foundation_id,job.payload)
            job.lease_until=utcnow()-timedelta(seconds=1);await db.commit();new=await claim(db,kinds=[job.kind]);await db.commit();fresh=JobContext(new.id,new.claim_token,new.foundation_id,new.payload)
            with pytest.raises(LeaseLost):await capture_take(db,old)
            await db.rollback()
            result=await capture_take(db,fresh);await db.commit()
            assert result=={'state':'failed','error_code':'capture_interrupted'}
            assert not await db.scalar(select(RecordingRenderVersion.id).where(RecordingRenderVersion.take_id==UUID(take['id'])))

@pytest.mark.asyncio
async def test_scene_transition_authorizes_only_prior_approved_frame_bounded(app):
    from app.modules.recordings import service
    from app.modules.recordings.models import StudioCaptureSession
    from app.modules.studio.models import StudioSession
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
        me,headers,post,take=await prepared(client)
        async with SessionLocal() as db:
            row=await db.get(RecordingTake,UUID(take['id']));owner=await db.get(RecordingProject,row.project_id)
            capture=await db.get(StudioCaptureSession,row.capture_session_id);studio=await db.get(StudioSession,capture.studio_session_id)
            owner.privacy_state='approved';await service.snapshot(db,owner,row,studio,privacy_state='approved',allowed_tracks=[])
            row.state='capturing';row.capture_checkpoint={'phase':'capturing'};row.started_at=utcnow()
            row.readiness_state='ready';row.readiness={'renderer_state_version':row.renderer_state_version,'projection_hash':row.projection_hash,'valid_until':(utcnow()+timedelta(seconds=10)).isoformat()}
            previous=(row.renderer_state_version,row.projection_hash)
            studio.scene_revision+=1;studio.scene={**studio.scene,'revision':studio.scene_revision,'presenter_size':30}
            await service.snapshot(db,owner,row,studio,privacy_state='approved',allowed_tracks=[])
            transition=service.scene_transition(row)
            assert transition['from_renderer_state_version']==previous[0] and transition['from_projection_hash']==previous[1] and service.capture_ready(row)
            row.readiness_state='blocked';row.readiness={'reasons':['visual_frame_unready']};assert service.capture_ready(row)
            row.readiness={'reasons':['media_not_connected','visual_frame_unready']};assert not service.capture_ready(row)
            row.readiness_state='waiting';row.capture_checkpoint={**row.capture_checkpoint,'scene_transition':{**row.capture_checkpoint['scene_transition'],'expires_at':(utcnow()-timedelta(seconds=1)).isoformat()}}
            assert service.scene_transition(row) is None and not service.capture_ready(row)
            await db.rollback()

@pytest.mark.asyncio
async def test_closed_asset_cannot_resurrect_processing(app):
    from app.modules.assets.router import router as assets
    from app.core.models import MediaAsset
    app.include_router(assets)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
        me,headers,post,take=await prepared(client)
        async with SessionLocal() as db:
            asset=MediaAsset(foundation_id=UUID(me['foundation_id']),owner_user_id=UUID(me['user_id']),storage_key=uuid4().hex,content_type='image/png',expected_size=10,received_size=10,checksum='a'*64,state='rejected')
            db.add(asset);await db.commit();aid=asset.id
        response=await client.post(f'/api/v1/assets/{aid}/complete-upload',headers=headers)
        assert response.status_code==409 and response.json()['code']=='upload_closed'
        async with SessionLocal() as db:
            asset=await db.get(MediaAsset,aid);assert asset.state=='rejected' and asset.processing_job_id is None

@pytest.mark.asyncio
async def test_worker_completes_safe_failure_after_handler_rollback():
    from app.core.config import get_settings
    from app.worker.queue import enqueue_job
    from app.worker.registry import register_handler
    from app.worker.main import run_once
    await fixtures();kind='rollback.fixture.'+uuid4().hex
    async def safe_failure(db,context):
        await db.rollback()
        return {'state':'failed','error_code':'synthetic_interrupted'}
    register_handler(kind,safe_failure,lease_seconds=30,heartbeat_seconds=5,timeout_seconds=10)
    async with SessionLocal() as db:
        job=enqueue_job(db,get_settings().foundation_id,kind,{});await db.commit();jid=job.id
    assert await run_once([kind])
    async with SessionLocal() as db:
        job=await db.get(Job,jid)
        assert job.state=='succeeded' and job.result=={'state':'failed','error_code':'synthetic_interrupted'}

def test_api_admission_does_not_require_media_worker_binaries(monkeypatch):
    monkeypatch.setenv('OPORA_CAPTURE_ENABLED','true')
    monkeypatch.setenv('OPORA_CAPTURE_RENDERER_URL','http://127.0.0.1:5174/recorder.html')
    monkeypatch.setenv('OPORA_RTC_URL','http://127.0.0.1:7880')
    monkeypatch.setenv('OPORA_RTC_API_KEY','synthetic-key')
    monkeypatch.setenv('OPORA_RTC_API_SECRET','synthetic-secret-not-a-real-provider-credential')
    monkeypatch.setenv('OPORA_CAPTURE_CHROME_PATH','/missing/dedicated-worker/chrome')
    monkeypatch.setattr('app.modules.recordings.capture.shutil.which',lambda name:None)
    assert CaptureSettings.configured() is not None
    assert CaptureSettings.configured(require_executables=True) is None
    monkeypatch.setenv('OPORA_CAPTURE_RENDERER_URL','https:///recorder.html')
    assert CaptureSettings.configured() is None

@pytest.mark.asyncio
async def test_failure_cleanup_removes_only_fenced_exact_private_identity(app,monkeypatch):
    from app.modules.recordings.jobs import remove_private_participants
    from app.modules.recordings.models import RecordingRendererGrant
    from app.core.crypto import digest
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
        me,headers,post,take=await prepared(client)
        removed=[];fences=[]
        async def remove(self,room,participant_identity,**options):removed.append(participant_identity)
        monkeypatch.setattr(LiveKitAdapter,'remove_participant',remove)
        class Context:
            async def fence(self,db):fences.append(True)
        async with SessionLocal() as db:
            row=await db.get(RecordingTake,UUID(take['id']))
            renderer=RecordingRendererGrant(take_id=row.id,generation=row.generation,token_hash=digest(uuid4().hex),purpose='renderer',expires_at=utcnow()+timedelta(minutes=1),revoked_at=utcnow())
            bootstrap=RecordingRendererGrant(take_id=row.id,generation=row.generation,token_hash=digest(uuid4().hex),purpose='bootstrap',expires_at=utcnow()+timedelta(minutes=1),revoked_at=utcnow())
            db.add_all([renderer,bootstrap]);await db.flush()
            await remove_private_participants(db,Context(),row)
            assert removed==['opora-renderer-'+renderer.id.hex] and len(fences)==2
            class Stale:
                async def fence(self,db):raise LeaseLost()
            with pytest.raises(LeaseLost):await remove_private_participants(db,Stale(),row)
            assert len(removed)==1
            await db.rollback()
