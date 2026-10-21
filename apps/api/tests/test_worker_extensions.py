import asyncio
from uuid import UUID,uuid4
import hashlib
from datetime import timedelta
import httpx
import pytest
from sqlalchemy import select,update
from app.cli import fixtures
from app.core.auth import resolve_principal
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import Job,Session
from app.modules.assets.registry import register_asset_purpose,create_upload_intent,PURPOSES
from app.worker.registry import register_handler,HANDLERS,run_handler
from app.worker.queue import enqueue_job,claim,LeaseLost
from app.worker.main import run_once
from test_messaging import app,actor

@pytest.mark.asyncio
async def test_resource_bound_intent_and_processing_do_not_expand_public_upload_policy(app):
    await fixtures()
    resource=uuid4()
    purpose='test.slides.'+uuid4().hex
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as owner,httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as stranger:
        session,headers=await actor(owner,'coordinator@example.test',True)
        other,_=await actor(stranger,'candidate-two@example.test')
        async def authorize(db,principal,resource_type,resource_id):
            if str(principal.user_id)!=session['user_id'] or resource_id!=resource or resource_type!='slide_deck':
                raise ApiError(404,'resource_not_found','Not found')
        register_asset_purpose(purpose,content_types=['application/x-test-deck'],max_bytes=2048,authorize=authorize,validate=lambda data,mime:data==b'fixture-deck',processor_kind='test.convert')
        data=b'fixture-deck'
        checksum=hashlib.sha256(data).hexdigest()
        public=await owner.post('/api/v1/assets/upload-intents',json={'content_type':'application/x-test-deck','expected_size':len(data),'checksum':checksum,'purpose':purpose,'resource_type':'slide_deck','resource_id':str(resource)},headers=headers)
        assert public.status_code==422
        async with SessionLocal() as db:
            row=await db.scalar(select(Session).where(Session.token_hash==digest(owner.cookies.get('opora_session'))))
            principal=await resolve_principal(db,row)
            asset=await create_upload_intent(db,principal,content_type='application/x-test-deck',expected_size=len(data),checksum=checksum,purpose=purpose,resource_type='slide_deck',resource_id=resource)
            aid=asset.id
            await db.commit()
        assert (await stranger.get(f'/api/v1/assets/{aid}/status')).status_code==404
        assert (await owner.patch(f'/api/v1/assets/{aid}/upload',content=data,headers={**headers,'X-Upload-Offset':'0'})).status_code==200
        finished=await owner.post(f'/api/v1/assets/{aid}/complete-upload',headers=headers)
        assert finished.status_code==200,finished.text
        assert finished.json()['state']=='processing'
        assert (await owner.get(f'/api/v1/assets/{aid}/content')).status_code==409
    PURPOSES.pop(purpose)

@pytest.mark.asyncio
async def test_explicit_kind_filter_and_independent_heartbeat_run_registered_job():
    seed=await fixtures()
    kind='test.heartbeat.'+uuid4().hex
    async def handler(db,context):
        await asyncio.sleep(1.2)
        await context.fence(db)
        return {'handler':'ran'}
    register_handler(kind,handler,lease_seconds=10,heartbeat_seconds=1,timeout_seconds=3)
    async with SessionLocal() as db:
        job=enqueue_job(db,UUID(seed['foundation_id']),kind,{})
        jid=job.id
        await db.commit()
    # An unrelated explicit kind cannot claim this job.
    assert await run_once(kinds=['test.no_handler']) is False
    async with SessionLocal() as db:
        assert (await db.get(Job,jid)).state=='queued'
    assert await run_once(kinds=[kind]) is True
    async with SessionLocal() as db:
        row=await db.get(Job,jid)
        assert row.state=='succeeded' and row.result=={'handler':'ran'}
    HANDLERS.pop(kind)

@pytest.mark.asyncio
async def test_lost_heartbeat_cancels_handler_and_prevents_stale_completion():
    seed=await fixtures()
    kind='test.loss.'+uuid4().hex
    started,cancelled=asyncio.Event(),asyncio.Event()
    async def handler(db,context):
        started.set()
        try:
            await asyncio.sleep(10)
            return {'should_not':'complete'}
        finally:
            cancelled.set()
    register_handler(kind,handler,lease_seconds=10,heartbeat_seconds=1,timeout_seconds=5)
    async with SessionLocal() as db:
        job=enqueue_job(db,UUID(seed['foundation_id']),kind,{})
        jid=job.id
        await db.commit()
        claimed=await claim(db,kinds=[kind],lease_seconds=10)
        await db.commit()
        work=asyncio.create_task(run_handler(db,claimed,HANDLERS[kind]))
        await started.wait()
        new_token=uuid4()
        async with SessionLocal() as reclaim:
            await reclaim.execute(update(Job).where(Job.id==jid).values(claim_token=new_token,lease_until=utcnow()+timedelta(seconds=30)))
            await reclaim.commit()
        with pytest.raises(LeaseLost):
            await work
        await db.rollback()
        assert cancelled.is_set()
        fresh=await db.get(Job,jid,populate_existing=True)
        assert fresh.claim_token==new_token and fresh.state=='running' and fresh.result is None
    HANDLERS.pop(kind)
