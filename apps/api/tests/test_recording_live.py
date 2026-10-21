"""Live binding keeps webinar and recording identities distinct; provider scope is host-only."""
import json
from uuid import UUID,uuid4
from datetime import timedelta
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from app.cli import fixtures
from app.core.clock import utcnow
from app.core.db import SessionLocal
from app.core.models import User,Session
from app.core.platform import install_platform
from app.modules.auth.router import router as auth
from app.modules.recordings.router import router as recordings
from app.modules.recordings.models import RecordingProject,RecordingTake
from app.modules.recordings.live import audience_excluded
from app.modules.recordings.capture import verify_provider_scope
from app.modules.studio.models import Webinar,WebinarEnrollment,StudioSession
from app.modules.studio import service as studio
from app.core.auth import resolve_principal
from app.integrations.rtc.livekit import identity,LiveKitAdapter
from test_messaging import actor

@pytest.mark.asyncio
async def test_live_binding_reuses_current_session_and_excludes_only_current_subscribers(monkeypatch):
    await fixtures();app=FastAPI();install_platform(app);app.include_router(auth);app.include_router(recordings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
        me,headers=await actor(client,'coordinator@example.test',True)
        async def post(path,body):
            headers['Idempotency-Key']=uuid4().hex
            return await client.post('/api/v1'+path,json=body,headers=headers)
        async with SessionLocal() as db:
            # The existing host-issued auth session is sufficient; no room or join grant is minted by bind.
            login=await db.scalar(select(Session).where(Session.user_id==UUID(me['user_id']),Session.revoked_at.is_(None)).order_by(Session.created_at.desc()))
            principal=await resolve_principal(db,login)
            webinar=Webinar(foundation_id=principal.foundation_id,host_user_id=principal.user_id,title='Synthetic live recording',starts_at=utcnow(),state='published')
            db.add(webinar);await db.flush();session,_=await studio.create_session(db,principal,'live_event',webinar.id)
            session.state='live';await db.commit();wid,sid=webinar.id,session.id
        bound=await post(f'/webinars/{wid}/recording-project',{'studio_session_id':str(sid),'expected_scene_revision':0})
        assert bound.status_code==200,bound.text
        project=bound.json();assert project['mode']=='live' and project['live_event_id']==str(wid) and project['studio_session_id']==str(sid) and project['id']!=str(wid)
        again=await post(f'/webinars/{wid}/recording-project',{'studio_session_id':str(sid),'expected_scene_revision':0})
        assert again.json()['id']==project['id']
        assert (await post(f'/webinars/{wid}/recording-project',{'studio_session_id':str(sid),'expected_scene_revision':99})).status_code==409
        made=await post(f"/recording-projects/{project['id']}/takes",{'expected_version':project['version'],'expected_scene_revision':0})
        assert made.status_code==200,made.text
        async with SessionLocal() as db:
            take=await db.get(RecordingTake,UUID(made.json()['id']));owner=await db.get(RecordingProject,take.project_id);session=await db.get(StudioSession,sid)
            assert take.projection['capture_plan']['resource_id']==str(wid)==take.projection['scene']['resource_id']
            viewer=User(foundation_id=owner.foundation_id);db.add(viewer);await db.flush()
            login=Session(foundation_id=owner.foundation_id,user_id=viewer.id,token_hash=uuid4().hex*2,csrf_hash='x'*64,csrf_cipher='fixture',expires_at=utcnow()+timedelta(hours=1));db.add(login);await db.flush()
            enrollment=WebinarEnrollment(foundation_id=owner.foundation_id,webinar_id=wid,user_id=viewer.id);db.add(enrollment);await db.flush()
            participant={'identity':identity(viewer.id),'metadata':json.dumps({'role':'audience','auth_session_id':str(login.id)}),'tracks':[]}
            assert await audience_excluded(db,session,participant)
            assert not await audience_excluded(db,session,participant|{'tracks':[{'sid':'TR_unapproved','source':'MICROPHONE'}]})
            async def participants(self,room):assert room==session.room_name;return [participant]
            monkeypatch.setattr(LiveKitAdapter,'participants',participants)
            await verify_provider_scope(db,take,owner)
            enrollment.state='revoked';await db.flush()
            with pytest.raises(ValueError,match='capture_unknown_participant'):await verify_provider_scope(db,take,owner)
            await db.rollback()
        async with SessionLocal() as db:
            session=await db.get(StudioSession,sid);session.state='closed';await db.commit()
        assert (await post(f'/webinars/{wid}/recording-project',{'studio_session_id':str(sid),'expected_scene_revision':1})).status_code==409

@pytest.mark.asyncio
async def test_normal_live_close_cannot_invalidate_encoding_and_revocations_still_fence(monkeypatch):
    """Ordinary End waits for a stopping take; forced closure is not a normal End path."""
    from app.modules.studio.router import router as studio_router
    from app.modules.recordings.models import StudioCaptureSession
    from app.modules.recordings.jobs import checked_take,CaptureFailure
    from app.worker.queue import enqueue_job,claim
    from app.worker.registry import JobContext
    await fixtures();app=FastAPI();install_platform(app)
    for router in (auth,recordings,studio_router):app.include_router(router)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
        me,headers=await actor(client,'coordinator@example.test',True)
        async def post(path,body):
            headers['Idempotency-Key']=uuid4().hex
            return await client.post('/api/v1'+path,json=body,headers=headers)
        async with SessionLocal() as db:
            login=await db.scalar(select(Session).where(Session.user_id==UUID(me['user_id']),Session.revoked_at.is_(None)).order_by(Session.created_at.desc()))
            principal=await resolve_principal(db,login)
            webinar=Webinar(foundation_id=principal.foundation_id,host_user_id=principal.user_id,title='Synthetic ordinary End during encoding',starts_at=utcnow(),state='published')
            db.add(webinar);await db.flush();session,_=await studio.create_session(db,principal,'live_event',webinar.id)
            session.state='live';await db.commit();wid,sid=webinar.id,session.id
        response=await post(f'/webinars/{wid}/recording-project',{'studio_session_id':str(sid),'expected_scene_revision':0});assert response.status_code==200
        project=response.json()
        response=await post(f"/recording-projects/{project['id']}/takes",{'expected_version':project['version'],'expected_scene_revision':0});assert response.status_code==200
        tid=UUID(response.json()['id']);kind='capture.close-proof.'+uuid4().hex
        async with SessionLocal() as db:
            take=await db.get(RecordingTake,tid);owner=await db.get(RecordingProject,take.project_id)
            take.state='stopping';take.capture_phase='encoding';take.capture_checkpoint={'phase':'encoding','start':{'synthetic':'completed-source'}}
            owner.privacy_state='approved';take.projection={**take.projection,'capture_plan':{**take.projection['capture_plan'],'privacy_state':'approved'}}
            job=enqueue_job(db,owner.foundation_id,kind,{'take_id':str(take.id),'generation':take.generation});await db.flush();take.capture_job_id=job.id
            capture=await db.get(StudioCaptureSession,take.capture_session_id);host_session_id=capture.host_auth_session_id
            session=await db.get(StudioSession,sid);version=session.version;await db.commit()
        response=await post(f'/studio-sessions/{sid}/close',{'expected_version':version})
        assert response.status_code==409 and response.json()['code']=='capture_still_active'
        async with SessionLocal() as db:
            session=await db.get(StudioSession,sid);take=await db.get(RecordingTake,tid)
            assert session.state=='live' and take.state=='stopping' and take.capture_phase=='encoding'
            job=await claim(db,kinds=[kind]);await db.commit();context=JobContext(job.id,job.claim_token,job.foundation_id,job.payload)
            assert (await checked_take(db,context))[0].id==tid
            await db.rollback()
        # An out-of-band forced closure remains fail-closed, rather than granting
        # a general ended-room bypass to unknown or active sources.
        for revoked in ('forced_closed','host_session','privacy'):
            async with SessionLocal() as db:
                session=await db.get(StudioSession,sid);login=await db.get(Session,host_session_id);owner=await db.get(RecordingProject,UUID(project['id']))
                session.state='closed' if revoked=='forced_closed' else 'live'
                login.revoked_at=utcnow() if revoked=='host_session' else None
                owner.privacy_state='blocked' if revoked=='privacy' else 'approved';await db.commit()
            async with SessionLocal() as db:
                with pytest.raises(CaptureFailure):await checked_take(db,context)
                await db.rollback()
