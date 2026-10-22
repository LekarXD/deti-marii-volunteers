import asyncio
import json
import secrets
from datetime import timedelta
from uuid import uuid4
import httpx
import pyotp
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update
from app.cli import fixtures
from app.core.auth import Principal
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.crypto import unseal
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.idempotency import begin_command, finish_command
from app.core.models import AuthChallenge, ContactChannel, Job, MfaFactor, OutboxMessage, Session, User
from app.core.platform import install_platform
from app.modules.auth.router import router as auth_router
from app.modules.staff.router import router as staff_router
from app.modules.assets.router import router as asset_router
from app.worker.queue import claim, complete, enqueue_job, LeaseLost

@pytest.fixture
def app():
    instance = FastAPI()
    install_platform(instance)
    instance.include_router(auth_router)
    instance.include_router(staff_router)
    instance.include_router(asset_router)
    return instance

async def login(client, email):
    session = (await client.get('/api/v1/auth/session')).json()
    headers = {'Origin':'http://testserver','X-CSRF-Token':session['csrf_token']}
    response = await client.post('/api/v1/auth/challenges', json={'email':email}, headers=headers)
    assert response.status_code == 200, response.text
    challenge_id = response.json()['challenge_id']
    async with SessionLocal() as db:
        rows = (await db.scalars(select(OutboxMessage).order_by(OutboxMessage.created_at.desc()))).all()
        payload = next(p for p in (json.loads(unseal(row.payload_cipher)) for row in rows) if p['challenge_id'] == challenge_id)
    response = await client.post('/api/v1/auth/challenges/verify', json={'challenge_id':challenge_id,'token':payload['token']}, headers=headers)
    assert response.status_code == 200, response.text
    return response.json(), payload

@pytest.mark.asyncio
async def test_real_auth_csrf_one_time_mfa_and_dynamic_revoke(app):
    await fixtures()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as staff, httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as candidate:
        bootstrap = (await staff.get('/api/v1/auth/session')).json()
        assert bootstrap['user_id'] is None and bootstrap['registration_id']
        bad = await staff.post('/api/v1/auth/challenges', json={'email':'coordinator@example.test'})
        assert bad.status_code == 403
        session,payload = await login(staff, 'coordinator@example.test')
        assert not session['is_staff'] and session['mfa_required']
        headers = {'Origin':'http://testserver','X-CSRF-Token':session['csrf_token']}
        replay = await staff.post('/api/v1/auth/challenges/verify', json={'challenge_id':payload['challenge_id'],'token':payload['token']}, headers=headers)
        assert replay.status_code == 400
        async with SessionLocal() as db:
            factor = await db.scalar(select(MfaFactor).where(MfaFactor.user_id == session['user_id']))
            code = pyotp.TOTP(unseal(factor.secret_cipher)).now()
            factor.last_counter = -1
            await db.commit()
        response = await staff.post('/api/v1/auth/mfa/verify', json={'code':code},headers=headers)
        assert response.status_code == 200, response.text
        session=response.json()
        assert session['is_staff'] and 'staff.manage' in session['permissions']
        headers['X-CSRF-Token']=session['csrf_token']
        headers['Idempotency-Key']=uuid4().hex
        candidate_session,_ = await login(candidate, f'isolated-{uuid4().hex}@example.test')
        assert candidate_session['user_id'] != session['user_id'] and not candidate_session['permissions']
        grant = await staff.post('/api/v1/coord/staff/grants', json={'user_id':candidate_session['user_id'],'permission':'roles.manage'},headers=headers)
        assert grant.status_code == 200, grant.text
        # Email proof alone cannot activate staff permission after grant.
        assert not (await candidate.get('/api/v1/auth/session')).json()['is_staff']
        async with SessionLocal() as db:
            candidate_factor=MfaFactor(user_id=candidate_session['user_id'],secret_cipher=__import__('app.core.crypto',fromlist=['seal']).seal(pyotp.random_base32()),confirmed_at=utcnow())
            db.add(candidate_factor)
            candidate_secret=unseal(candidate_factor.secret_cipher)
            await db.commit()
        ch={'Origin':'http://testserver','X-CSRF-Token':candidate_session['csrf_token']}
        verified=await candidate.post('/api/v1/auth/mfa/verify',json={'code':pyotp.TOTP(candidate_secret).now()},headers=ch)
        assert verified.status_code == 200, verified.text
        assert 'roles.manage' in verified.json()['permissions']
        headers['Idempotency-Key']=uuid4().hex
        revoked=await staff.post('/api/v1/coord/staff/grants/'+grant.json()['id']+'/revoke',headers=headers)
        assert revoked.status_code==200
        assert 'roles.manage' not in (await candidate.get('/api/v1/auth/session')).json()['permissions']

@pytest.mark.asyncio
async def test_atomic_receipt_replay_conflict_actor_and_lease_fencing():
    seed=await fixtures()
    uid=__import__('uuid').UUID(seed['identities']['candidate-one@example.test']['user_id'])
    principal=Principal(uid,None,get_settings().foundation_id,uuid4(),False,str(uid))
    operation='test.'+uuid4().hex
    async def command():
        async with SessionLocal() as db:
            replay=await begin_command(db,principal,operation,'same',{'value':1})
            if replay is None:
                job=enqueue_job(db,principal.foundation_id,'test.job',{})
                result={'id':str(job.id)}
                await finish_command(db,principal,operation,'same',result)
            else:
                result=replay
            await db.commit()
            return result
    first,second=await asyncio.gather(command(),command())
    assert first==second
    async with SessionLocal() as db:
        with pytest.raises(ApiError) as exc:
            await begin_command(db,principal,operation,'same',{'value':2})
        assert exc.value.status_code==409
    async with SessionLocal() as db:
        job=await claim(db,kinds=['test.job'])
        assert job is not None
        old=job.claim_token
        jid=job.id
        job.lease_until=utcnow()-timedelta(seconds=1)
        await db.commit()
    async with SessionLocal() as db:
        reclaimed=await claim(db,kinds=['test.job'])
        assert reclaimed.id==jid and reclaimed.claim_token!=old
        await db.commit()
    async with SessionLocal() as db:
        with pytest.raises(LeaseLost):
            await complete(db,jid,old)
        await db.rollback()
        await complete(db,jid,reclaimed.claim_token,{'ok':True})
        await db.commit()

@pytest.mark.asyncio
async def test_private_upload_checks_full_image_and_other_identity(app):
    import hashlib
    import io
    from PIL import Image
    await fixtures()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as owner, httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as stranger:
        session=(await owner.get('/api/v1/auth/session')).json()
        await stranger.get('/api/v1/auth/session')
        headers={'Origin':'http://testserver','X-CSRF-Token':session['csrf_token']}
        buffer=io.BytesIO()
        Image.new('RGB',(2,2),'blue').save(buffer,format='PNG')
        data=buffer.getvalue()
        # Registration sessions are free to mint, so they never get private uploads.
        response=await owner.post('/api/v1/assets/upload-intents',json={'content_type':'image/png','expected_size':len(data),'checksum':hashlib.sha256(data).hexdigest()},headers=headers)
        assert response.status_code==403 and response.json()['code']=='verified_account_required'
        session,_=await login(owner,'candidate-one@example.test')
        headers['X-CSRF-Token']=session['csrf_token']
        response=await owner.post('/api/v1/assets/upload-intents',json={'content_type':'image/png','expected_size':len(data),'checksum':hashlib.sha256(data).hexdigest()},headers=headers)
        assert response.status_code==200,response.text
        aid=response.json()['id']
        response=await owner.patch(f'/api/v1/assets/{aid}/upload',content=data,headers={**headers,'X-Upload-Offset':'0'})
        assert response.status_code==200,response.text
        duplicate=await owner.patch(f'/api/v1/assets/{aid}/upload',content=data,headers={**headers,'X-Upload-Offset':'0'})
        assert duplicate.status_code==409
        complete_response=await owner.post(f'/api/v1/assets/{aid}/complete-upload',headers=headers)
        assert complete_response.status_code==200,complete_response.text
        assert (await owner.get(f'/api/v1/assets/{aid}/content')).content==data
        assert (await stranger.get(f'/api/v1/assets/{aid}/content')).status_code==404
        # A matching PNG signature cannot turn malformed image bytes into a ready file.
        malformed=b'\x89PNG\r\n\x1a\nnot-image'
        response=await owner.post('/api/v1/assets/upload-intents',json={'content_type':'image/png','expected_size':len(malformed),'checksum':hashlib.sha256(malformed).hexdigest()},headers=headers)
        bad=response.json()['id']
        await owner.patch(f'/api/v1/assets/{bad}/upload',content=malformed,headers={**headers,'X-Upload-Offset':'0'})
        assert (await owner.post(f'/api/v1/assets/{bad}/complete-upload',headers=headers)).status_code==422
        assert (await owner.get(f'/api/v1/assets/{bad}/content')).status_code==409

@pytest.mark.asyncio
async def test_generic_upload_intents_bound_outstanding_bytes_and_rate(app):
    from uuid import UUID
    from app.core.models import MediaAsset
    await fixtures()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as owner:
        session,_=await login(owner,f'uploader-{uuid4().hex}@example.test')
        headers={'Origin':'http://testserver','X-CSRF-Token':session['csrf_token']}
        intent=lambda size:owner.post('/api/v1/assets/upload-intents',json={'content_type':'image/png','expected_size':size,'checksum':'a'*64},headers=headers)
        for _ in range(10):assert (await intent(get_settings().max_asset_bytes)).status_code==200
        full=await intent(1);assert full.status_code==429 and full.json()['code']=='upload_quota_exceeded'
        async with SessionLocal() as db:
            await db.execute(update(MediaAsset).where(MediaAsset.owner_user_id==UUID(session['user_id'])).values(state='rejected'));await db.commit()
        for _ in range(49):assert (await intent(1)).status_code==200
        limited=await intent(1);assert limited.status_code==429 and limited.json()['code']=='rate_limited'

def test_auth_openapi_has_concrete_generated_session_contract(app):
    schema=app.openapi()
    for path in ('/api/v1/auth/session','/api/v1/auth/challenges/verify'):
        method='get' if path.endswith('/session') else 'post'
        assert schema['paths'][path][method]['responses']['200']['content']['application/json']['schema']['$ref'].endswith('/AuthSessionView')
    assert set(schema['components']['schemas']['AuthSessionView']['required']) == {'user_id','registration_id','foundation_id','is_staff','permissions','csrf_token','actor_id','mfa_required'}
