import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit
import pyotp
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import get_settings
from app.core.db import Base, get_db
from app.core.model_loader import load_models
from app.core.models import Session, AuthChallenge, OutboxMessage, MfaFactor, User
from app.core.errors import install_error_handlers
from app.modules.auth.router import router
from app.stage_demo.operator import seed, login_token, validate_runtime, write_new_private, CONFIRMATION

def test_stage_guard_rejects_runtime_and_provider_shortcuts(monkeypatch):
    monkeypatch.setenv('OPORA_STAGE_FIXTURE_SEED_ALLOW','true')
    valid={'environment':'staging','dev_inbox':False,'cookie_secure':True,'smtp_host':None}
    validate_runtime(SimpleNamespace(**valid),CONFIRMATION)
    for changed in ({'environment':'production'},{'environment':'development'},{'dev_inbox':True},{'cookie_secure':False},{'smtp_host':'smtp.example.test'}):
        with pytest.raises(RuntimeError): validate_runtime(SimpleNamespace(**{**valid,**changed}),CONFIRMATION)
    with pytest.raises(RuntimeError): validate_runtime(SimpleNamespace(**valid),'yes')

def test_private_file_is_new_mode0600_and_not_overwritten(tmp_path):
    target=tmp_path/'private.json'
    write_new_private(target,{'marker':'not-a-secret'})
    assert stat.S_IMODE(target.stat().st_mode)==0o600
    with pytest.raises(FileExistsError): write_new_private(target,{'marker':'different'})
    link=tmp_path/'symlink.json';link.symlink_to(target)
    with pytest.raises(FileExistsError): write_new_private(link,{'marker':'different'})

@pytest_asyncio.fixture
async def stage(monkeypatch,tmp_path):
    url=os.getenv('OPORA_STAGE_DEMO_TEST_DATABASE_URL','')
    if not url: pytest.skip('Dedicated own loopback OPORA_STAGE_DEMO_TEST_DATABASE_URL /opora_stage required')
    parsed=urlsplit(url)
    if parsed.hostname not in ('127.0.0.1','localhost') or parsed.path!='/opora_stage':
        raise RuntimeError('Refusing to reset a non-loopback/non-designated test database')
    monkeypatch.setenv('OPORA_DATABASE_URL',url)
    monkeypatch.setenv('OPORA_ENVIRONMENT','staging')
    monkeypatch.setenv('OPORA_COOKIE_SECURE','true')
    monkeypatch.setenv('OPORA_DEV_INBOX','false')
    monkeypatch.setenv('OPORA_SECRET_KEY','synthetic-staging-unit-test-key-not-for-deployment-2026')
    monkeypatch.setenv('OPORA_SMTP_HOST','')
    monkeypatch.setenv('OPORA_TRUSTED_ORIGINS','["https://stage.example.test"]')
    monkeypatch.setenv('OPORA_STAGE_FIXTURE_SEED_ALLOW','true')
    monkeypatch.delenv('OPORA_TELEGRAM_BOT_TOKEN',raising=False)
    get_settings.cache_clear();load_models()
    engine=create_async_engine(url,hide_parameters=True)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    app=FastAPI();install_error_handlers(app);app.include_router(router)
    async def override():
        async with factory() as db:
            try: yield db
            except BaseException:
                await db.rollback();raise
    app.dependency_overrides[get_db]=override
    yield factory,app,tmp_path/'demo-credentials.json'
    await engine.dispose();get_settings.cache_clear()

@pytest.mark.asyncio
async def test_seed_once_and_normal_api_email_mfa_without_public_inbox(stage):
    factory,app,credentials_path=stage
    async with factory() as db:
        result=await seed(db,credentials_path,CONFIRMATION)
    assert result['status']=='seeded'
    private=json.loads(credentials_path.read_text())
    from app.modules.participants.models import Participant
    from app.modules.applications.models import FormVersion
    from app.modules.applications.form import FORM_VERSION
    async with factory() as db:
        assert await db.scalar(select(func.count()).select_from(User))==6
        assert await db.scalar(select(func.count()).select_from(Session))==0
        assert await db.scalar(select(func.count()).select_from(AuthChallenge))==0
        assert await db.scalar(select(func.count()).select_from(OutboxMessage))==0
        assert not await db.scalar(select(Participant.id).where(Participant.photo_asset_id.is_not(None)).limit(1))
        factor=await db.scalar(select(MfaFactor))
        assert factor.confirmed_at is None
        assert await db.scalar(select(FormVersion.id).where(FormVersion.version==FORM_VERSION))
        repeated=await seed(db,credentials_path,CONFIRMATION)
        assert repeated['status']=='already_seeded'
        assert await db.scalar(select(func.count()).select_from(User))==6
    for key in ('volunteer','coordinator'):
        async with AsyncClient(transport=ASGITransport(app=app),base_url='https://stage.example.test') as client:
            initial=(await client.get('/api/v1/auth/session')).json()
            client.headers.update({'Origin':'https://stage.example.test','X-CSRF-Token':initial['csrf_token']})
            response=await client.post('/api/v1/auth/challenges',json={'email':private['identities'][key]['email']})
            assert response.status_code==200
            challenge=response.json()
            assert challenge['delivery']=='pending'
            output=credentials_path.parent/f'login-{key}.json'
            async with factory() as db:
                before=await db.scalar(select(func.count()).select_from(Session))
                from uuid import UUID
                await login_token(db,credentials_path,private['identities'][key]['email'],UUID(challenge['challenge_id']),output,CONFIRMATION)
                assert await db.scalar(select(func.count()).select_from(Session))==before
            code=json.loads(output.read_text())
            verified=await client.post('/api/v1/auth/challenges/verify',json={'challenge_id':challenge['challenge_id'],'token':code['token']})
            assert verified.status_code==200
            identity=verified.json()
            assert identity['user_id']==private['identities'][key]['user_id']
            assert not identity['is_staff']
            if key=='coordinator':
                assert identity['mfa_required']
                client.headers['X-CSRF-Token']=identity['csrf_token']
                mfa=await client.post('/api/v1/auth/mfa/verify',json={'code':pyotp.TOTP(private['identities'][key]['totp_secret']).now()})
                assert mfa.status_code==200
                assert mfa.json()['is_staff'] and 'hours.review' in mfa.json()['permissions']
            async with factory() as db:
                with pytest.raises(RuntimeError):
                    await login_token(db,credentials_path,private['identities'][key]['email'],UUID(challenge['challenge_id']),output.parent/'consumed.json',CONFIRMATION)
