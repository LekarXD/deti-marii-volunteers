"""Explicit opt-in reminders inside Opora; never a Dobro API or external message."""
from datetime import datetime, timedelta, time
from uuid import UUID
from sqlalchemy import select
from app.core.auth import load_background_staff_authorization, lock_background_authorizations
from app.core.clock import utcnow
from app.core.idempotency import payload_hash
from app.core.models import MutationReceipt
from app.modules.messaging.consumers import enqueue_notice
from app.worker.queue import enqueue_job
from app.worker.registry import register_handler
from .models import DobroSettings
from .service import transfer_period, foundation_lock
from .calculation import ZONE

def capable(actor):
    return bool(actor and actor.has_permission('integrations.manage') and actor.has_permission('hours.review'))

def actionable(view, activity_id=None):
    return [row for group in view.groups if activity_id is None or group.activity.id == activity_id for row in group.rows if row.state != 'not_needed' and row.hours_due and not row.historical]

async def enqueue_once(db, settings, actor, period, reason, activity_id=None, deadline=None):
    # Existing durable receipts provide a unique key across job retries and settings
    # edits. No user identity can collide with this reserved internal actor prefix.
    key = f'{actor.user_id}:{reason}:{period if reason == "monthly" else str(activity_id)+":"+str(deadline)}'
    owner = f'dobro:{settings.foundation_id}'
    prior = await db.scalar(select(MutationReceipt).where(MutationReceipt.actor_id == owner, MutationReceipt.operation == 'dobro.reminder.enqueue', MutationReceipt.key == key))
    if prior: return False
    source = {'kind':'dobro_reminder', 'owner_id':str(actor.user_id), 'period':period, 'reason':reason, 'activity_id':str(activity_id) if activity_id else None, 'deadline':str(deadline) if deadline else None}
    outbox = enqueue_notice(db, settings.foundation_id, actor.user_id, 'Перенести часы в Добро.рф', '', topic='messages', source=source)
    db.add(MutationReceipt(actor_id=owner, operation='dobro.reminder.enqueue', key=key, payload_hash=payload_hash(source), result={'outbox_id':str(outbox.id)}))
    await db.flush()
    return True

async def run_reminders(db, context):
    initial = await db.get(DobroSettings, context.foundation_id)
    if not initial or not initial.reminders_enabled or not initial.reminder_owner_user_id: return {'state':'disabled'}
    await lock_background_authorizations(db, context.foundation_id, [initial.reminder_owner_user_id])
    actor = await load_background_staff_authorization(db, context.foundation_id, initial.reminder_owner_user_id)
    if not capable(actor): return {'state':'blocked_authorization'}
    await foundation_lock(db, actor)
    settings = await db.scalar(select(DobroSettings).where(DobroSettings.foundation_id == context.foundation_id).with_for_update().execution_options(populate_existing=True))
    if not settings.reminders_enabled or settings.reminder_owner_user_id != actor.user_id or settings.version != context.payload.get('settings_version'): return {'state':'superseded'}
    scheduled_for = datetime.fromisoformat(context.payload['scheduled_for'])
    if scheduled_for > utcnow(): return {'state':'not_due'}
    await context.fence(db)
    today = utcnow().astimezone(ZONE).date()
    prior_month = (today.replace(day=1)-timedelta(days=1)).strftime('%Y-%m')
    queued = 0
    if today.day >= settings.monthly_day:
        monthly = await transfer_period(db, actor, prior_month)
        if actionable(monthly): queued += await enqueue_once(db, settings, actor, prior_month, 'monthly')
    current_period = today.strftime('%Y-%m')
    current = await transfer_period(db, actor, current_period)
    for group in current.groups:
        due = actionable(current, group.activity.id)
        if due and any(row.deadline_state in ('risk','overdue') for row in due):
            queued += await enqueue_once(db, settings, actor, current_period, 'risk', group.activity.id, due[0].hard_deadline)
    tomorrow = datetime.combine(today+timedelta(days=1), time(9), ZONE)
    enqueue_job(db, settings.foundation_id, 'dobro.reminders.scan', {'settings_version':settings.version, 'scheduled_for':tomorrow.isoformat()}, available_at=tomorrow)
    await db.flush()
    return {'state':'scheduled', 'queued':queued}

register_handler('dobro.reminders.scan', run_reminders, timeout_seconds=90)
