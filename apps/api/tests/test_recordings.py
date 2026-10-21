import json
from uuid import UUID,uuid4
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from app.cli import fixtures
from app.core.clock import utcnow
from app.core.db import SessionLocal
from app.core.models import Session,Job
from app.core.platform import install_platform
from app.modules.auth.router import router as auth_router
from app.modules.recordings.router import router as recording_router
from app.modules.recordings.models import RecordingTake,RecordingProject,StudioCaptureSession,RecordingStageEvent
from app.modules.recordings.renderer import issue_renderer_ticket
from app.modules.recordings import service
from app.modules.studio.models import StudioSession
from app.worker.registry import JobContext
from app.worker.queue import enqueue_job,claim
from test_messaging import actor

@pytest.fixture
def app():
    app=FastAPI();install_platform(app);app.include_router(auth_router);app.include_router(recording_router);return app

@pytest.mark.asyncio
async def test_private_renderer_scope_monotonic_fences_and_readiness_is_not_capture(app):
    await fixtures()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as host,httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as renderer:
        identity,headers=await actor(host,'coordinator@example.test',True)
        created=await host.post('/api/v1/recording-projects',json={'title':'Invented private renderer fixture'},headers=headers)
        assert created.status_code==200,created.text
        assert (await host.post('/api/v1/recording-projects',json={'title':'Invented private renderer fixture'},headers=headers)).json()==created.json()
        project=created.json();headers['Idempotency-Key']=uuid4().hex
        prepared=await host.post(f"/api/v1/recording-projects/{project['id']}/prepare",json={'expected_version':project['version']},headers=headers)
        assert prepared.status_code==200,prepared.text
        headers['Idempotency-Key']=uuid4().hex
        made=await host.post(f"/api/v1/recording-projects/{project['id']}/takes",json={'expected_version':prepared.json()['version'],'expected_scene_revision':0},headers=headers)
        assert made.status_code==200,made.text
        take_id=UUID(made.json()['id'])
        async with SessionLocal() as db:
            take=await db.get(RecordingTake,take_id)
            kind='recording.fixture.'+uuid4().hex
            job=enqueue_job(db,UUID(identity['foundation_id']),kind,{'take_id':str(take_id)})
            await db.commit()
            claimed=await claim(db,kinds=[kind]);await db.commit()
            ticket=await issue_renderer_ticket(db,take,context=JobContext(claimed.id,claimed.claim_token,claimed.foundation_id,claimed.payload));await db.commit()
        assert (await host.get('/api/v1/recording-renderer/state')).status_code==401
        assert (await renderer.get('/api/v1/recording-renderer/state?access_token=redacted-fixture')).status_code==401
        boot=await renderer.post('/api/v1/recording-renderer/bootstrap',headers={'Authorization':'Bearer '+ticket})
        assert boot.status_code==200,boot.text
        initial=boot.json();access={'Authorization':'Bearer '+initial['access_token']}
        assert initial['invalidated'] and initial['provider_grant'] is None
        assert 'no-store' in boot.headers['cache-control']
        assert (await renderer.post('/api/v1/recording-renderer/bootstrap',headers={'Authorization':'Bearer '+ticket})).status_code==401
        readiness={'readiness_sequence':1,'visual_ready':True,'renderer_state_version':initial['renderer_state_version'],'projection_hash':initial['projection_hash'],'viewport_width':1920,'viewport_height':1080,'device_pixel_ratio':1,'render_profile_version':'opora-stage/1','observed_tracks':[],'asset_proofs':[]}
        not_ready=await renderer.post('/api/v1/recording-renderer/readiness',json=readiness,headers=access)
        assert not_ready.status_code==200 and not_ready.json()['reasons']==['privacy_not_approved']
        async with SessionLocal() as db:
            take=await db.get(RecordingTake,take_id);owner=await db.get(RecordingProject,take.project_id);capture=await db.get(StudioCaptureSession,take.capture_session_id);session=await db.get(StudioSession,capture.studio_session_id)
            # Trusted policy seam, intentionally no RTC provider or recording side effect in this test.
            await service.snapshot(db,owner,take,session,privacy_state='approved',allowed_tracks=[]);await db.commit()
        latest=(await renderer.get('/api/v1/recording-renderer/state',headers=access)).json()
        assert latest['renderer_state_version']>initial['renderer_state_version'] and latest['scene']['revision']==initial['scene']['revision']
        assert (await renderer.post('/api/v1/recording-renderer/readiness',json=readiness,headers=access)).status_code==409
        readiness.update(readiness_sequence=2,renderer_state_version=latest['renderer_state_version'],projection_hash=latest['projection_hash'])
        wrong_viewport=await renderer.post('/api/v1/recording-renderer/readiness',json=readiness|{'viewport_width':1280},headers=access)
        assert 'viewport_mismatch' in wrong_viewport.json()['reasons']
        readiness['readiness_sequence']=3
        ready=await renderer.post('/api/v1/recording-renderer/readiness',json=readiness,headers=access)
        assert ready.json()['ready'] and ready.json()['capture_state']=='created' and ready.json()['valid_until']
        lost=await renderer.post('/api/v1/recording-renderer/readiness',json=readiness|{'visual_ready':False,'readiness_sequence':4},headers=access)
        assert lost.json()['reasons']==['visual_frame_unready'] and lost.json()['valid_until'] is None
        stale=await renderer.post('/api/v1/recording-renderer/readiness',json=readiness,headers=access)
        assert stale.status_code==409 and stale.json()['code']=='renderer_readiness_sequence_conflict'
        exact_replay=await renderer.post('/api/v1/recording-renderer/readiness',json=readiness|{'visual_ready':False,'readiness_sequence':4},headers=access)
        assert exact_replay.json()==lost.json()
        assert (await renderer.get(f'/api/v1/recording-renderer/assets/{uuid4()}',headers=access)).status_code==404
        unavailable=await host.post(f'/api/v1/recording-takes/{take_id}/start',json={'expected_version':made.json()['version']},headers=headers)
        assert unavailable.status_code==503 and unavailable.json()['code']=='recording_capture_unavailable'
        async with SessionLocal() as db:
            take=await db.get(RecordingTake,take_id);assert take.started_at is None
            capture=await db.get(StudioCaptureSession,take.capture_session_id);session=await db.get(Session,capture.host_auth_session_id);session.revoked_at=utcnow();await db.commit()
        assert (await renderer.get('/api/v1/recording-renderer/state',headers=access)).status_code==401

def test_renderer_openapi_reuses_canonical_scene_and_purpose_only_routes(app):
    document=app.openapi();schemas=document['components']['schemas']
    assert schemas['RendererStateView']['properties']['scene']['properties']['resource_kind']['enum']==['live_event','lesson_recording_project']
    assert schemas['RendererStateView']['properties']['capture_plan']['properties']['raw_fallback']['const']=='forbidden'
    for path,value in document['paths'].items():
        if '/recording-renderer' not in path:continue
        for method in value.values():
            parameters=method.get('parameters',[])
            assert not any(p['name'] in ('ticket','token','access_token') for p in parameters)

@pytest.mark.asyncio
async def test_exact_render_approval_claim_expires_with_transaction(app):
    from app.core.auth import resolve_principal
    from app.core.crypto import digest
    from app.core.models import MediaAsset
    from app.core.errors import ApiError
    from app.modules.learning.models import LearningTrack,Lesson,LessonDraft
    from app.modules.recordings.models import RecordingRenderVersion
    from app.modules.recordings.publication import prepare_recording_publication,validate_recording_claim
    await fixtures()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as host:
        identity,headers=await actor(host,'coordinator@example.test',True)
        async with SessionLocal() as db:
            fid=UUID(identity['foundation_id'])
            track=LearningTrack(foundation_id=fid,key='recording-'+uuid4().hex,title='Fixture');db.add(track);await db.flush()
            lesson=Lesson(foundation_id=fid,track_id=track.id,key='fixture');db.add(lesson);await db.flush()
            draft=LessonDraft(foundation_id=fid,lesson_id=lesson.id,title='Fixture',minutes=1,source='',blocks=[],version=1,status='reviewed');db.add(draft);await db.commit();lesson_id=lesson.id
        created=(await host.post('/api/v1/recording-projects',json={'title':'Approval fixture','target_lesson_id':str(lesson_id)},headers=headers)).json()
        headers['Idempotency-Key']=uuid4().hex
        prepared=(await host.post(f"/api/v1/recording-projects/{created['id']}/prepare",json={'expected_version':created['version']},headers=headers)).json()
        headers['Idempotency-Key']=uuid4().hex
        take_response=await host.post(f"/api/v1/recording-projects/{created['id']}/takes",json={'expected_version':prepared['version'],'expected_scene_revision':0},headers=headers)
        assert take_response.status_code==200,take_response.text
        tid=UUID(take_response.json()['id']);rid=uuid4()
        async with SessionLocal() as db:
            take=await db.get(RecordingTake,tid);owner=await db.get(RecordingProject,take.project_id)
            # Synthetic DB fixture validates approval/transaction semantics, not real media readiness.
            take.state='captured';owner.privacy_state='approved'
            asset=MediaAsset(foundation_id=fid,owner_user_id=UUID(identity['user_id']),storage_key=uuid4().hex,content_type='video/mp4',expected_size=100,received_size=100,checksum='a'*64,state='ready',purpose='recording.output',resource_type='recording_render',resource_id=rid);db.add(asset);await db.flush()
            render=RecordingRenderVersion(id=rid,project_id=owner.id,take_id=tid,generation=take.generation,state='preview_ready',version=1,manifest={'synthetic_test_fixture':True},render_hash='b'*64,asset_id=asset.id,content_hash=asset.checksum,duration_ms=1000,quality='verified')
            db.add(render);await db.commit();asset_id=asset.id
        headers['Idempotency-Key']=uuid4().hex
        approved=await host.post(f'/api/v1/recording-renders/{rid}/approve',json={'expected_version':1,'render_hash':'b'*64},headers=headers)
        assert approved.status_code==200 and approved.json()['approval_state']=='approved'
        async with SessionLocal() as db:
            auth=await db.scalar(select(Session).where(Session.token_hash==digest(host.cookies.get('opora_session'))));principal=await resolve_principal(db,auth)
            claim=await prepare_recording_publication(db,principal,asset_id=asset_id,target_lesson_id=lesson_id,expected_draft_version=1)
            await validate_recording_claim(db,claim,asset_id=asset_id,target_lesson_id=lesson_id,expected_draft_version=1)
            await db.commit()
            with pytest.raises(ApiError):await validate_recording_claim(db,claim,asset_id=asset_id,target_lesson_id=lesson_id,expected_draft_version=1)
            render=await db.get(RecordingRenderVersion,rid);render.render_hash='c'*64;await db.commit()
            with pytest.raises(ApiError):await prepare_recording_publication(db,principal,asset_id=asset_id,target_lesson_id=lesson_id,expected_draft_version=1)

def test_projection_hash_ecmascript_jcs_goldens():
    from pathlib import Path
    vectors=json.loads((Path(__file__).parent/'fixtures'/'recording-jcs.json').read_text())
    for vector in vectors:assert service.stable_hash(vector['value'])==vector['sha256']
