import asyncio,os,re
from datetime import timedelta
from urllib.parse import parse_qs,urlsplit
from uuid import uuid4
import httpx,pytest,pytest_asyncio
from fastapi import FastAPI
from starlette.responses import Response
from sqlalchemy import select,func,text
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.core.auth import issue_session
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.crypto import digest,unseal
from app.core.db import Base,get_db
from app.core.errors import install_error_handlers
from app.core.model_loader import load_models
from app.core.models import Foundation,User,ContactChannel,Session,OutboxMessage,MutationReceipt,AuthChallenge
from app.modules.applications.models import ConsentEvent
from app.modules.auth.router import router as auth_router
from app.modules.messaging.models import Message
from app.modules.notifications.models import NotificationPreference
from app.modules.notifications.telegram_config import TelegramSettings
from app.modules.notifications.telegram_models import TelegramBinding,TelegramLinkToken
from app.modules.notifications.telegram_router import router
from app.modules.notifications import telegram_service,telegram_router
from app.modules.applications.tests.test_applications import actor
load_models()
BASE='/api/v1/me/notification-channels/telegram'
SECRET='fixture_webhook_secret_'+('0'*32)

@pytest_asyncio.fixture
async def env(monkeypatch):
    url=os.environ.get('OPORA_TELEGRAM_TEST_DATABASE_URL','')
    if not url:pytest.skip('Set dedicated OPORA_TELEGRAM_TEST_DATABASE_URL')
    if not url.endswith('/opora_telegram_test'):raise RuntimeError('Dedicated Telegram proof database required')
    engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'));await conn.run_sync(Base.metadata.drop_all);await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:db.add(Foundation(id=get_settings().foundation_id,name='Вымышленный фонд'));await db.commit()
    config=TelegramSettings(link_enabled=True,bot_username='Opora_fixture_bot',webhook_secret=SECRET)
    monkeypatch.setattr(telegram_service,'get_telegram_settings',lambda:config);monkeypatch.setattr(telegram_router,'get_telegram_settings',lambda:config)
    app=FastAPI();install_error_handlers(app);app.include_router(auth_router);app.include_router(router)
    async def override():
        async with factory() as db:
            try:yield db
            except BaseException:await db.rollback();raise
    app.dependency_overrides[get_db]=override
    yield app,factory,config
    await engine.dispose()

async def volunteer(app,factory,user_id=None):
    client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver')
    async with factory() as db:
        if user_id is None:
            user=User(foundation_id=get_settings().foundation_id,display_name='Тестовый волонтёр');db.add(user);await db.flush();user_id=user.id
            db.add(ContactChannel(user_id=user_id,normalized_value=uuid4().hex+'@example.test',verified_at=utcnow()))
        response=Response();session,csrf=await issue_session(db,response,user_id=user_id);await db.commit();session_id=session.id
    client.cookies.set('opora_session',response.headers['set-cookie'].split(';')[0].split('=',1)[1]);client.headers.update({'Origin':'http://testserver','X-CSRF-Token':csrf});return client,user_id,session_id
async def issue(client,key=None):
    response=await client.post(BASE+'/link-tokens',json={},headers={'Idempotency-Key':key or str(uuid4())});assert response.status_code==200,response.text;return response.json()
def bearer(value):return parse_qs(urlsplit(value['start_url']).query)['start'][0]
def update(raw,telegram_id=10001,**changes):
    value={'update_id':1,'message':{'from':{'id':telegram_id,'is_bot':False},'chat':{'id':telegram_id,'type':'private'},'text':'/start '+raw}};value['message'].update(changes);return value
async def callback(client,value,secret=SECRET):return await client.post('/api/v1/integrations/telegram/webhook',json=value,headers={'X-Telegram-Bot-Api-Secret-Token':secret})

@pytest.mark.asyncio
async def test_unconfigured_and_unverified_are_explicitly_unavailable_without_tokens_or_messages(env):
    app,factory,config=env;client,_,_=await volunteer(app,factory);anonymous=await actor(app)
    try:
        assert (await anonymous.get(BASE)).status_code==403
        config.link_enabled=False
        status=(await client.get(BASE)).json();assert status['state']=='unavailable' and not status['configured'] and not status['delivery_available']
        assert (await client.post(BASE+'/link-tokens',json={},headers={'Idempotency-Key':'disabled'})).status_code==503
        assert (await callback(client,update('bind_'+('a'*43)))).status_code==503
        async with factory() as db:assert await db.scalar(select(func.count()).select_from(TelegramLinkToken))==0;assert await db.scalar(select(func.count()).select_from(OutboxMessage))==0
    finally:await client.aclose();await anonymous.aclose()

@pytest.mark.asyncio
async def test_one_use_binding_has_encrypted_replayable_bearer_and_never_grants_consent_or_delivery(env):
    app,factory,_=env;client,user_id,_=await volunteer(app,factory)
    try:
        async with factory() as db:preference=NotificationPreference(foundation_id=get_settings().foundation_id,user_id=user_id,email_enabled=False,no_contact=True,topics=dict(assignments=False,learning=True,messages=False,news=False));db.add(preference);await db.commit()
        token=await issue(client,'logical-token');raw=bearer(token);assert re.fullmatch(r'bind_[A-Za-z0-9_-]{43}',raw) and len(raw)<=64
        assert await issue(client,'logical-token')==token
        async with factory() as db:
            row=await db.get(TelegramLinkToken,token['id']);receipt=await db.scalar(select(MutationReceipt).where(MutationReceipt.operation=='notifications.telegram.issue'))
            assert row.token_hash==digest(raw) and raw not in row.token_cipher and unseal(row.token_cipher)==raw
            assert receipt.result=={'token_id':token['id']} and raw not in str(receipt.result)
        assert (await callback(client,update(raw))).json()=={'state':'linked'}
        assert (await callback(client,update(raw,telegram_id=20002))).json()=={'state':'ignored'}
        status=(await client.get(BASE)).json();assert status['state']=='linked' and status['version']==1 and not status['delivery_available'];assert 'chat_id' not in status and 'telegram_user_id' not in status
        replay=await issue(client,'logical-token');assert replay['state']=='consumed' and replay['start_url'] is None
        async with factory() as db:
            row=await db.get(TelegramLinkToken,token['id']);assert row.consumed_at and row.token_cipher is None and row.outcome=='linked'
            preference=await db.scalar(select(NotificationPreference).where(NotificationPreference.user_id==user_id));assert preference.no_contact and not preference.email_enabled and preference.topics==dict(assignments=False,learning=True,messages=False,news=False)
            assert await db.scalar(select(func.count()).select_from(TelegramBinding))==1
            for model in (ConsentEvent,OutboxMessage,Message):assert await db.scalar(select(func.count()).select_from(model))==0
    finally:await client.aclose()

@pytest.mark.asyncio
async def test_expiry_and_other_purpose_bearer_cannot_bind(env,monkeypatch):
    app,factory,_=env;client,_,session_id=await volunteer(app,factory)
    try:
        token=await issue(client);raw=bearer(token)
        async with factory() as db:
            row=await db.get(TelegramLinkToken,token['id']);future=row.expires_at+timedelta(seconds=1)
            unrelated='bind_'+('z'*43);db.add(AuthChallenge(foundation_id=get_settings().foundation_id,bound_session_id=session_id,token_hash=digest(unrelated),normalized_contact='proof@example.test',purpose='login',expires_at=future+timedelta(hours=1)));await db.commit()
        assert (await callback(client,update(unrelated))).json()['state']=='ignored'
        monkeypatch.setattr(telegram_service,'utcnow',lambda:future)
        assert (await callback(client,update(raw))).json()['state']=='ignored'
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(TelegramBinding))==0
            assert not (await db.scalar(select(AuthChallenge))).consumed_at
    finally:await client.aclose()

@pytest.mark.asyncio
@pytest.mark.parametrize('change',['session_revoked','account_disabled','proof_removed','session_owner_changed'])
async def test_callback_rechecks_exact_current_verified_identity_and_session(env,change):
    app,factory,_=env;client,user_id,session_id=await volunteer(app,factory)
    try:
        token=await issue(client)
        async with factory() as db:
            if change=='session_revoked':(await db.get(Session,session_id)).revoked_at=utcnow()
            elif change=='account_disabled':(await db.get(User,user_id)).account_state='deleted'
            elif change=='proof_removed':await db.delete(await db.scalar(select(ContactChannel).where(ContactChannel.user_id==user_id)))
            else:
                other=User(foundation_id=get_settings().foundation_id);db.add(other);await db.flush();(await db.get(Session,session_id)).user_id=other.id
            await db.commit()
        assert (await callback(client,update(bearer(token)))).json()['state']=='ignored'
        async with factory() as db:assert await db.scalar(select(func.count()).select_from(TelegramBinding))==0
    finally:await client.aclose()

@pytest.mark.asyncio
async def test_duplicate_callbacks_and_two_users_cannot_claim_one_private_identity_twice(env):
    app,factory,_=env;client,first,_=await volunteer(app,factory);other,second,_=await volunteer(app,factory)
    try:
        token=await issue(client);responses=await asyncio.gather(callback(client,update(bearer(token))),callback(other,update(bearer(token))))
        assert sorted(response.json()['state'] for response in responses)==['ignored','linked']
        other_token=await issue(other);assert (await callback(other,update(bearer(other_token)))).json()['state']=='conflict'
        assert (await other.get(BASE)).json()['state']=='conflict'
        async with factory() as db:
            bindings=(await db.scalars(select(TelegramBinding))).all();assert len(bindings)==1 and bindings[0].user_id==first and bindings[0].user_id!=second
    finally:await client.aclose();await other.aclose()

@pytest.mark.asyncio
async def test_new_link_revokes_old_tokens_and_explicit_disconnect_prevents_relink(env):
    app,factory,_=env;client,_,_=await volunteer(app,factory)
    try:
        old=await issue(client);current=await issue(client)
        assert (await callback(client,update(bearer(old)))).json()['state']=='ignored'
        assert (await callback(client,update(bearer(current)))).json()['state']=='linked'
        assert (await client.post(BASE+'/disconnect',json={'expected_version':0},headers={'Idempotency-Key':'stale'})).status_code==409
        response=await client.post(BASE+'/disconnect',json={'expected_version':1},headers={'Idempotency-Key':'disconnect'});assert response.status_code==200 and response.json()['state']=='disconnected'
        assert (await callback(client,update(bearer(current)))).json()['state']=='ignored'
        async with factory() as db:assert (await db.scalar(select(TelegramBinding))).revoked_at
        pending=await issue(client,'pending-cancel')
        cancelled=await client.post(BASE+'/disconnect',json={'expected_version':0},headers={'Idempotency-Key':'cancel-pending'});assert cancelled.status_code==200 and cancelled.json()['state']=='disconnected'
        assert (await callback(client,update(bearer(pending)))).json()['state']=='ignored'
    finally:await client.aclose()

@pytest.mark.asyncio
async def test_webhook_secret_private_chat_sender_and_body_are_bounded(env):
    app,factory,_=env;client,_,_=await volunteer(app,factory)
    try:
        token=await issue(client);raw=bearer(token)
        assert (await callback(client,update(raw),secret='wrong')).status_code==403
        for value in (update(raw,chat={'id':-1,'type':'group'}),update(raw,chat={'id':20002,'type':'private'}),update(raw,**{'from':{'id':10001,'is_bot':True}}),update(raw,text='/start@another_bot '+raw)):
            assert (await callback(client,value)).json()['state']=='ignored'
        oversized=await client.post('/api/v1/integrations/telegram/webhook',content=b'x'*8193,headers={'X-Telegram-Bot-Api-Secret-Token':SECRET});assert oversized.status_code==413
        assert (await callback(client,update(raw))).json()['state']=='linked'
    finally:await client.aclose()

@pytest.mark.asyncio
async def test_bearer_receipt_cannot_cross_users_or_rotation_sessions(env):
    app,factory,_=env;client,user_id,_=await volunteer(app,factory);other,_,_=await volunteer(app,factory);rotated,_,_=await volunteer(app,factory,user_id)
    try:
        token=await issue(client,'same-key');other_token=await issue(other,'same-key');assert other_token['id']!=token['id']
        failed=await rotated.post(BASE+'/link-tokens',json={},headers={'Idempotency-Key':'same-key'});assert failed.status_code==409 and 'start_url' not in failed.text
        assert (await other.get(BASE)).json()['token_id']==other_token['id']
        assert (await client.post(BASE+'/link-tokens',json={'user_id':str(user_id)},headers={'Idempotency-Key':'extra'})).status_code==422
    finally:await client.aclose();await other.aclose();await rotated.aclose()
