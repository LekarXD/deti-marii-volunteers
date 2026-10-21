"""Transactional in-app notification consumer. Source version is checked at delivery."""
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import select, text
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.models import User, RegistrationSession
from app.worker.queue import enqueue_outbox
from .models import Conversation, ConversationMember, Message

LABELS={"interview.booked":"Встреча назначена", "interview.rescheduled":"Встреча перенесена", "interview.cancelled":"Встреча отменена", "interview.completed":"Встреча завершена", "interview.missed":"Не удалось встретиться"}

def enqueue_notice(db,foundation_id,recipient_id,subject,body):
    """For authoritative, already-authorized non-scheduled system events only.
    Booking/reminder producers must use the source-bound internal event envelope.
    """
    return enqueue_outbox(db,foundation_id,"in_app",{"recipient_id":str(recipient_id),"subject":subject,"text":body})

async def deliver_internal(db,outbox,payload):
    existing=await db.scalar(select(Message.id).where(Message.source_outbox_id==outbox.id))
    if existing:
        return "delivered"
    if payload.get("event", "").startswith("interview."):
        from app.modules.interviews.models import InterviewBooking
        booking=await db.scalar(select(InterviewBooking).where(InterviewBooking.id==UUID(payload['booking_id']),InterviewBooking.foundation_id==outbox.foundation_id).with_for_update())
        if booking is None or booking.version!=payload.get("booking_version"):
            return "suppressed_stale"
        event=payload["event"]
        if event not in LABELS:
            return "unavailable"
        expected={"interview.booked":"booked","interview.rescheduled":"booked","interview.cancelled":"cancelled","interview.completed":"completed","interview.missed":"missed"}[event]
        if booking.status!=expected:
            return "suppressed_stale"
        recipient=booking.user_id
        if recipient is None:
            registration=await db.get(RegistrationSession,booking.registration_id)
            if registration is None or registration.expires_at<=utcnow():
                return "suppressed_expired"
            return "waiting_identity"
        time=booking.starts_at.astimezone(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y в %H:%M МСК")
        content=f"{LABELS[event]}. {time}. {booking.venue}"
    else:
        # General notices are internal persisted events, not a broadcast interface.
        if outbox.channel!="in_app" or not payload.get("recipient_id"):
            return "unavailable"
        recipient=UUID(payload['recipient_id'])
        content=f"{payload.get('subject','Уведомление фонда')}\n{payload.get('text','')}".strip()
        if len(content)>8000:
            return "unavailable"
    user=await db.get(User,recipient)
    if user is None or user.foundation_id!=outbox.foundation_id or user.account_state!="active":
        return "suppressed_recipient"
    direct_key=f"system:{outbox.foundation_id}:{recipient}"
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"),{"key":int(digest(direct_key)[:15],16)})
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
