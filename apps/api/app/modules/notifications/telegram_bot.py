"""Server-to-server access for @-bot: a volunteer-scoped session per verified Telegram binding.

The bot proves itself with OPORA_TELEGRAM_BOT_API_SECRET and names a Telegram user. If that user has an
active binding, it receives an ordinary session of the bound account (channel='telegram_bot') and then calls
the same /api/v1 routes as the web app. The session carries no staff permissions until a coordinator passes
POST .../coordinator with a TOTP or recovery code (or, where the web app itself lets staff in without TOTP —
OPORA_DEMO_EMAIL_CODES on staging — by that same rule). Revoking the binding revokes these sessions.

All of this works only inside the server: the bot calls the API directly (http://api:8001), while every request
from the internet passes the site's proxy, which always adds forwarding headers. Such requests get 404 on the
bot routes and the webhook, and a bot session sent through the proxy is rejected even with the secret.
"""
import secrets
from datetime import timedelta,timezone
from uuid import UUID
from fastapi import APIRouter,Depends,Header,Request
from pydantic import BaseModel,ConfigDict,Field
from sqlalchemy import select,update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.audit import audit
from app.core.auth import Principal,get_principal,get_session_row,resolve_principal
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.crypto import digest,seal
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.models import MfaFactor,Session,StaffMembership,User
from app.modules.auth.mfa import consume_code
from app.core.rate_limit import rate_limit
from .telegram_config import get_telegram_settings
from .telegram_models import TelegramBinding
router=APIRouter(prefix='/api/v1/integrations/telegram/bot',tags=['notifications'])
SESSION_HOURS=12
# Set by the proxies in front of the API (stage nginx: /api/ → api:8001 always sets X-Forwarded-Proto and -Prefix).
PROXY_HEADERS=('x-forwarded-for','x-forwarded-proto','x-forwarded-prefix','x-forwarded-host','forwarded','x-real-ip')

def via_proxy(request):return any(name in request.headers for name in PROXY_HEADERS)

def internal_only(request):
    if via_proxy(request):raise ApiError(404,'not_found','Не найдено')

def check_bot_request(request):
    """A bot session counts only on a direct call with the service secret."""
    if via_proxy(request):raise ApiError(401,'telegram_bot_unauthorized','Бот не подтверждён')
    check_bot_secret(request.headers.get('authorization',''))

def check_bot_secret(authorization):
    config=get_telegram_settings()
    if not config.bot_api_configured():raise ApiError(503,'telegram_bot_api_unavailable','Доступ бота к платформе не настроен')
    scheme,_,supplied=authorization.partition(' ')
    if scheme.lower()!='bearer' or not secrets.compare_digest(supplied.encode(),config.bot_api_secret.get_secret_value().encode()):raise ApiError(401,'telegram_bot_unauthorized','Бот не подтверждён')

async def revoke_bot_sessions(db,foundation_id,user_id):
    await db.execute(update(Session).where(Session.foundation_id==foundation_id,Session.user_id==user_id,Session.channel=='telegram_bot',Session.revoked_at.is_(None)).values(revoked_at=utcnow()))

class BotSessionCommand(BaseModel):
    model_config=ConfigDict(extra='forbid')
    telegram_user_id:int=Field(gt=0,lt=2**52)
class BotSessionView(BaseModel):
    user_id:UUID
    display_name:str
    session_token:str
    expires_at:str

@router.post('/sessions',response_model=BotSessionView,operation_id='telegram_bot_session_create')
async def open_session(body:BotSessionCommand,request:Request,authorization:str=Header(''),db:AsyncSession=Depends(get_db)):
    internal_only(request);check_bot_secret(authorization)
    await rate_limit(db,f'telegram-bot:{body.telegram_user_id}','telegram_bot_session',limit=30,seconds=300)
    binding=await db.scalar(select(TelegramBinding).where(TelegramBinding.foundation_id==get_settings().foundation_id,TelegramBinding.telegram_user_id==body.telegram_user_id,TelegramBinding.revoked_at.is_(None)))
    user=await db.get(User,binding.user_id) if binding else None
    if binding is None or user is None or user.account_state!='active' or user.foundation_id!=binding.foundation_id:raise ApiError(404,'telegram_not_linked','Этот Telegram не привязан к профилю')
    # One live bot session per volunteer: a new one replaces the previous.
    await revoke_bot_sessions(db,binding.foundation_id,binding.user_id)
    token=secrets.token_urlsafe(48);expires=utcnow()+timedelta(hours=SESSION_HOURS)
    db.add(Session(foundation_id=binding.foundation_id,token_hash=digest(token),csrf_hash=digest(secrets.token_urlsafe(32)),csrf_cipher=seal(''),user_id=binding.user_id,expires_at=expires,channel='telegram_bot'))
    await db.commit()
    return BotSessionView(user_id=binding.user_id,display_name=user.display_name,session_token=token,expires_at=expires.astimezone(timezone.utc).isoformat())


class BotCoordinatorCommand(BaseModel):
    model_config=ConfigDict(extra='forbid')
    code:str=Field('',max_length=100)
class BotCoordinatorView(BaseModel):
    is_staff:bool
    permissions:list[str]

@router.post('/coordinator',response_model=BotCoordinatorView,operation_id='telegram_bot_coordinator')
async def elevate(body:BotCoordinatorCommand,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    internal_only(request);session=await get_session_row(request,db)
    if session.channel!='telegram_bot':raise ApiError(403,'telegram_bot_session_required','Только для сессии бота')
    await rate_limit(db,principal.actor_id,'telegram_bot_coordinator',limit=10,seconds=300)
    if not await db.scalar(select(StaffMembership.id).where(StaffMembership.user_id==principal.user_id,StaffMembership.foundation_id==principal.foundation_id,StaffMembership.revoked_at.is_(None))):
        raise ApiError(403,'staff_required','Этот профиль не сотрудник фонда')
    if not get_settings().demo_email_codes:
        if not await db.scalar(select(MfaFactor.id).where(MfaFactor.user_id==principal.user_id,MfaFactor.confirmed_at.is_not(None))):
            raise ApiError(403,'mfa_enrollment_required','Сначала включите вход по коду на сайте')
        _,accepted=await consume_code(db,principal.user_id,body.code.strip())
        if not accepted:
            await db.commit();raise ApiError(400,'mfa_invalid','Код недействителен')
    session.mfa_at=utcnow()
    audit(db,principal,'notifications.telegram.coordinator','session',session.id)
    await db.flush();fresh=await resolve_principal(db,session);await db.commit()
    return BotCoordinatorView(is_staff=fresh.is_staff,permissions=sorted(fresh.permissions))
