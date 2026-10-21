import hashlib
import json
import string
from datetime import timedelta
from uuid import UUID,uuid4
from sqlalchemy import select
from app.core.audit import audit
from app.core.auth import authz_guard
from app.core.clock import utcnow
from app.core.contact_policy import contact_guard
from app.core.errors import ApiError
from app.core.idempotency import begin_command,finish_command
from app.core.models import ContactChannel,User,Foundation,Session
from app.integrations.delivery.email import readiness
from app.modules.crm.service import contact_preference
from app.worker.queue import enqueue_outbox
from .models import NotificationPreference,NotificationTemplate,NotificationTemplateVersion,NotificationAudiencePreview,NotificationDelivery

ALLOWED_FIELDS=frozenset({'volunteer_name','foundation_name'})

def validate_template(subject,body):
    if not subject.strip() or '\n' in subject or '\r' in subject or not body.strip():
        raise ApiError(422,'invalid_template','Заполните тему и текст. Тема должна быть одной строкой')
    fields=set()
    try:
        for _literal,name,spec,conversion in string.Formatter().parse(subject+'\n'+body):
            if name is not None:
                if name not in ALLOWED_FIELDS or spec or conversion:
                    raise ValueError()
                fields.add(name)
    except ValueError:
        raise ApiError(422,'invalid_template_fields','Доступны только {volunteer_name} и {foundation_name}, без формул и вложенных полей')
    return sorted(fields)

async def require_staff(db,principal,permission):
    await authz_guard(db,principal)
    if not principal.has_permission(permission):
        raise ApiError(403,'permission_denied','Недостаточно прав')

async def preferences(db,foundation_id,user_id):
    return await db.scalar(select(NotificationPreference).where(NotificationPreference.foundation_id==foundation_id,NotificationPreference.user_id==user_id))

async def may_contact(db,foundation_id,user_id,channel):
    await contact_guard(db,foundation_id)
    if (await contact_preference(db,foundation_id,user_id=user_id))['no_contact']:
        return False,'no_contact'
    pref=await preferences(db,foundation_id,user_id)
    if pref and pref.no_contact:
        return False,'no_contact'
    if channel=='email' and not (pref and pref.email_enabled):
        return False,'email_disabled'
    if channel=='in_app' and pref and not pref.in_app_enabled:
        return False,'in_app_disabled'
    return True,None

async def preference_view(db,principal):
    if principal.user_id is None:
        raise ApiError(403,'verified_account_required','Подтвердите почту')
    pref=await preferences(db,principal.foundation_id,principal.user_id)
    crm=(await contact_preference(db,principal.foundation_id,user_id=principal.user_id))['no_contact']
    return {'no_contact':pref.no_contact if pref else False,'email_enabled':pref.email_enabled if pref else False,'in_app_enabled':pref.in_app_enabled if pref else True,'effective_no_contact':crm or bool(pref and pref.no_contact),'version':pref.version if pref else 0,'email_provider_state':readiness()['state']}

async def save_preferences(db,principal,body,key):
    await authz_guard(db,principal)
    if principal.user_id is None:
        raise ApiError(403,'verified_account_required','Подтвердите почту')
    await contact_guard(db,principal.foundation_id)
    replay=await begin_command(db,principal,'notifications.preferences',key,body.model_dump(mode='json'))
    if replay is not None:return replay
    pref=await preferences(db,principal.foundation_id,principal.user_id)
    if (pref.version if pref else 0)!=body.expected_version:
        raise ApiError(409,'version_conflict','Настройки изменились',current_version=pref.version if pref else 0)
    if pref is None:
        pref=NotificationPreference(foundation_id=principal.foundation_id,user_id=principal.user_id,version=0)
        db.add(pref)
    pref.no_contact,pref.email_enabled,pref.in_app_enabled=body.no_contact,body.email_enabled,body.in_app_enabled
    pref.version+=1
    pref.updated_at=utcnow()
    await db.flush()
    audit(db,principal,'notifications.preferences','user',principal.user_id,('no_contact','email_enabled','in_app_enabled'))
    return await finish_command(db,principal,'notifications.preferences',key,await preference_view(db,principal))

async def template_row(db,principal,tid,lock=False):
    query=select(NotificationTemplate).where(NotificationTemplate.id==tid,NotificationTemplate.foundation_id==principal.foundation_id)
    if lock:query=query.with_for_update()
    row=await db.scalar(query)
    if row is None:raise ApiError(404,'template_not_found','Шаблон не найден')
    return row

async def template_view(db,row):
    version=await db.scalar(select(NotificationTemplateVersion).where(NotificationTemplateVersion.template_id==row.id).order_by(NotificationTemplateVersion.revision.desc()).limit(1))
    return {'id':str(row.id),'key':row.key,'channel':row.channel,'subject':row.subject,'body':row.body,'state':row.state,'version':row.version,'published_version_id':str(version.id) if version else None,'fields':validate_template(row.subject,row.body),'allowed_actions':['edit','publish','archive'] if row.state!='archived' else []}

async def create_template(db,principal,body,key):
    await require_staff(db,principal,'notifications.manage')
    replay=await begin_command(db,principal,'notifications.template.create',key,body.model_dump(mode='json'))
    if replay is not None:return replay
    validate_template(body.subject,body.body)
    if await db.scalar(select(NotificationTemplate.id).where(NotificationTemplate.foundation_id==principal.foundation_id,NotificationTemplate.key==body.key)):
        raise ApiError(409,'template_key_exists','Такой ключ шаблона уже существует')
    row=NotificationTemplate(foundation_id=principal.foundation_id,**body.model_dump())
    db.add(row)
    await db.flush()
    audit(db,principal,'notifications.template.create','notification_template',row.id,('subject','body'))
    return await finish_command(db,principal,'notifications.template.create',key,await template_view(db,row))

async def mutate_template(db,principal,tid,body,key,operation):
    await require_staff(db,principal,'notifications.manage')
    row=await template_row(db,principal,tid,lock=True)
    name=f'notifications.template.{operation}:{tid}'
    replay=await begin_command(db,principal,name,key,body.model_dump(mode='json'))
    if replay is not None:return replay
    if row.version!=body.expected_version:
        raise ApiError(409,'version_conflict','Шаблон изменился',current_version=row.version)
    if operation=='edit':
        validate_template(body.subject,body.body)
        row.subject,row.body,row.state=body.subject,body.body,'draft'
    elif operation=='publish':
        if row.state!='draft':raise ApiError(409,'template_not_draft','Для публикации нужен черновик')
        db.add(NotificationTemplateVersion(template_id=row.id,revision=row.version,subject=row.subject,body=row.body,fields=validate_template(row.subject,row.body),published_by=principal.user_id))
        row.state='published'
    elif operation=='archive':row.state='archived'
    row.version+=1
    row.updated_at=utcnow()
    await db.flush()
    audit(db,principal,'notifications.template.'+operation,'notification_template',row.id,('state','version'))
    return await finish_command(db,principal,name,key,await template_view(db,row))

async def published_version(db,principal,version_id):
    pair=(await db.execute(select(NotificationTemplateVersion,NotificationTemplate).join(NotificationTemplate,NotificationTemplate.id==NotificationTemplateVersion.template_id).where(NotificationTemplateVersion.id==version_id,NotificationTemplate.foundation_id==principal.foundation_id))).first()
    if not pair or pair[1].state=='archived':raise ApiError(404,'template_version_not_found','Опубликованный шаблон недоступен')
    return pair

async def audience_snapshot(db,principal,template,ids):
    users={u.id:u for u in (await db.scalars(select(User).where(User.id.in_(ids),User.foundation_id==principal.foundation_id,User.account_state=='active'))).all()}
    result=[]
    for uid in sorted(set(ids),key=str):
        user=users.get(uid)
        reason='user_unavailable' if user is None else None
        if user:
            allowed,reason=await may_contact(db,principal.foundation_id,uid,template.channel)
            if allowed and template.channel=='email':
                if readiness()['state']=='unavailable':reason='provider_unavailable'
                elif not await db.scalar(select(ContactChannel.id).where(ContactChannel.user_id==uid,ContactChannel.type=='email')):reason='verified_email_missing'
        result.append({'user_id':str(uid),'display_name':user.display_name if user else 'Получатель недоступен','eligible':reason is None,'reason':reason})
    return result

def preview_hash(version_id,snapshot):
    return hashlib.sha256(json.dumps({'version_id':str(version_id),'members':snapshot},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

async def preview(db,principal,body):
    await require_staff(db,principal,'notifications.manage')
    await contact_guard(db,principal.foundation_id)
    _version,template=await published_version(db,principal,body.template_version_id)
    snapshot=await audience_snapshot(db,principal,template,body.recipient_user_ids)
    row=NotificationAudiencePreview(foundation_id=principal.foundation_id,actor_user_id=principal.user_id,template_version_id=body.template_version_id,snapshot=snapshot,preview_hash=preview_hash(body.template_version_id,snapshot),expires_at=utcnow()+timedelta(minutes=15))
    db.add(row)
    await db.flush()
    return {'id':str(row.id),'template_version_id':str(row.template_version_id),'members':snapshot,'eligible_count':sum(x['eligible'] for x in snapshot),'preview_hash':row.preview_hash,'expires_at':row.expires_at.isoformat()}

async def enqueue_preview(db,principal,body,key):
    await require_staff(db,principal,'notifications.send')
    await contact_guard(db,principal.foundation_id)
    row=await db.scalar(select(NotificationAudiencePreview).where(NotificationAudiencePreview.id==body.preview_id,NotificationAudiencePreview.foundation_id==principal.foundation_id,NotificationAudiencePreview.actor_user_id==principal.user_id).with_for_update())
    if row is None:raise ApiError(404,'preview_not_found','Предпросмотр не найден')
    replay=await begin_command(db,principal,'notifications.send',key,body.model_dump(mode='json'))
    if replay is not None:return replay
    if row.consumed_at or row.expires_at<=utcnow():raise ApiError(409,'preview_expired','Обновите предпросмотр получателей')
    version,template=await published_version(db,principal,row.template_version_id)
    current=await audience_snapshot(db,principal,template,[UUID(x['user_id']) for x in row.snapshot])
    if body.preview_hash!=row.preview_hash or preview_hash(row.template_version_id,current)!=row.preview_hash:
        raise ApiError(409,'audience_changed','Получатели или их настройки изменились. Обновите предпросмотр')
    selected=[item for item in current if item['eligible']]
    if not selected:raise ApiError(409,'no_eligible_recipients','Нет получателей с разрешённым и доступным каналом')
    deliveries=[]
    for item in selected:
        uid=UUID(item['user_id'])
        foundation=await db.get(Foundation,principal.foundation_id)
        context={'volunteer_name':item['display_name'],'foundation_name':foundation.name}
        payload={'purpose':'notification','recipient_id':str(uid),'subject':version.subject.format_map(context),'text':version.body.format_map(context),'template_version_id':str(version.id),'actor_session_id':str(principal.session_id),'actor_user_id':str(principal.user_id)}
        if template.channel=='email':
            contact=await db.scalar(select(ContactChannel).where(ContactChannel.user_id==uid,ContactChannel.type=='email'))
            payload['to']=contact.normalized_value
        outbox=enqueue_outbox(db,principal.foundation_id,template.channel,payload)
        delivery=NotificationDelivery(id=uuid4(),foundation_id=principal.foundation_id,outbox_id=outbox.id,recipient_user_id=uid,template_version_id=version.id,channel=template.channel)
        db.add(delivery)
        deliveries.append(str(delivery.id))
    row.consumed_at=utcnow()
    audit(db,principal,'notifications.send','notification_audience_preview',row.id,('consumed_at',))
    return await finish_command(db,principal,'notifications.send',key,{'enqueued':len(deliveries),'delivery_ids':deliveries,'state':'queued'})

async def sender_authorized(db,foundation_id,payload):
    if payload.get('purpose')!='notification':
        return True
    try:
        session_id=UUID(payload.get('actor_session_id',''))
    except (ValueError,TypeError):
        return False
    session=await db.get(Session,session_id,populate_existing=True)
    if session is None or session.revoked_at or session.expires_at<=utcnow() or session.foundation_id!=foundation_id:
        return False
    from app.core.auth import resolve_principal
    try:
        actor=await resolve_principal(db,session)
    except ApiError:
        return False
    return actor.has_permission('notifications.send') and str(actor.user_id)==payload.get('actor_user_id')
