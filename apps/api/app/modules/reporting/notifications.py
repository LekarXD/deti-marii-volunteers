"""Delivery rebuilds operational reports from the current authorized source."""
from uuid import UUID
from sqlalchemy import select
from app.core.auth import load_background_staff_authorization,assert_background_authorizations_locked
from app.core.errors import ApiError
from app.modules.messaging.registry import register_notice_source
from .models import ReportDigestSchedule,ReportDigestDelivery,ReportDigestRecipient
from .scopes import allowed
from .metrics import metrics

async def source_rows(db,outbox,source):
    try:delivery_id=UUID(source['delivery_id']);schedule_id=UUID(source['schedule_id']);recipient_id=UUID(source['recipient_id'])
    except (ValueError,KeyError,TypeError):return None
    pair=(await db.execute(select(ReportDigestDelivery,ReportDigestSchedule).join(ReportDigestSchedule,ReportDigestSchedule.id==ReportDigestDelivery.schedule_id).where(ReportDigestDelivery.id==delivery_id,ReportDigestDelivery.foundation_id==outbox.foundation_id,ReportDigestDelivery.outbox_id==outbox.id,ReportDigestDelivery.schedule_id==schedule_id,ReportDigestDelivery.recipient_id==recipient_id,ReportDigestSchedule.foundation_id==outbox.foundation_id))).one_or_none()
    return pair

async def lock_subjects(db,outbox,source):
    pair=await source_rows(db,outbox,source)
    return [pair[1].owner_user_id,pair[0].recipient_id] if pair else []

async def resolve_digest(db,outbox,source):
    pair=await source_rows(db,outbox,source)
    if pair is None:return 'suppressed_report_invalid'
    delivery,schedule=pair
    if not schedule.enabled or source.get('schedule_version')!=schedule.version or delivery.schedule_version!=schedule.version:return 'suppressed_report_stale'
    if source.get('period_from')!=delivery.period_from.isoformat() or source.get('period_to')!=delivery.period_to.isoformat():return 'suppressed_report_invalid'
    selected=await db.scalar(select(ReportDigestRecipient.user_id).where(ReportDigestRecipient.schedule_id==schedule.id,ReportDigestRecipient.user_id==delivery.recipient_id))
    if not selected:return 'suppressed_report_removed'
    try:assert_background_authorizations_locked(db,outbox.foundation_id,[schedule.owner_user_id,delivery.recipient_id])
    except ApiError:return 'suppressed_report_authz'
    owner=await load_background_staff_authorization(db,outbox.foundation_id,schedule.owner_user_id);recipient=await load_background_staff_authorization(db,outbox.foundation_id,delivery.recipient_id)
    if not allowed(owner,'reports.write',schedule.scope_type,schedule.scope_id) or not allowed(owner,'reports.read',schedule.scope_type,schedule.scope_id) or not allowed(recipient,'reports.read',schedule.scope_type,schedule.scope_id):return 'suppressed_report_revoked'
    try:data=await metrics(db,recipient,outbox.foundation_id,delivery.period_from,delivery.period_to,schedule.scope_type,schedule.scope_id)
    except ApiError:return 'suppressed_report_unavailable'
    values={item.key:item for item in data.metrics}
    text=f'Сводка за {delivery.period_from:%d.%m.%Y} — {delivery.period_to:%d.%m.%Y}. Область: {data.scope.label}.\nПодтверждённая помощь: {int(values["volunteer_minutes"].value)} минут. Занятий с подтверждённой помощью: {int(values["held_occurrences"].value)}. Волонтёров: {int(values["active_volunteers"].value)}.\nПодробности и определения: /fund/reports'
    return dict(recipient_id=str(delivery.recipient_id),subject='Сводка Опоры',text=text,topic='messages')
register_notice_source('report_digest',resolve_digest,lock_subjects=lock_subjects)
