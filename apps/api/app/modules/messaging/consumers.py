"""Transactional in-app notification consumer. Source version is checked at delivery."""
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import select, text
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.models import User, RegistrationSession
from app.worker.queue import enqueue_outbox
from .models import Conversation, ConversationMember, Message

LABELS={"interview.booked":"Встреча назначена", "interview.rescheduled":"Встреча перенесена", "interview.cancelled":"Встреча отменена", "interview.completed":"Встреча завершена", "interview.missed":"Не удалось встретиться", "interview.result_updated":"Итог встречи обновлён"}

def enqueue_notice(db,foundation_id,recipient_id,subject,body,*,topic='messages',source=None):
    """For authoritative, already-authorized non-scheduled system events only.
    Booking/reminder producers must use the source-bound internal event envelope.
    """
    return enqueue_outbox(db,foundation_id,"in_app",{"source":source,"topic":topic,"recipient_id":str(recipient_id),"subject":subject,"text":body})

async def deliver_internal(db,outbox,payload):
    from app.core.contact_policy import contact_guard
    await contact_guard(db,outbox.foundation_id)
    existing=await db.scalar(select(Message.id).where(Message.source_outbox_id==outbox.id))
    if existing:
        return "delivered"
    if payload.get('source') is not None:
        from .registry import notice_source
        source=payload['source']
        if not isinstance(source,dict) or not isinstance(source.get('kind'),str):return 'unavailable'
        resolver=notice_source(source['kind'])
        if resolver is None:return 'unavailable'
        resolved=await resolver(db,outbox,source)
        if isinstance(resolved,str):return resolved if resolved.startswith('suppressed_') or resolved in ('unavailable','waiting_identity') else 'unavailable'
        if not isinstance(resolved,dict) or not {'recipient_id','subject','text','topic'}<=resolved.keys() or resolved.get('topic') not in ('assignments','learning','messages','news') or not isinstance(resolved.get('subject'),str) or not isinstance(resolved.get('text'),str):return 'unavailable'
        payload={key:resolved[key] for key in ('recipient_id','subject','text','topic')}
        try:payload['recipient_id']=str(UUID(str(payload['recipient_id'])))
        except (ValueError,TypeError):return 'unavailable'
    if payload.get("event", "").startswith("interview."):
        from app.modules.interviews.models import InterviewBooking
        booking=await db.scalar(select(InterviewBooking).where(InterviewBooking.id==UUID(payload['booking_id']),InterviewBooking.foundation_id==outbox.foundation_id).with_for_update())
        if booking is None or booking.version!=payload.get("booking_version"):
            return "suppressed_stale"
        event=payload["event"]
        if event not in LABELS:
            return "unavailable"
        expected={"interview.booked":"booked","interview.rescheduled":"booked","interview.cancelled":"cancelled","interview.completed":"completed","interview.missed":"missed","interview.result_updated":booking.status}[event]
        if booking.status!=expected or (event=="interview.result_updated" and booking.status not in ("completed","missed")):
            return "suppressed_stale"
        recipient=booking.user_id
        if recipient is None:
            registration=await db.get(RegistrationSession,booking.registration_id)
            if registration is None or registration.expires_at<=utcnow():
                return "suppressed_expired"
            return "waiting_identity"
        time=booking.starts_at.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y в %H:%M МСК")
        content=f"{LABELS[event]}. {time}. {booking.venue}"
    elif payload.get("event","").startswith("assignment."):
        from app.modules.activities.assignment_models import Assignment
        from app.modules.activities.calendar_models import EventOccurrence
        assignment=await db.scalar(select(Assignment).where(Assignment.id==UUID(payload['assignment_id']),Assignment.foundation_id==outbox.foundation_id).with_for_update())
        if assignment is None or assignment.version!=payload.get('assignment_version'):
            return "suppressed_stale"
        event=payload['event']
        labels={"assignment.invited":"Приглашение на занятие","assignment.approved":"Участие согласовано координатором","assignment.confirmed":"Участие подтверждено","assignment.declined":"Отказ от участия сохранён","assignment.cancelled":"Участие отменено"}
        expected={"assignment.invited":"invited","assignment.approved":"invited","assignment.confirmed":"confirmed","assignment.declined":"declined","assignment.cancelled":"cancelled"}
        if event not in labels:
            return "unavailable"
        if assignment.status!=expected[event] or (event=='assignment.approved' and assignment.approved_at is None):
            return "suppressed_stale"
        occurrence=await db.scalar(select(EventOccurrence).where(EventOccurrence.id==assignment.occurrence_id,EventOccurrence.foundation_id==outbox.foundation_id))
        if occurrence is None or (assignment.status in ('invited','confirmed') and occurrence.status!='scheduled'):
            return "suppressed_stale"
        recipient=assignment.user_id
        when=occurrence.starts_at.astimezone(ZoneInfo('Europe/Moscow')).strftime('%d.%m.%Y в %H:%M МСК')
        content=f"{labels[event]}. {occurrence.title}. {when}. {occurrence.location}"
    else:
        # General notices are internal persisted events, not a broadcast interface.
        if outbox.channel!="in_app" or not payload.get("recipient_id"):
            return "unavailable"
        recipient=UUID(payload['recipient_id'])
        content=f"{payload.get('subject','Уведомление фонда')}\n{payload.get('text','')}".strip()
        if len(content)>8000:
            return "unavailable"
    from app.modules.notifications.service import may_contact,sender_authorized,quiet_until,topic_for
    from app.modules.notifications.models import NotificationDelivery
    if not await sender_authorized(db,outbox.foundation_id,payload):
        return "suppressed_authz"
    allowed,reason=await may_contact(db,outbox.foundation_id,recipient,"in_app",topic_for(payload))
    if not allowed:
        return "suppressed_"+reason
    delivery=await db.scalar(select(NotificationDelivery).where(NotificationDelivery.outbox_id==outbox.id))
    if delivery:delivery.recipient_user_id=recipient
    outbox.defer_until=await quiet_until(db,outbox.foundation_id,recipient)
    if outbox.defer_until:return 'deferred_quiet'
    user=await db.get(User,recipient)
    if user is None or user.foundation_id!=outbox.foundation_id or user.account_state!="active":
        return "suppressed_recipient"
    direct_key=f"system:{outbox.foundation_id}:{recipient}"
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"),{"key":int(digest(direct_key)[:15],16)})
    if await db.scalar(select(Message.id).where(Message.source_outbox_id==outbox.id)):
        return "delivered"
    conversation=await db.scalar(select(Conversation).where(Conversation.direct_key==direct_key).with_for_update())
    if conversation is None:
        conversation=Conversation(id=uuid4(),foundation_id=outbox.foundation_id,title="Уведомления фонда",kind="system",direct_key=direct_key)
        db.add(conversation)
        await db.flush()
        db.add(ConversationMember(conversation_id=conversation.id,user_id=recipient))
    conversation.last_seq+=1
    conversation.version+=1
    conversation.updated_at=utcnow()
    db.add(Message(id=uuid4(),conversation_id=conversation.id,author_user_id=None,seq=conversation.last_seq,text=content,source_outbox_id=outbox.id))
    await db.flush()
    return "delivered"
