"""Rebuild reminder content under the current owner, grant and settings scope."""
from uuid import UUID
from sqlalchemy import select
from app.core.auth import load_background_staff_authorization, assert_background_authorizations_locked
from app.core.errors import ApiError
from app.modules.messaging.registry import register_notice_source
from .models import DobroSettings
from .service import transfer_period, foundation_lock
from .jobs import capable, actionable

async def lock_subjects(db, outbox, source):
    try: return [UUID(source['owner_id'])]
    except (ValueError, KeyError, TypeError): return []

async def resolve_reminder(db, outbox, source):
    try:
        owner_id = UUID(source['owner_id'])
        period = str(source['period'])
        activity_id = UUID(source['activity_id']) if source.get('activity_id') else None
    except (ValueError, KeyError, TypeError): return 'suppressed_dobro_source'
    try: assert_background_authorizations_locked(db, outbox.foundation_id, [owner_id])
    except ApiError: return 'suppressed_dobro_authorization'
    actor = await load_background_staff_authorization(db, outbox.foundation_id, owner_id)
    if not capable(actor): return 'suppressed_dobro_revoked'
    # Hold the same domain fence as manual attestations through the actual message
    # insert. A different coordinator must not settle hours between projection and
    # delivery, otherwise an already-completed transfer would be announced as due.
    # This path never acquires minute-ledger subject locks while holding the fence.
    await foundation_lock(db, actor)
    settings = await db.scalar(select(DobroSettings).where(DobroSettings.foundation_id == outbox.foundation_id).execution_options(populate_existing=True))
    if not settings or not settings.reminders_enabled or settings.reminder_owner_user_id != owner_id: return 'suppressed_dobro_disabled'
    try: view = await transfer_period(db, actor, period)
    except ApiError: return 'suppressed_dobro_source'
    rows = actionable(view, activity_id)
    if not rows: return 'suppressed_dobro_complete'
    positive = sum(max(0,row.hours_due) for row in rows)
    corrections = sum(max(0,-row.hours_due) for row in rows)
    if source.get('reason') == 'risk':
        if not activity_id or not all(str(row.hard_deadline) == source.get('deadline') for row in rows): return 'suppressed_dobro_stale'
        if not any(row.deadline_state in ('risk','overdue') for row in rows): return 'suppressed_dobro_not_at_risk'
        heading = f'Проверьте срок Добро.рф: {rows[0].hard_deadline:%d.%m.%Y}.'
    elif source.get('reason') == 'monthly' and activity_id is None:
        heading = f'Пора перенести часы за {period}. Рабочий срок: {view.work_deadline:%d.%m.%Y}.'
    else: return 'suppressed_dobro_source'
    text = f'{heading}\nК переносу: {positive} ч у {len({row.user_id for row in rows})} человек.'
    if corrections: text += f' Исправления: уменьшить ранее внесённое на {corrections} ч.'
    text += f'\nПеренос выполняется вручную в CRM Добро.рф. Список и журнал: /fund/integrations/dobro/transfers?period={period}'
    return {'recipient_id':str(owner_id), 'subject':'Перенести часы в Добро.рф', 'text':text, 'topic':'messages'}

register_notice_source('dobro_reminder', resolve_reminder, lock_subjects=lock_subjects)
