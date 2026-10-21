from datetime import datetime,timedelta
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.auth import load_background_staff_authorization,lock_background_authorizations
from app.worker.registry import register_handler
from app.worker.queue import enqueue_job
from app.modules.messaging.consumers import enqueue_notice
from .models import ReportDigestSchedule,ReportDigestRecipient,ReportDigestDelivery
from .scopes import allowed
from .digests import next_run

async def run_digest(db,context):
    schedule_id=UUID(context.payload['schedule_id']);version=context.payload['version'];scheduled_for=datetime.fromisoformat(context.payload['scheduled_for'])
    initial=await db.scalar(select(ReportDigestSchedule).where(ReportDigestSchedule.id==schedule_id,ReportDigestSchedule.foundation_id==context.foundation_id))
    if initial is None:return {'state':'source_missing'}
    await lock_background_authorizations(db,context.foundation_id,[initial.owner_user_id])
    row=await db.scalar(select(ReportDigestSchedule).where(ReportDigestSchedule.id==schedule_id).with_for_update().execution_options(populate_existing=True))
    if not row.enabled or row.version!=version or row.next_run_at!=scheduled_for:return {'state':'superseded'}
    if scheduled_for>utcnow():return {'state':'not_due'}
    owner=await load_background_staff_authorization(db,row.foundation_id,row.owner_user_id)
    capable=allowed(owner,'reports.read',row.scope_type,row.scope_id) and allowed(owner,'reports.write',row.scope_type,row.scope_id)
    # Dates of service remain Moscow calendar dates; timezone only controls dispatch.
    period_to=scheduled_for.astimezone(ZoneInfo('Europe/Moscow')).date()-timedelta(days=1);period_from=period_to-timedelta(days=6)
    recipients=(await db.scalars(select(ReportDigestRecipient.user_id).where(ReportDigestRecipient.schedule_id==row.id).order_by(ReportDigestRecipient.user_id))).all();queued=0;suppressed=0
    await context.fence(db)
    for user_id in recipients:
        prior=await db.scalar(select(ReportDigestDelivery.id).where(ReportDigestDelivery.schedule_id==row.id,ReportDigestDelivery.period_to==period_to,ReportDigestDelivery.recipient_id==user_id))
        if prior:continue
        recipient=await load_background_staff_authorization(db,row.foundation_id,user_id)
        permitted=capable and allowed(recipient,'reports.read',row.scope_type,row.scope_id)
        delivery=ReportDigestDelivery(foundation_id=row.foundation_id,schedule_id=row.id,schedule_version=row.version,recipient_id=user_id,period_from=period_from,period_to=period_to,state='queued' if permitted else 'suppressed',reason='' if permitted else 'report_access_revoked');db.add(delivery);await db.flush()
        if permitted:
            source=dict(kind='report_digest',schedule_id=str(row.id),schedule_version=row.version,delivery_id=str(delivery.id),recipient_id=str(user_id),period_from=period_from.isoformat(),period_to=period_to.isoformat())
            outbox=enqueue_notice(db,row.foundation_id,user_id,'Сводка Опоры','',topic='messages',source=source);delivery.outbox_id=outbox.id;queued+=1
        else:suppressed+=1
    row.last_run_at=utcnow();row.state='scheduled' if capable else 'blocked';row.next_run_at=next_run(row.weekday,row.minute_of_day,row.timezone,max(utcnow(),scheduled_for));row.updated_at=utcnow()
    enqueue_job(db,row.foundation_id,'reporting.digest',dict(schedule_id=str(row.id),version=row.version,scheduled_for=row.next_run_at.isoformat()),available_at=row.next_run_at)
    await db.flush();return dict(state=row.state,queued=queued,suppressed=suppressed)
register_handler('reporting.digest',run_digest,timeout_seconds=90)
