import json,secrets
from fastapi import APIRouter,Depends,Header,Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal
from app.core.db import get_db
from app.core.errors import ApiError
from .telegram_config import get_telegram_settings
from .telegram_bot import internal_only
from .telegram_schemas import TelegramBindingView,TelegramLinkCommand,TelegramLinkTokenView,TelegramDisconnectCommand,TelegramWebhookView
from . import telegram_service as service
router=APIRouter(prefix='/api/v1',tags=['notifications'])

@router.get('/me/notification-channels/telegram',response_model=TelegramBindingView,operation_id='telegram_binding_status')
async def status(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.read_status(db,principal)
@router.post('/me/notification-channels/telegram/link-tokens',response_model=TelegramLinkTokenView,operation_id='telegram_link_token_create')
async def issue(body:TelegramLinkCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    result=await service.issue_token(db,principal,key);await db.commit();return result
@router.post('/me/notification-channels/telegram/disconnect',response_model=TelegramBindingView,operation_id='telegram_binding_disconnect')
async def disconnect(body:TelegramDisconnectCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    result=await service.disconnect(db,principal,body,key);await db.commit();return result
@router.post('/integrations/telegram/webhook',response_model=TelegramWebhookView,operation_id='telegram_binding_webhook')
async def webhook(request:Request,db:AsyncSession=Depends(get_db)):
    internal_only(request)  # the bot polls Telegram and forwards /start bind_… itself; nothing calls this from outside
    config=get_telegram_settings()
    if not config.configured():raise ApiError(503,'telegram_binding_unavailable','Бот для привязки пока не настроен')
    supplied=request.headers.get('X-Telegram-Bot-Api-Secret-Token','')
    if not secrets.compare_digest(supplied.encode(),config.webhook_secret.get_secret_value().encode()):raise ApiError(403,'telegram_webhook_invalid','Callback недействителен')
    data=bytearray()
    async for chunk in request.stream():
        if len(data)+len(chunk)>8192:raise ApiError(413,'telegram_update_too_large','Callback слишком большой')
        data.extend(chunk)
    try:update=json.loads(data)
    except (ValueError,UnicodeError):raise ApiError(422,'telegram_update_invalid','Callback недействителен') from None
    state=await service.consume_update(db,update);await db.commit();return TelegramWebhookView(state=state)
