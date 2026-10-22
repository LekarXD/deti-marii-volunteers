from uuid import uuid4
import httpx,pyotp,pytest
from pydantic import SecretStr
from sqlalchemy import select
from app.core.auth import resolve_principal
from app.core.config import get_settings
from app.core.crypto import seal
from app.core.clock import utcnow
from app.core.models import MfaFactor,PermissionGrant,Session,StaffMembership
from app.modules.notifications import telegram_bot
from app.modules.notifications.tests.test_telegram_binding import BASE,bearer,callback,env,issue,update,volunteer  # noqa: F401  (env is a fixture)
BOT='/api/v1/integrations/telegram/bot/sessions'
BOT_SECRET='fixture_bot_api_secret_'+('1'*32)

@pytest.fixture
def bot_app(env,monkeypatch):
    app,factory,config=env;config.bot_api_secret=SecretStr(BOT_SECRET)
    monkeypatch.setattr(telegram_bot,'get_telegram_settings',lambda:config);app.include_router(telegram_bot.router)
    return app,factory,config

def as_bot(app,secret=BOT_SECRET):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',headers={'Authorization':'Bearer '+secret} if secret else {})

async def linked(app,factory,telegram_id=10001):
    client,user_id,_=await volunteer(app,factory)
    assert (await callback(client,update(bearer(await issue(client)),telegram_id=telegram_id))).json()=={'state':'linked'}
    return client,user_id

def session_client(app,token,secret=BOT_SECRET):
    client=as_bot(app,secret);client.cookies.set('opora_session',token);return client

@pytest.mark.asyncio
async def test_bot_session_requires_configured_secret_and_an_active_binding(bot_app):
    app,factory,config=bot_app;client,user_id=await linked(app,factory)
    try:
        for secret,status in ((None,401),('wrong_secret_'+'2'*32,401)):
            async with as_bot(app,secret) as bot:assert (await bot.post(BOT,json={'telegram_user_id':10001})).status_code==status
        async with as_bot(app) as bot:
            missing=await bot.post(BOT,json={'telegram_user_id':30003});assert missing.status_code==404 and missing.json()['code']=='telegram_not_linked'
            assert (await bot.post(BOT,json={'telegram_user_id':10001,'extra':1})).status_code==422
            config.bot_api_secret=None;assert (await bot.post(BOT,json={'telegram_user_id':10001})).status_code==503
    finally:await client.aclose()

@pytest.mark.asyncio
async def test_bot_session_acts_as_the_bound_volunteer_without_browser_origin_and_dies_with_the_binding(bot_app):
    app,factory,_=bot_app;client,user_id=await linked(app,factory)
    try:
        async with as_bot(app) as bot:opened=(await bot.post(BOT,json={'telegram_user_id':10001})).json()
        assert opened['user_id']==str(user_id) and opened['display_name']=='Тестовый волонтёр'
        async with factory() as db:row=await db.scalar(select(Session).where(Session.user_id==user_id,Session.channel=='telegram_bot'));assert row.revoked_at is None and row.mfa_at is None
        async with session_client(app,opened['session_token']) as session:
            status=(await session.get(BASE)).json();assert status['state']=='linked'
            # Server-to-server write: no Origin/CSRF, the service secret is enough.
            gone=await session.post(BASE+'/disconnect',json={'expected_version':status['version']},headers={'Idempotency-Key':str(uuid4())})
            assert gone.status_code==200 and gone.json()['state']=='disconnected'
            assert (await session.get(BASE)).status_code==401
        async with as_bot(app) as bot:assert (await bot.post(BOT,json={'telegram_user_id':10001})).status_code==404
    finally:await client.aclose()

@pytest.mark.asyncio
async def test_leaked_bot_session_token_is_useless_without_the_service_secret_and_new_session_replaces_old(bot_app):
    app,factory,_=bot_app;client,_=await linked(app,factory)
    try:
        async with as_bot(app) as bot:
            first=(await bot.post(BOT,json={'telegram_user_id':10001})).json()['session_token']
            second=(await bot.post(BOT,json={'telegram_user_id':10001})).json()['session_token']
        for path in (BASE,'/api/v1/auth/session'):
            async with session_client(app,second,None) as stolen:assert (await stolen.get(path)).status_code==401
        async with session_client(app,first) as old:assert (await old.get(BASE)).status_code==401
        async with session_client(app,second) as current:assert (await current.get(BASE)).status_code==200
    finally:await client.aclose()

@pytest.mark.asyncio
async def test_bot_session_of_a_staff_member_carries_no_staff_grants_before_the_coordinator_step(bot_app,monkeypatch):
    app,factory,_=bot_app;client,user_id=await linked(app,factory)
    monkeypatch.setattr(get_settings(),'demo_email_codes',True)
    try:
        async with factory() as db:
            membership=StaffMembership(foundation_id=get_settings().foundation_id,user_id=user_id);db.add(membership);await db.flush()
            db.add(PermissionGrant(membership_id=membership.id,permission='staff.manage'));await db.commit()
        async with as_bot(app) as bot:token=(await bot.post(BOT,json={'telegram_user_id':10001})).json()['session_token']
        async with factory() as db:
            row=await db.scalar(select(Session).where(Session.user_id==user_id,Session.channel=='telegram_bot',Session.revoked_at.is_(None)))
            principal=await resolve_principal(db,row);assert not principal.is_staff and not principal.grants
        assert token
    finally:await client.aclose()


async def staff_member(factory,user_id,secret=None):
    async with factory() as db:
        membership=StaffMembership(foundation_id=get_settings().foundation_id,user_id=user_id);db.add(membership);await db.flush()
        db.add(PermissionGrant(membership_id=membership.id,permission='staff.manage'))
        if secret:db.add(MfaFactor(user_id=user_id,secret_cipher=seal(secret),confirmed_at=utcnow()))
        await db.commit()

@pytest.mark.asyncio
async def test_coordinator_step_requires_staff_and_a_fresh_totp_then_grants_staff_to_that_bot_session_only(bot_app,monkeypatch):
    app,factory,_=bot_app;client,user_id=await linked(app,factory);monkeypatch.setattr(get_settings(),'demo_email_codes',False)
    secret=pyotp.random_base32()
    try:
        async with as_bot(app) as bot:token=(await bot.post(BOT,json={'telegram_user_id':10001})).json()['session_token']
        async with session_client(app,token) as session:
            assert (await session.post(BOT.replace('sessions','coordinator'),json={'code':'123456'})).json()['code']=='staff_required'
            await staff_member(factory,user_id)
            assert (await session.post(BOT.replace('sessions','coordinator'),json={'code':'123456'})).json()['code']=='mfa_enrollment_required'
        async with factory() as db:db.add(MfaFactor(user_id=user_id,secret_cipher=seal(secret),confirmed_at=utcnow()));await db.commit()
        async with session_client(app,token) as session:
            assert (await session.post(BOT.replace('sessions','coordinator'),json={'code':'000000' if pyotp.TOTP(secret).now()!='000000' else '111111'})).status_code==400
            ok=await session.post(BOT.replace('sessions','coordinator'),json={'code':pyotp.TOTP(secret).now()})
            assert ok.status_code==200 and ok.json()=={'is_staff':True,'permissions':['staff.manage']}
            # the same TOTP cannot be replayed
            assert (await session.post(BOT.replace('sessions','coordinator'),json={'code':pyotp.TOTP(secret).now()})).status_code==400
        async with factory() as db:
            row=await db.scalar(select(Session).where(Session.user_id==user_id,Session.channel=='telegram_bot',Session.revoked_at.is_(None)))
            assert (await resolve_principal(db,row)).is_staff
        # a new bot session (e.g. after 12 h) starts without staff again
        async with as_bot(app) as bot:await bot.post(BOT,json={'telegram_user_id':10001})
        async with factory() as db:
            row=await db.scalar(select(Session).where(Session.user_id==user_id,Session.channel=='telegram_bot',Session.revoked_at.is_(None)))
            assert not (await resolve_principal(db,row)).is_staff
        # web sessions cannot use the bot step
        assert (await client.post(BOT.replace('sessions','coordinator'),json={'code':''})).status_code==403
    finally:await client.aclose()

@pytest.mark.asyncio
async def test_coordinator_step_follows_the_web_rule_where_demo_codes_admit_staff_without_totp(bot_app,monkeypatch):
    app,factory,_=bot_app;client,user_id=await linked(app,factory);monkeypatch.setattr(get_settings(),'demo_email_codes',True)
    try:
        await staff_member(factory,user_id)
        async with as_bot(app) as bot:token=(await bot.post(BOT,json={'telegram_user_id':10001})).json()['session_token']
        async with session_client(app,token) as session:
            ok=await session.post(BOT.replace('sessions','coordinator'),json={})
            assert ok.status_code==200 and ok.json()['is_staff']
    finally:await client.aclose()

@pytest.mark.asyncio
async def test_bot_routes_webhook_and_bot_sessions_answer_only_inside_the_server(bot_app):
    app,factory,_=bot_app;client,_=await linked(app,factory)
    # every request from the internet passes the site's proxy (stage nginx sets these on /api/)
    proxied={'X-Forwarded-Proto':'https','X-Forwarded-Prefix':'/deti-marii'}
    try:
        async with as_bot(app) as bot:
            outside=await bot.post(BOT,json={'telegram_user_id':10001},headers=proxied);assert outside.status_code==404,outside.text
            for header in ('X-Forwarded-For','X-Real-IP','Forwarded'):
                assert (await bot.post(BOT,json={'telegram_user_id':10001},headers={header:'203.0.113.7'})).status_code==404
            token=(await bot.post(BOT,json={'telegram_user_id':10001})).json()['session_token']
        async with session_client(app,token) as session:
            assert (await session.get(BASE)).status_code==200
            assert (await session.get(BASE,headers=proxied)).status_code==401
            assert (await session.post(BOT.replace('sessions','coordinator'),json={},headers=proxied)).status_code in (401,404)
        hook=await client.post('/api/v1/integrations/telegram/webhook',json=update('bind_'+'a'*43),headers={'X-Telegram-Bot-Api-Secret-Token':'fixture_webhook_secret_'+('0'*32),**proxied})
        assert hook.status_code==404,hook.text
    finally:await client.aclose()
