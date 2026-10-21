"""Invented identities only; isolated real PostgreSQL HTTP contract tests."""
import asyncio,json,os
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID,uuid4
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport,AsyncClient
from sqlalchemy import func,select,text
from sqlalchemy.ext.asyncio import async_sessionmaker,create_async_engine
from app.core.auth import issue_session
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.crypto import digest,unseal
from app.core.db import Base,get_db
from app.core.errors import install_error_handlers
from app.core.model_loader import load_models
from app.core.models import ContactChannel,Foundation,OutboxMessage,Session,StaffMembership,User
from app.modules.applications.router import router as applications
from app.modules.auth.password import hash_password,verify_password
from app.modules.auth.password_models import PasswordChallenge,PasswordCredential
from app.modules.auth.router import router as auth
from app.modules.notifications.delivery import check_email

# Public invented fixture inputs, never deployment credentials.
FAKE_PASSWORD='invented-local-test-password'
FAKE_NEXT_PASSWORD='invented-local-replacement-password'
FAKE_EMAIL='invented@fixture.example.test'

@pytest_asyncio.fixture
async def env():
    url=os.environ.get('OPORA_PASSWORD_TEST_DATABASE_URL','')
    if not url:pytest.skip('Set OPORA_PASSWORD_TEST_DATABASE_URL to the owned disposable DB')
    if not url.startswith('postgresql+psycopg://') or not url.endswith(':56158/opora_welcome_auth_test'):raise RuntimeError('Only owned isolated DB on56158 allowed')
    load_models();engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
    async with engine.begin() as c:
        await c.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
        await c.run_sync(Base.metadata.drop_all);await c.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(Foundation(id=get_settings().foundation_id,name='Invented fixture foundation'));await db.commit()
    app=FastAPI();install_error_handlers(app);app.include_router(auth);app.include_router(applications)
    async def database():
        async with factory() as db:
            try:yield db
            except Exception:await db.rollback();raise
    app.dependency_overrides[get_db]=database
    yield app,factory
    await engine.dispose()

@asynccontextmanager
async def actor(app):
    client=AsyncClient(transport=ASGITransport(app=app),base_url='http://testserver')
    data=(await client.get('/api/v1/auth/session')).json()
    client.headers.update({'Origin':'http://testserver','X-CSRF-Token':data['csrf_token']})
    try:yield client
    finally:await client.aclose()

async def post(client,path,payload):return await client.post('/api/v1/auth'+path,json=payload)

async def proof(factory,challenge_id):
    async with factory() as db:
        for outbox in (await db.scalars(select(OutboxMessage))).all():
            payload=json.loads(unseal(outbox.payload_cipher))
            if payload.get('challenge_id')==challenge_id:return payload,outbox
    raise AssertionError('Fixture email missing')

async def register(client,factory,email=FAKE_EMAIL):
    result=await post(client,'/register',{'email':email,'password':FAKE_PASSWORD});assert result.status_code==200,result.text
    payload,_=await proof(factory,result.json()['challenge_id'])
    result=await post(client,'/register/verify',{'challenge_id':payload['challenge_id'],'code':payload['code']});assert result.status_code==200,result.text
    client.headers['X-CSRF-Token']=result.json()['csrf_token'];return result.json()

def test_hash_salt_params_and_unicode():
    one,two=hash_password(FAKE_PASSWORD),hash_password(FAKE_PASSWORD)
    assert one!=two and one.startswith('scrypt$32768$8$3$')
    assert verify_password(FAKE_PASSWORD,one) and not verify_password(FAKE_NEXT_PASSWORD,one)
    unusual='Пример длинного пароля🔑\x00';assert verify_password(unusual,hash_password(unusual))
    assert not verify_password(FAKE_PASSWORD,'scrypt$1$1$1$00$00')

@pytest.mark.asyncio
async def test_verified_gate_and_email_ownership(env):
    app,factory=env
    async with actor(app) as client:
        draft={'expected_version':0,'step':0,'answers':{'firstName':'Fixture'}};headers={'Idempotency-Key':str(uuid4())}
        denied=await client.put('/api/v1/registration/draft',json=draft,headers=headers)
        assert denied.status_code==403 and denied.json()['code']=='verified_account_required'
        denied=await client.post('/api/v1/applications/submit',json={'expected_version':0,'answers':{},'consents':{'personal_data':True}},headers=headers)
        assert denied.status_code==403
        pending=await post(client,'/register',{'email':' '+FAKE_EMAIL.upper()+' ','password':FAKE_PASSWORD});assert pending.status_code==200,pending.text
        payload,_=await proof(factory,pending.json()['challenge_id'])
        assert len(payload['code'])==6 and payload['code'].isascii() and payload['code'].isdigit()
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(User))==0
            assert await db.scalar(select(func.count()).select_from(PasswordCredential))==0
            row=await db.get(PasswordChallenge,UUID(payload['challenge_id']))
            assert FAKE_PASSWORD not in row.pending_password_hash and row.code_hash!=digest(payload['code'])
        result=await post(client,'/register/verify',{'challenge_id':payload['challenge_id'],'code':payload['code']});assert result.status_code==200,result.text
        data=result.json();assert data['user_id'] and data['registration_id'] is None and data['verified_email']==FAKE_EMAIL
        client.headers['X-CSRF-Token']=data['csrf_token'];draft['answers']['email']='forged@fixture.example.test'
        saved=await client.put('/api/v1/registration/draft',json=draft,headers=headers)
        assert saved.status_code==200,saved.text
        assert saved.json()['answers']['email']==FAKE_EMAIL
        assert (await client.get('/api/v1/auth/session')).json()['verified_email']==FAKE_EMAIL

@pytest.mark.asyncio
async def test_code_binding_five_attempts_expiry_resend_delivery(env):
    app,factory=env
    async with actor(app) as first,actor(app) as other:
        pending=(await post(first,'/register',{'email':FAKE_EMAIL,'password':FAKE_PASSWORD})).json()
        payload,outbox=await proof(factory,pending['challenge_id'])
        async with factory() as db:assert await check_email(db,outbox,payload) is None
        body={'challenge_id':pending['challenge_id'],'code':payload['code']}
        assert (await post(other,'/register/verify',body)).status_code==400
        wrong='111111' if payload['code']!='111111' else '222222'
        for _ in range(5):assert (await post(first,'/register/verify',{**body,'code':wrong})).status_code==400
        assert (await post(first,'/register/verify',body)).status_code==400
        async with factory() as db:
            assert (await db.get(PasswordChallenge,UUID(pending['challenge_id']))).attempts==5
            assert await check_email(db,outbox,payload)=='suppressed_stale_auth'
        fresh=(await post(first,'/register',{'email':FAKE_EMAIL,'password':FAKE_PASSWORD})).json();new_payload,_=await proof(factory,fresh['challenge_id'])
        async with factory() as db:
            row=await db.get(PasswordChallenge,UUID(fresh['challenge_id']));row.expires_at=utcnow()-timedelta(seconds=1);await db.commit()
        assert (await post(first,'/register/verify',{'challenge_id':fresh['challenge_id'],'code':new_payload['code']})).status_code==400
        assert (await post(first,'/register',{'email':FAKE_EMAIL,'password':FAKE_PASSWORD})).status_code==200
        async with factory() as db:assert (await db.get(PasswordChallenge,UUID(fresh['challenge_id']))).consumed_at
        assert (await post(first,'/register',{'email':FAKE_EMAIL,'password':FAKE_PASSWORD})).status_code==429

@pytest.mark.asyncio
async def test_existing_account_login_origin_csrf(env):
    app,factory=env
    async with actor(app) as owner,actor(app) as newcomer:
        existing=await register(owner,factory)
        assert (await post(newcomer,'/register',{'email':FAKE_EMAIL,'password':FAKE_NEXT_PASSWORD})).status_code==409
        invalid=await post(newcomer,'/login',{'email':FAKE_EMAIL,'password':FAKE_NEXT_PASSWORD})
        unknown=await post(newcomer,'/login',{'email':'unknown@fixture.example.test','password':FAKE_NEXT_PASSWORD})
        assert invalid.status_code==unknown.status_code==401
        assert invalid.json()['code']==unknown.json()['code']=='invalid_credentials'
        csrf=newcomer.headers.pop('X-CSRF-Token')
        assert (await post(newcomer,'/login',{'email':FAKE_EMAIL,'password':FAKE_PASSWORD})).status_code==403
        newcomer.headers['X-CSRF-Token']=csrf;newcomer.headers['Origin']='https://untrusted.example.test'
        assert (await post(newcomer,'/login',{'email':FAKE_EMAIL,'password':FAKE_PASSWORD})).status_code==403
        newcomer.headers['Origin']='http://testserver'
        good=await post(newcomer,'/login',{'email':FAKE_EMAIL,'password':FAKE_PASSWORD})
        assert good.status_code==200 and good.json()['user_id']==existing['user_id']

@pytest.mark.asyncio
async def test_concurrent_contact_registration_single_winner(env):
    app,factory=env
    async with actor(app) as one,actor(app) as two:
        bodies=[]
        for client in (one,two):
            pending=await post(client,'/register',{'email':FAKE_EMAIL,'password':FAKE_PASSWORD});payload,_=await proof(factory,pending.json()['challenge_id']);bodies.append({'challenge_id':payload['challenge_id'],'code':payload['code']})
        results=await asyncio.gather(post(one,'/register/verify',bodies[0]),post(two,'/register/verify',bodies[1]))
        assert sorted(r.status_code for r in results)==[200,409]
        async with factory() as db:assert await db.scalar(select(func.count()).select_from(PasswordCredential))==1

@pytest.mark.asyncio
async def test_reset_generic_single_use_all_sessions_and_staff_mfa(env):
    app,factory=env
    async with actor(app) as owner,actor(app) as resetter,actor(app) as unknown,actor(app) as second:
        existing=await register(owner,factory);uid=UUID(existing['user_id'])
        async with factory() as db:
            db.add(StaffMembership(user_id=uid,foundation_id=get_settings().foundation_id))
            from starlette.responses import Response
            await issue_session(db,Response(),user_id=uid,mfa_at=utcnow());await db.commit()
        logged=await post(second,'/login',{'email':FAKE_EMAIL,'password':FAKE_PASSWORD});assert logged.status_code==200 and logged.json()['mfa_required']
        second.headers['X-CSRF-Token']=logged.json()['csrf_token']
        known=await post(resetter,'/password/reset',{'email':FAKE_EMAIL});absent=await post(unknown,'/password/reset',{'email':'absent@fixture.example.test'})
        assert known.status_code==absent.status_code==200
        assert {k:v for k,v in known.json().items() if k!='challenge_id'}=={k:v for k,v in absent.json().items() if k!='challenge_id'}
        payload,outbox=await proof(factory,known.json()['challenge_id']);body={'challenge_id':known.json()['challenge_id'],'code':payload['code'],'password':FAKE_NEXT_PASSWORD}
        assert (await post(unknown,'/password/reset/verify',body)).status_code==400
        result=await post(resetter,'/password/reset/verify',body);assert result.status_code==200,result.text
        assert result.json()['user_id']==existing['user_id'] and result.json()['mfa_required']
        resetter.headers['X-CSRF-Token']=result.json()['csrf_token']
        assert (await owner.get('/api/v1/me/application')).status_code==401
        assert (await second.get('/api/v1/me/application')).status_code==401
        async with factory() as db:
            sessions=(await db.scalars(select(Session).where(Session.user_id==uid,Session.revoked_at.is_(None)))).all();assert len(sessions)==1 and sessions[0].mfa_at is None
            assert await check_email(db,outbox,payload)=='suppressed_stale_auth'
            credential=await db.scalar(select(PasswordCredential).where(PasswordCredential.user_id==uid));assert credential.version==2 and verify_password(FAKE_NEXT_PASSWORD,credential.password_hash)
        async with actor(app) as fresh:
            assert (await post(fresh,'/password/reset/verify',body)).status_code==400
            assert (await post(fresh,'/login',{'email':FAKE_EMAIL,'password':FAKE_PASSWORD})).status_code==401
            good=await post(fresh,'/login',{'email':FAKE_EMAIL,'password':FAKE_NEXT_PASSWORD});assert good.status_code==200 and good.json()['mfa_required']
            fresh.headers['X-CSRF-Token']=good.json()['csrf_token'];assert (await post(fresh,'/logout',{})).status_code==200
            assert (await resetter.get('/api/v1/me/application')).status_code==401

def test_demo_mode_forbidden_in_production():
    from app.core.config import Settings
    with pytest.raises(RuntimeError,match='Demo email codes'):
        Settings(environment='production',demo_email_codes=True).validate_runtime()

@pytest.mark.asyncio
async def test_demo_any_nonblank_code_new_identity_only(env,monkeypatch):
    app,factory=env
    monkeypatch.setattr(get_settings(),'demo_email_codes',True)
    async with actor(app) as client,actor(app) as other:
        assert (await client.get('/api/v1/auth/session')).json()['demo_email_codes']
        pending=await post(client,'/register',{'email':FAKE_EMAIL,'password':FAKE_PASSWORD});assert pending.status_code==200
        challenge_id=pending.json()['challenge_id'];body={'challenge_id':challenge_id,'code':'любая строка'}
        assert (await post(other,'/register/verify',body)).status_code==400
        assert (await post(client,'/register/verify',{**body,'code':'   '})).status_code==400
        result=await post(client,'/register/verify',body);assert result.status_code==200,result.text
        assert result.json()['verified_email']==FAKE_EMAIL
        async with factory() as db:
            credential=await db.scalar(select(PasswordCredential));assert credential.demo_created
            assert await db.scalar(select(func.count()).select_from(OutboxMessage))==0
        assert (await post(other,'/register',{'email':FAKE_EMAIL,'password':FAKE_NEXT_PASSWORD})).status_code==409
        reset=await post(other,'/password/reset',{'email':FAKE_EMAIL});assert reset.status_code==200
        changed=await post(other,'/password/reset/verify',{'challenge_id':reset.json()['challenge_id'],'code':'anything','password':FAKE_NEXT_PASSWORD})
        assert changed.status_code==200,changed.text

@pytest.mark.asyncio
async def test_demo_cannot_reset_real_credential_or_claim_existing(env,monkeypatch):
    app,factory=env
    async with actor(app) as owner,actor(app) as attacker:
        existing=await register(owner,factory)
        monkeypatch.setattr(get_settings(),'demo_email_codes',True)
        assert (await post(attacker,'/register',{'email':FAKE_EMAIL,'password':FAKE_NEXT_PASSWORD})).status_code==409
        pending=await post(attacker,'/password/reset',{'email':FAKE_EMAIL});payload,_=await proof(factory,pending.json()['challenge_id'])
        denied=await post(attacker,'/password/reset/verify',{'challenge_id':pending.json()['challenge_id'],'code':'any-code','password':FAKE_NEXT_PASSWORD})
        assert denied.status_code==400
        async with factory() as db:
            credential=await db.scalar(select(PasswordCredential));assert not credential.demo_created and verify_password(FAKE_PASSWORD,credential.password_hash)
            assert (await db.get(User,UUID(existing['user_id']))).account_state=='active'
