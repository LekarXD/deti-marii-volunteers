"""Durable delivery outcomes; provider I/O follows a committed calling marker."""
from uuid import UUID
from sqlalchemy import func,select
from app.core.clock import utcnow
from app.core.contact_policy import contact_guard
from app.core.crypto import digest
from app.core.models import AuthChallenge,ContactChannel,OutboxMessage
from app.integrations.delivery.email import DeliveryOutcome,deliver_email,readiness
from app.worker.queue import fenced_update
from .models import DeliveryAttempt,NotificationDelivery,NotificationTemplate,NotificationTemplateVersion
from .service import may_contact,sender_authorized,quiet_until,topic_for

async def journal(db,outbox,payload):
    row=await db.scalar(select(NotificationDelivery).where(NotificationDelivery.outbox_id==outbox.id).with_for_update())
    if row is None:
        uid=payload.get('recipient_id')
        row=NotificationDelivery(foundation_id=outbox.foundation_id,outbox_id=outbox.id,channel=outbox.channel,recipient_user_id=UUID(uid) if uid else None,provider_message_id=f'<{outbox.id}@opora.local>' if outbox.channel=='email' else None)
        db.add(row)
        await db.flush()
    elif outbox.channel=='email' and row.provider_message_id is None:
        row.provider_message_id=f'<{outbox.id}@opora.local>'
    return row

async def new_attempt(db,delivery,state):
    last=await db.scalar(select(func.max(DeliveryAttempt.attempt_number)).where(DeliveryAttempt.delivery_id==delivery.id))
    attempt=DeliveryAttempt(delivery_id=delivery.id,attempt_number=(last or 0)+1,state=state)
    db.add(attempt)
    await db.flush()
    return attempt

async def check_email(db,outbox,payload):
    if payload.get('purpose') in ('login','contact_change'):
        try:identity=UUID(payload.get('challenge_id',''))
        except ValueError:return 'suppressed_stale_auth'
        challenge=await db.get(AuthChallenge,identity)
        if challenge is None or challenge.foundation_id!=outbox.foundation_id or challenge.consumed_at or challenge.expires_at<=utcnow() or challenge.token_hash!=digest(payload.get('token','')) or challenge.purpose!=payload.get('purpose'):
            return 'suppressed_stale_auth'
        if challenge.purpose=='contact_change':
            from app.core.models import Session
            session=await db.get(Session,challenge.bound_session_id)
            if session is None or session.revoked_at or session.expires_at<=utcnow() or session.user_id!=challenge.bound_user_id:return 'suppressed_stale_auth'
        return None
    if payload.get('purpose')!='notification' or not payload.get('recipient_id'):
        return 'unavailable'
    if not await sender_authorized(db,outbox.foundation_id,payload):return 'suppressed_authz'
    recipient=UUID(payload['recipient_id'])
    allowed,reason=await may_contact(db,outbox.foundation_id,recipient,'email',topic_for(payload))
    if not allowed:return 'suppressed_'+reason
    version=await db.get(NotificationTemplateVersion,UUID(payload['template_version_id']))
    template=await db.get(NotificationTemplate,version.template_id) if version else None
    if not template or template.foundation_id!=outbox.foundation_id or template.state=='archived':return 'suppressed_template'
    contact=await db.scalar(select(ContactChannel).where(ContactChannel.user_id==recipient,ContactChannel.type=='email'))
    if contact is None or contact.normalized_value!=payload.get('to'):return 'suppressed_contact_changed'
    return None

async def process_email(db,job,outbox,payload):
    if payload.get('purpose') not in ('login','contact_change'):await contact_guard(db,outbox.foundation_id)
    delivery=await journal(db,outbox,payload)
    latest=await db.scalar(select(DeliveryAttempt).where(DeliveryAttempt.delivery_id==delivery.id).order_by(DeliveryAttempt.attempt_number.desc()).limit(1))
    if delivery.state in ('delivered','bounced'):
        return DeliveryOutcome(delivery.state)
    if latest and latest.state=='calling':
        latest.state='unknown'
        latest.error_code='worker_interrupted_after_calling'
        latest.completed_at=utcnow()
        delivery.state=outbox.state='unknown'
        delivery.version+=1
        return DeliveryOutcome('unknown','worker_interrupted_after_calling')
    if latest and latest.state not in ('unavailable','queued','deferred_quiet'):
        return DeliveryOutcome(latest.state,latest.error_code)
    blocked=await check_email(db,outbox,payload)
    if blocked:
        attempt=await new_attempt(db,delivery,blocked)
        attempt.completed_at=utcnow()
        delivery.state=outbox.state=blocked
        delivery.version+=1
        return DeliveryOutcome(blocked)
    outbox.defer_until=await quiet_until(db,outbox.foundation_id,UUID(payload['recipient_id'])) if payload.get('purpose')=='notification' else None
    if outbox.defer_until:
        attempt=await new_attempt(db,delivery,'deferred_quiet')
        attempt.completed_at=utcnow()
        delivery.state=outbox.state='deferred_quiet'
        delivery.version+=1
        return DeliveryOutcome('deferred_quiet')
    if readiness()['state']=='unavailable':
        attempt=await new_attempt(db,delivery,'unavailable')
        attempt.completed_at=utcnow()
        attempt.error_code='provider_unavailable'
        delivery.state=outbox.state='unavailable'
        delivery.version+=1
        return DeliveryOutcome('unavailable','provider_unavailable')
    attempt=await new_attempt(db,delivery,'calling')
    delivery.state=outbox.state='calling'
    # A crash after this point is uncertain. A retry never blindly calls SMTP again.
    await db.commit()
    if payload.get('purpose') not in ('login','contact_change'):await contact_guard(db,outbox.foundation_id)
    blocked=await check_email(db,outbox,payload)
    if not blocked and payload.get('purpose')=='notification':
        outbox.defer_until=await quiet_until(db,outbox.foundation_id,UUID(payload['recipient_id']))
        if outbox.defer_until:blocked='deferred_quiet'
    result=DeliveryOutcome(blocked) if blocked else await deliver_email({**payload,'message_id':delivery.provider_message_id})
    await fenced_update(db,job.id,job.claim_token,state='running')
    attempt.state=result.state
    attempt.error_code=result.error_code
    attempt.completed_at=utcnow()
    await db.refresh(delivery,with_for_update=True)
    if delivery.last_webhook_at and delivery.state in ('delivered','bounced'):
        outbox.state=delivery.state
        delivery.version+=1
        return DeliveryOutcome(delivery.state)
    delivery.state=outbox.state=result.state
    delivery.version+=1
    return result

async def process_internal(db,job,outbox,payload):
    await contact_guard(db,outbox.foundation_id)
    delivery=await journal(db,outbox,payload)
    latest=await db.scalar(select(DeliveryAttempt).where(DeliveryAttempt.delivery_id==delivery.id).order_by(DeliveryAttempt.attempt_number.desc()).limit(1))
    if latest and latest.state not in ('waiting_identity','unavailable','deferred_quiet'):
        return latest.state
    attempt=await new_attempt(db,delivery,'processing')
    from app.modules.messaging.consumers import deliver_internal
    state=await deliver_internal(db,outbox,payload)
    attempt.state=state
    attempt.completed_at=utcnow()
    delivery.state=outbox.state=state
    delivery.version+=1
    return state
