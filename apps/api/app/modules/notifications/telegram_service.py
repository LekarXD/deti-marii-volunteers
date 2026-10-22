"""One-use private-chat proof; it grants no notification or news consent."""
import hashlib,re,secrets
from datetime import timedelta,timezone
from uuid import UUID
from sqlalchemy import select,text
from app.core.auth import authz_guard,resolve_principal
from app.core.audit import audit
from app.core.clock import utcnow
from app.core.crypto import digest,seal,unseal
from app.core.errors import ApiError
from app.core.idempotency import begin_command,finish_command
from app.core.models import ContactChannel,Session,User
from app.core.rate_limit import rate_limit
from .telegram_bot import revoke_bot_sessions
from .telegram_config import get_telegram_settings
from .telegram_models import TelegramBinding,TelegramLinkToken
from .telegram_schemas import TelegramBindingView,TelegramLinkTokenView
PURPOSE='telegram_bind'

async def verified_identity(db,principal):
    await authz_guard(db,principal)
    if principal.user_id is None:raise ApiError(403,'verified_identity_required','Сначала войдите по подтверждённой почте')
    if not await db.scalar(select(ContactChannel.id).join(User,User.id==ContactChannel.user_id).where(User.id==principal.user_id,User.foundation_id==principal.foundation_id,User.account_state=='active',ContactChannel.type=='email',ContactChannel.verified_at.is_not(None)).limit(1)):raise ApiError(403,'verified_identity_required','Сначала подтвердите почту своего аккаунта')

async def current_binding(db,principal,lock=False):
    query=select(TelegramBinding).where(TelegramBinding.foundation_id==principal.foundation_id,TelegramBinding.user_id==principal.user_id,TelegramBinding.revoked_at.is_(None))
    return await db.scalar(query.with_for_update() if lock else query)

async def status_view(db,principal):
    config=get_telegram_settings();configured=config.configured();binding=await current_binding(db,principal)
    if binding:return TelegramBindingView(state='linked',configured=configured,binding_id=binding.id,version=binding.version,verified_at=binding.verified_at.astimezone(timezone.utc),reason='Telegram подключён: приглашения, напоминания и сообщения координатора приходят в бот фонда.')
    if not configured:return TelegramBindingView(state='unavailable',configured=False,reason='Бот для привязки пока не настроен. Доступны уведомления в кабинете и настроенная почта.')
    token=await db.scalar(select(TelegramLinkToken).where(TelegramLinkToken.foundation_id==principal.foundation_id,TelegramLinkToken.user_id==principal.user_id,TelegramLinkToken.session_id==principal.session_id,TelegramLinkToken.purpose==PURPOSE,TelegramLinkToken.revoked_at.is_(None),TelegramLinkToken.expires_at>utcnow()).order_by(TelegramLinkToken.created_at.desc(),TelegramLinkToken.id.desc()).limit(1))
    if token and token.consumed_at is None:return TelegramBindingView(state='pending',configured=True,token_id=token.id,token_expires_at=token.expires_at.astimezone(timezone.utc),reason='Откройте личный чат с ботом по одноразовой ссылке и нажмите «Начать».')
    if token and token.outcome=='conflict':return TelegramBindingView(state='conflict',configured=True,reason='Этот Telegram уже привязан. Используйте другой аккаунт Telegram или отключите прежнюю привязку.')
    return TelegramBindingView(state='disconnected',configured=True,reason='Telegram не привязан. Указанный в анкете username не подтверждает владение аккаунтом.')

async def read_status(db,principal):
    await verified_identity(db,principal)
    return await status_view(db,principal)

async def revoke_tokens(db,principal):
    rows=(await db.scalars(select(TelegramLinkToken).where(TelegramLinkToken.foundation_id==principal.foundation_id,TelegramLinkToken.user_id==principal.user_id,TelegramLinkToken.purpose==PURPOSE,TelegramLinkToken.consumed_at.is_(None),TelegramLinkToken.revoked_at.is_(None)).with_for_update())).all()
    for row in rows:row.revoked_at=utcnow();row.token_cipher=None

async def token_view(db,principal,id):
    row=await db.scalar(select(TelegramLinkToken).where(TelegramLinkToken.id==id,TelegramLinkToken.foundation_id==principal.foundation_id,TelegramLinkToken.user_id==principal.user_id,TelegramLinkToken.session_id==principal.session_id,TelegramLinkToken.purpose==PURPOSE))
    if row is None:raise ApiError(409,'telegram_link_session_changed','Создайте новую ссылку в текущей сессии')
    state='revoked' if row.revoked_at else 'consumed' if row.consumed_at else 'expired' if row.expires_at<=utcnow() else 'issued'
    url=None
    if state=='issued' and row.token_cipher:url=f'https://t.me/{get_telegram_settings().username()}?start={unseal(row.token_cipher)}'
    return TelegramLinkTokenView(id=row.id,state=state,expires_at=row.expires_at.astimezone(timezone.utc),start_url=url)

async def issue_token(db,principal,key):
    await verified_identity(db,principal)
    config=get_telegram_settings()
    if not config.configured():raise ApiError(503,'telegram_binding_unavailable','Бот для привязки пока не настроен')
    await rate_limit(db,f'{principal.foundation_id}:{principal.user_id}','telegram_link_issue',limit=6,seconds=300)
    previous=await begin_command(db,principal,'notifications.telegram.issue',key,{})
    if previous is not None:return await token_view(db,principal,UUID(previous['token_id']))
    if await current_binding(db,principal):raise ApiError(409,'telegram_already_linked','Сначала отключите текущую привязку')
    await revoke_tokens(db,principal)
    raw='bind_'+secrets.token_urlsafe(32);row=TelegramLinkToken(foundation_id=principal.foundation_id,user_id=principal.user_id,session_id=principal.session_id,token_hash=digest(raw),token_cipher=seal(raw),purpose=PURPOSE,expires_at=utcnow()+timedelta(minutes=10));db.add(row);await db.flush()
    audit(db,principal,'notifications.telegram.issue','telegram_link_token',row.id,('purpose','expires_at'))
    # The generic receipt contains only the ID, never the bearer URL/token.
    await finish_command(db,principal,'notifications.telegram.issue',key,{'token_id':str(row.id)})
    return await token_view(db,principal,row.id)

async def disconnect(db,principal,command,key):
    await verified_identity(db,principal)
    previous=await begin_command(db,principal,'notifications.telegram.disconnect',key,command.model_dump())
    if previous is not None:return await status_view(db,principal)
    binding=await current_binding(db,principal,True)
    if command.expected_version!=(binding.version if binding else 0):raise ApiError(409,'version_conflict','Привязка изменилась. Обновите состояние')
    if binding:binding.revoked_at=utcnow();binding.version+=1;await revoke_bot_sessions(db,principal.foundation_id,principal.user_id)
    await revoke_tokens(db,principal)
    audit(db,principal,'notifications.telegram.disconnect','user',principal.user_id,('telegram_binding',))
    await finish_command(db,principal,'notifications.telegram.disconnect',key,{'state':'disconnected'})
    await db.flush();return await status_view(db,principal)

async def consume_update(db,update):
    config=get_telegram_settings();message=update.get('message') if isinstance(update,dict) else None
    if not isinstance(message,dict):return 'ignored'
    sender,chat=message.get('from'),message.get('chat');content=message.get('text')
    if not isinstance(sender,dict) or not isinstance(chat,dict) or not isinstance(content,str) or len(content)>128:return 'ignored'
    sender_id,chat_id=sender.get('id'),chat.get('id')
    if type(sender_id) is not int or not 0<sender_id<2**52 or type(chat_id) is not int or chat_id!=sender_id or chat.get('type')!='private' or sender.get('is_bot') is not False:return 'ignored'
    match=re.fullmatch(r'/start(?:@([A-Za-z0-9_]+))?\s+(bind_[A-Za-z0-9_-]{43})',content.strip())
    if not match or match[1] and match[1].casefold()!=config.username().casefold():return 'ignored'
    token=await db.scalar(select(TelegramLinkToken).where(TelegramLinkToken.token_hash==digest(match[2]),TelegramLinkToken.purpose==PURPOSE))
    if token is None:return 'ignored'
    session=await db.get(Session,token.session_id,populate_existing=True)
    if session is None or session.foundation_id!=token.foundation_id or session.user_id!=token.user_id or session.revoked_at or session.expires_at<=utcnow():return 'ignored'
    try:
        principal=await resolve_principal(db,session);await verified_identity(db,principal)
    except ApiError:return 'ignored'
    token=await db.scalar(select(TelegramLinkToken).where(TelegramLinkToken.id==token.id).with_for_update().execution_options(populate_existing=True))
    if token.expires_at<=utcnow() or token.consumed_at or token.revoked_at:return 'ignored'
    lock=int.from_bytes(hashlib.sha256(f'telegram:{token.foundation_id}:{sender_id}'.encode()).digest()[:8],'big',signed=True)
    await db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':lock})
    occupied=await db.scalar(select(TelegramBinding.id).where(TelegramBinding.foundation_id==token.foundation_id,TelegramBinding.telegram_user_id==sender_id,TelegramBinding.revoked_at.is_(None)))
    token.consumed_at=utcnow();token.token_cipher=None
    if occupied or await current_binding(db,principal):
        token.outcome='conflict';audit(db,principal,'notifications.telegram.conflict','telegram_link_token',token.id);await db.flush();return 'conflict'
    binding=TelegramBinding(foundation_id=token.foundation_id,user_id=token.user_id,telegram_user_id=sender_id,chat_id=chat_id);db.add(binding);token.outcome='linked';await db.flush()
    audit(db,principal,'notifications.telegram.link','telegram_binding',binding.id,('verified_at',));return 'linked'
