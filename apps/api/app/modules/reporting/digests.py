from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from uuid import UUID
from sqlalchemy import select,delete,text
from app.core.clock import utcnow
from app.core.auth import load_background_staff_authorization
from app.core.errors import ApiError
from app.core.models import User,StaffMembership,OutboxMessage
from app.worker.queue import enqueue_job
from app.modules.applications.service import check_version
from .models import ReportDigestSchedule,ReportDigestRecipient,ReportDigestDelivery
from .schemas import ReportDigestView,ReportDigestRecipientView,ReportDigestDeliveryView
from .scopes import authorize_scope,allowed

def next_run(weekday,minute_of_day,timezone_name,after):
    try:zone=ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError,ValueError):raise ApiError(422,'invalid_timezone','Укажите существующий часовой пояс')
    local=after.astimezone(zone);candidate=local.replace(hour=minute_of_day//60,minute=minute_of_day%60,second=0,microsecond=0)+timedelta(days=(weekday-local.weekday())%7)
    if candidate<=local:candidate+=timedelta(days=7)
    return candidate.astimezone(timezone.utc)

async def schedule_for(db,principal,scope_type,scope_id,lock=False):
    query=select(ReportDigestSchedule).where(ReportDigestSchedule.foundation_id==principal.foundation_id,ReportDigestSchedule.owner_user_id==principal.user_id,ReportDigestSchedule.scope_type==scope_type,ReportDigestSchedule.scope_id==scope_id)
    return await db.scalar(query.with_for_update() if lock else query)

async def digest_view(db,principal,scope_type,scope_id):
    scope=await authorize_scope(db,principal,principal.foundation_id,scope_type,scope_id)
    row=await schedule_for(db,principal,scope_type,scope_id)
    if row is None:return ReportDigestView(id=None,version=0,enabled=False,scope=scope,recipients=[],weekday=0,minute_of_day=540,timezone='Europe/Moscow',state='disabled',next_run_at=None,last_run_at=None,deliveries=[])
    users=(await db.scalars(select(User).join(ReportDigestRecipient,User.id==ReportDigestRecipient.user_id).where(ReportDigestRecipient.schedule_id==row.id,User.foundation_id==principal.foundation_id).order_by(User.display_name,User.id))).all()
    deliveries=(await db.execute(select(ReportDigestDelivery,OutboxMessage.state).outerjoin(OutboxMessage,OutboxMessage.id==ReportDigestDelivery.outbox_id).where(ReportDigestDelivery.schedule_id==row.id).order_by(ReportDigestDelivery.created_at.desc()).limit(50))).all()
    return ReportDigestView(id=row.id,version=row.version,enabled=row.enabled,scope=scope,recipients=[ReportDigestRecipientView(user_id=u.id,display_name=u.display_name) for u in users],weekday=row.weekday,minute_of_day=row.minute_of_day,timezone=row.timezone,state=row.state,next_run_at=row.next_run_at,last_run_at=row.last_run_at,deliveries=[ReportDigestDeliveryView(id=d.id,recipient_id=d.recipient_id,period_from=d.period_from,period_to=d.period_to,state=outbox_state or d.state,reason=d.reason,created_at=d.created_at) for d,outbox_state in deliveries])

async def recipient_options(db,principal,scope_type,scope_id):
    await authorize_scope(db,principal,principal.foundation_id,scope_type,scope_id,'reports.write')
    users=(await db.scalars(select(User).join(StaffMembership,StaffMembership.user_id==User.id).where(User.foundation_id==principal.foundation_id,User.account_state=='active',StaffMembership.foundation_id==principal.foundation_id,StaffMembership.revoked_at.is_(None)).order_by(User.display_name,User.id).limit(200))).all();options=[]
    for user in users:
        authority=await load_background_staff_authorization(db,principal.foundation_id,user.id)
        if allowed(authority,'reports.read',scope_type,scope_id):options.append(ReportDigestRecipientView(user_id=user.id,display_name=user.display_name))
    return options

async def save_schedule(db,principal,command):
    await authorize_scope(db,principal,principal.foundation_id,command.scope_type,command.scope_id,'reports.write')
    if not principal.user_id:raise ApiError(403,'verified_account_required','Войдите в подтверждённый аккаунт')
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'report-digest:{principal.foundation_id}:{principal.user_id}:{command.scope_type}:{command.scope_id}'})
    row=await schedule_for(db,principal,command.scope_type,command.scope_id,True);check_version(row.version if row else 0,command.expected_version)
    if len(set(command.recipient_ids))!=len(command.recipient_ids):raise ApiError(422,'duplicate_digest_recipient','Уберите повторяющихся получателей')
    due=next_run(command.weekday,command.minute_of_day,command.timezone,utcnow())
    if command.enabled:
        owner=await load_background_staff_authorization(db,principal.foundation_id,principal.user_id)
        if not allowed(owner,'reports.write',command.scope_type,command.scope_id) or not allowed(owner,'reports.read',command.scope_type,command.scope_id):raise ApiError(403,'digest_mfa_required','Подтвердите второй фактор для фоновой сводки')
        if not command.recipient_ids:raise ApiError(422,'digest_recipients_required','Выберите хотя бы одного получателя')
    for user_id in command.recipient_ids:
        authority=await load_background_staff_authorization(db,principal.foundation_id,user_id)
        if not allowed(authority,'reports.read',command.scope_type,command.scope_id):raise ApiError(422,'digest_recipient_scope_denied','Получатель не имеет текущего доступа к этой области отчёта')
    if row is None:
        row=ReportDigestSchedule(foundation_id=principal.foundation_id,owner_user_id=principal.user_id,scope_type=command.scope_type,scope_id=command.scope_id,version=1);db.add(row);await db.flush()
    else:row.version+=1
    row.enabled=command.enabled;row.weekday=command.weekday;row.minute_of_day=command.minute_of_day;row.timezone=command.timezone;row.next_run_at=due if command.enabled else None;row.state='scheduled' if command.enabled else 'disabled';row.updated_at=utcnow()
    await db.execute(delete(ReportDigestRecipient).where(ReportDigestRecipient.schedule_id==row.id))
    for user_id in command.recipient_ids:db.add(ReportDigestRecipient(schedule_id=row.id,user_id=user_id,foundation_id=principal.foundation_id))
    await db.flush()
    if row.enabled:enqueue_job(db,row.foundation_id,'reporting.digest',dict(schedule_id=str(row.id),version=row.version,scheduled_for=due.isoformat()),available_at=due)
    return await digest_view(db,principal,row.scope_type,row.scope_id)
