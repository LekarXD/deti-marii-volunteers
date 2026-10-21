import hashlib
import hmac
import time
from uuid import UUID
from fastapi import APIRouter,Depends,Query,Request
from pydantic import ValidationError
from sqlalchemy import func,select,text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal,require_permission
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.models import OutboxMessage,User
from . import service
from .models import DeliveryAttempt,NotificationDelivery,NotificationTemplate,NotificationWebhookReceipt
from .schemas import AudienceCommand,AudienceView,DeliveryList,EnqueuedView,NotificationPreferenceCommand,PreferenceView,SendAudienceCommand,TemplateInput,TemplateList,TemplateUpdate,TemplateView,NotificationVersionCommand,WebhookInput,WebhookView,DeliveryAttemptPage,NotificationReadinessView,NotificationRecipientPage
router=APIRouter(prefix='/api/v1',tags=['notifications'])

@router.get('/me/notification-preferences',operation_id='notification_preferences',response_model=PreferenceView)
async def preferences(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.preference_view(db,principal)

@router.put('/me/notification-preferences',operation_id='notification_preferences_save',response_model=PreferenceView)
async def preferences_save(body:NotificationPreferenceCommand,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    result=await service.save_preferences(db,principal,body,request.headers.get('Idempotency-Key'))
    await db.commit()
    return result

@router.get('/coord/notification-templates',operation_id='notification_template_list',response_model=TemplateList)
async def templates(limit:int=Query(30,ge=1,le=100),cursor:str|None=Query(None,max_length=100),principal:Principal=Depends(require_permission('notifications.manage')),db:AsyncSession=Depends(get_db)):
    query=select(NotificationTemplate).where(NotificationTemplate.foundation_id==principal.foundation_id)
    if cursor:query=query.where(NotificationTemplate.key>cursor)
    rows=(await db.scalars(query.order_by(NotificationTemplate.key).limit(limit+1))).all()
    return {'items':[await service.template_view(db,row) for row in rows[:limit]],'next_cursor':rows[limit-1].key if len(rows)>limit else None}

@router.post('/coord/notification-templates',operation_id='notification_template_create',response_model=TemplateView)
async def template_create(body:TemplateInput,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    result=await service.create_template(db,principal,body,request.headers.get('Idempotency-Key'))
    await db.commit()
    return result

@router.patch('/coord/notification-templates/{tid}',operation_id='notification_template_edit',response_model=TemplateView)
async def template_edit(tid:UUID,body:TemplateUpdate,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    result=await service.mutate_template(db,principal,tid,body,request.headers.get('Idempotency-Key'),'edit')
    await db.commit()
    return result

@router.post('/coord/notification-templates/{tid}/publish',operation_id='notification_template_publish',response_model=TemplateView)
async def template_publish(tid:UUID,body:NotificationVersionCommand,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    result=await service.mutate_template(db,principal,tid,body,request.headers.get('Idempotency-Key'),'publish')
    await db.commit()
    return result

@router.post('/coord/notification-templates/{tid}/archive',operation_id='notification_template_archive',response_model=TemplateView)
async def template_archive(tid:UUID,body:NotificationVersionCommand,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    result=await service.mutate_template(db,principal,tid,body,request.headers.get('Idempotency-Key'),'archive')
    await db.commit()
    return result

@router.post('/coord/notifications/audience-preview',operation_id='notification_audience_preview',response_model=AudienceView)
async def preview(body:AudienceCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    result=await service.preview(db,principal,body)
    await db.commit()
    return result

@router.post('/coord/notifications/send',operation_id='notification_audience_send',response_model=EnqueuedView)
async def send(body:SendAudienceCommand,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    result=await service.enqueue_preview(db,principal,body,request.headers.get('Idempotency-Key'))
    await db.commit()
    return result

@router.get('/coord/notifications/recipients',operation_id='notification_recipients',response_model=NotificationRecipientPage)
async def recipients(q:str=Query('',max_length=100),cursor:UUID|None=None,limit:int=Query(30,ge=1,le=100),principal:Principal=Depends(require_permission('notifications.manage')),db:AsyncSession=Depends(get_db)):
    query=select(User).where(User.foundation_id==principal.foundation_id,User.account_state=='active')
    if q.strip():
        normalized=func.translate(func.lower(User.display_name),'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ','абвгдеёжзийклмнопрстуфхцчшщъыьэюя')
        query=query.where(normalized.contains(q.strip().casefold(),autoescape=True))
    if cursor:query=query.where(User.id>cursor)
    rows=(await db.scalars(query.order_by(User.id).limit(limit+1))).all()
    return {'items':[{'id':u.id,'display_name':u.display_name} for u in rows[:limit]],'next_cursor':rows[limit-1].id if len(rows)>limit else None}

@router.get('/coord/notification-deliveries',operation_id='notification_deliveries',response_model=DeliveryList)
async def deliveries(limit:int=Query(20,ge=1,le=50),cursor:UUID|None=None,principal:Principal=Depends(require_permission('notifications.manage')),db:AsyncSession=Depends(get_db)):
    query=select(NotificationDelivery).where(NotificationDelivery.foundation_id==principal.foundation_id)
    if cursor:query=query.where(NotificationDelivery.id>cursor)
    rows=(await db.scalars(query.order_by(NotificationDelivery.id).limit(limit+1))).all()
    result=[]
    for row in rows[:limit]:
        attempts=(await db.scalars(select(DeliveryAttempt).where(DeliveryAttempt.delivery_id==row.id).order_by(DeliveryAttempt.attempt_number.desc()).limit(21))).all()
        result.append({'id':row.id,'recipient_user_id':row.recipient_user_id,'template_version_id':row.template_version_id,'channel':row.channel,'state':row.state,'version':row.version,'next_attempt_at':(await db.get(OutboxMessage,row.outbox_id)).defer_until,'attempts_next_cursor':attempts[19].attempt_number if len(attempts)>20 else None,'attempts':[{'attempt_number':a.attempt_number,'state':a.state,'error_code':a.error_code,'started_at':a.started_at,'completed_at':a.completed_at} for a in attempts[:20]]})
    return {'items':result,'next_cursor':rows[limit-1].id if len(rows)>limit else None}

@router.get('/coord/notification-deliveries/{delivery_id}/attempts',operation_id='notification_delivery_attempts',response_model=DeliveryAttemptPage)
async def attempts(delivery_id:UUID,before:int|None=Query(None,ge=1),limit:int=Query(20,ge=1,le=100),principal:Principal=Depends(require_permission('notifications.manage')),db:AsyncSession=Depends(get_db)):
    row=await db.scalar(select(NotificationDelivery).where(NotificationDelivery.id==delivery_id,NotificationDelivery.foundation_id==principal.foundation_id))
    if row is None:raise ApiError(404,'delivery_not_found','Доставка не найдена')
    query=select(DeliveryAttempt).where(DeliveryAttempt.delivery_id==row.id)
    if before:query=query.where(DeliveryAttempt.attempt_number<before)
    rows=(await db.scalars(query.order_by(DeliveryAttempt.attempt_number.desc()).limit(limit+1))).all()
    return {'items':[{'attempt_number':a.attempt_number,'state':a.state,'error_code':a.error_code,'started_at':a.started_at,'completed_at':a.completed_at} for a in rows[:limit]],'next_cursor':rows[limit-1].attempt_number if len(rows)>limit else None}

@router.get('/coord/notifications/provider-readiness',operation_id='notification_provider_readiness',response_model=NotificationReadinessView)
async def provider_readiness(principal:Principal=Depends(require_permission('notifications.manage'))):
    from app.integrations.delivery.email import readiness
    value=readiness()
    return {**value,'webhook_state':'configured' if get_settings().email_webhook_secret else 'unavailable','external_send_enabled':value['state']=='available','channels':[{'channel':'in_app','state':'available','reason':'Внутренние уведомления сохраняются в платформе'},value]}

@router.post('/integrations/email/webhook',operation_id='notification_email_webhook',response_model=WebhookView)
async def webhook(request:Request,db:AsyncSession=Depends(get_db)):
    secret=get_settings().email_webhook_secret
    if not secret:raise ApiError(503,'webhook_unavailable','Webhook почтового провайдера не настроен',retryable=True)
    timestamp=request.headers.get('X-Webhook-Timestamp','')
    signature=request.headers.get('X-Webhook-Signature','')
    if not timestamp.isdigit() or len(timestamp)>12 or abs(int(timestamp)-int(time.time()))>300 or len(signature)!=64:
        raise ApiError(401,'invalid_webhook_signature','Подпись недействительна')
    chunks=[]
    size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>65536:raise ApiError(413,'webhook_too_large','Событие превышает лимит')
        chunks.append(chunk)
    raw=b''.join(chunks)
    expected=hmac.new(secret.encode(),timestamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected,signature):raise ApiError(401,'invalid_webhook_signature','Подпись недействительна')
    try:body=WebhookInput.model_validate_json(raw)
    except ValidationError:raise ApiError(422,'invalid_webhook_event','Некорректное событие')
    key=int(hashlib.sha256(('email-webhook:'+body.event_id).encode()).hexdigest()[:15],16)
    await db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':key})
    prior=await db.scalar(select(NotificationWebhookReceipt).where(NotificationWebhookReceipt.event_id==body.event_id))
    digest=hashlib.sha256(raw).hexdigest()
    if prior:
        if prior.body_hash!=digest:raise ApiError(409,'webhook_event_conflict','Идентификатор события использован повторно')
        return {'status':'replayed'}
    row=await db.scalar(select(NotificationDelivery).where(NotificationDelivery.provider_message_id==body.message_id,NotificationDelivery.foundation_id==get_settings().foundation_id).with_for_update())
    if row is None:raise ApiError(404,'delivery_not_found','Доставка не найдена')
    db.add(NotificationWebhookReceipt(event_id=body.event_id,body_hash=digest,provider_message_id=body.message_id,state=body.state))
    ignored=int(timestamp)<row.last_webhook_at
    if not ignored:
        row.state=body.state
        row.last_webhook_at=int(timestamp)
        row.version+=1
        outbox=await db.get(OutboxMessage,row.outbox_id)
        outbox.state=body.state
    await db.commit()
    return {'status':'ignored_stale' if ignored else 'applied'}
