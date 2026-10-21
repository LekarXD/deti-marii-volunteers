"""Append-only minute deltas backed by immutable attendance or coordinator reviews."""
from datetime import date,timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import select,func,text
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.models import User
from app.modules.activities.assignment_models import Assignment,AttendanceEvent,Attendance
from app.modules.activities.calendar_models import EventOccurrence
from app.modules.applications.service import check_version
from .models import ServiceTimeEntry,ManualTimeRequest,ManualTimeReview,Gratitude
from .schemas import ServiceTimeEntryView,ManualTimeView,ManualTimeReviewView,HoursView,AchievementView,GratitudeView

async def subject_lock(db,foundation_id,user_id):
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'ledger:{foundation_id}:{user_id}'})

async def append_service_time(db,principal,user_id,assignment_id,attendance_event_id,delta_minutes=None,reason=None):
    """Trusted internal adapter. Caller commits attendance and projection together."""
    await subject_lock(db,principal.foundation_id,user_id)
    event=await db.scalar(select(AttendanceEvent).where(AttendanceEvent.id==attendance_event_id,AttendanceEvent.foundation_id==principal.foundation_id,AttendanceEvent.user_id==user_id,AttendanceEvent.assignment_id==assignment_id).with_for_update())
    if event is None:raise ApiError(404,'attendance_event_not_found','Факт посещения не найден')
    delta=event.new_minutes-event.old_minutes
    if delta_minutes is not None and delta_minutes!=delta:raise ApiError(422,'attendance_delta_mismatch','Минуты не соответствуют факту посещения')
    prior=await db.scalar(select(ServiceTimeEntry).where(ServiceTimeEntry.attendance_event_id==event.id))
    if prior:
        if prior.delta_minutes!=delta:raise ApiError(409,'ledger_source_conflict','Источник часов изменился')
        event.ledger_state='posted';return prior
    earlier=await db.scalar(select(AttendanceEvent.id).where(AttendanceEvent.attendance_id==event.attendance_id,AttendanceEvent.version<event.version,AttendanceEvent.ledger_state!='posted').limit(1))
    if earlier:raise ApiError(409,'ledger_prior_event_pending','Предыдущий факт посещения ещё не учтён',retryable=True)
    pair=(await db.execute(select(Assignment,EventOccurrence).join(EventOccurrence,Assignment.occurrence_id==EventOccurrence.id).where(Assignment.id==assignment_id,Assignment.user_id==user_id,Assignment.foundation_id==principal.foundation_id,EventOccurrence.foundation_id==principal.foundation_id))).one_or_none()
    if not pair:raise ApiError(404,'assignment_not_found','Назначение не найдено')
    assignment,occurrence=pair
    entry=ServiceTimeEntry(foundation_id=principal.foundation_id,user_id=user_id,service_date=occurrence.starts_at.astimezone(ZoneInfo('Europe/Moscow')).date(),title=occurrence.title,delta_minutes=delta,source_kind='attendance',source_id=event.attendance_id,source_revision=event.version,attendance_event_id=event.id,assignment_id=assignment.id,reason=event.reason,actor_id=event.actor_id)
    db.add(entry);event.ledger_state='posted';await db.flush();return entry

async def post_pending_attendance(db,principal,user_id):
    await subject_lock(db,principal.foundation_id,user_id)
    events=(await db.scalars(select(AttendanceEvent).where(AttendanceEvent.foundation_id==principal.foundation_id,AttendanceEvent.user_id==user_id,AttendanceEvent.ledger_state=='pending').order_by(AttendanceEvent.attendance_id,AttendanceEvent.version))).all()
    for event in events:await append_service_time(db,principal,user_id,event.assignment_id,event.id)
    return len(events)

def entry_view(row):
    return ServiceTimeEntryView(id=row.id,service_date=row.service_date,title=row.title,delta_minutes=row.delta_minutes,source_kind=row.source_kind,source_id=row.source_id,source_revision=row.source_revision,assignment_id=row.assignment_id,reason=row.reason,created_at=row.created_at)
async def manual_view(db,row):
    user=await db.get(User,row.user_id)
    reviews=(await db.scalars(select(ManualTimeReview).where(ManualTimeReview.request_id==row.id).order_by(ManualTimeReview.version))).all()
    return ManualTimeView(id=row.id,user_id=row.user_id,display_name=user.display_name,title=row.title,service_date=row.service_date,requested_minutes=row.requested_minutes,approved_minutes=row.approved_minutes,state=row.state,version=row.version,created_at=row.created_at,reviews=[ManualTimeReviewView(id=r.id,version=r.version,decision=r.decision,approved_minutes=r.approved_minutes,reason=r.reason,actor_id=r.actor_id,created_at=r.created_at) for r in reviews])

async def request_manual_time(db,principal,command):
    from .service import own_user
    user=await own_user(db,principal)
    if command.service_date>utcnow().date():raise ApiError(422,'future_service_date','Подтверждать можно уже выполненную помощь')
    row=ManualTimeRequest(foundation_id=principal.foundation_id,user_id=user.id,title=command.title.strip(),service_date=command.service_date,requested_minutes=command.requested_minutes,state='pending',version=1,approved_minutes=0)
    if not row.title:raise ApiError(422,'empty_title','Укажите, чем помогали')
    db.add(row);await db.flush();return await manual_view(db,row)

async def review_manual_time(db,principal,request_id,command):
    # Lookup identity without locking; then one global per-subject ledger order.
    row=await db.scalar(select(ManualTimeRequest).where(ManualTimeRequest.id==request_id,ManualTimeRequest.foundation_id==principal.foundation_id))
    if row is None:raise ApiError(404,'manual_time_not_found','Запрос не найден')
    if row.user_id==principal.user_id:raise ApiError(403,'self_time_review_forbidden','Свои часы подтверждает другой координатор')
    await subject_lock(db,principal.foundation_id,row.user_id)
    row=await db.scalar(select(ManualTimeRequest).where(ManualTimeRequest.id==request_id).with_for_update().execution_options(populate_existing=True))
    check_version(row.version,command.expected_version)
    if row.state=='cancelled':raise ApiError(409,'manual_time_cancelled','Запрос отменён')
    old=row.approved_minutes;row.approved_minutes=command.approved_minutes;row.state=command.decision;row.version+=1
    review=ManualTimeReview(request_id=row.id,version=row.version,decision=command.decision,approved_minutes=command.approved_minutes,reason=command.reason.strip(),actor_id=principal.actor_id)
    db.add(review);await db.flush()
    db.add(ServiceTimeEntry(foundation_id=row.foundation_id,user_id=row.user_id,service_date=row.service_date,title=row.title,delta_minutes=command.approved_minutes-old,source_kind='manual_review',source_id=row.id,source_revision=row.version,manual_request_id=row.id,reason=review.reason,actor_id=principal.actor_id))
    await db.flush();return await manual_view(db,row)

async def cancel_manual_time(db,principal,request_id,command):
    row=await db.scalar(select(ManualTimeRequest).where(ManualTimeRequest.id==request_id,ManualTimeRequest.foundation_id==principal.foundation_id,ManualTimeRequest.user_id==principal.user_id).with_for_update())
    if row is None:raise ApiError(404,'manual_time_not_found','Запрос не найден')
    check_version(row.version,command.expected_version)
    if row.state!='pending':raise ApiError(409,'manual_time_decided','Координатор уже принял решение')
    row.state='cancelled';row.version+=1;await db.flush();return await manual_view(db,row)

async def hours_view(db,principal):
    from .service import own_user
    user=await own_user(db,principal)
    entries=(await db.scalars(select(ServiceTimeEntry).where(ServiceTimeEntry.foundation_id==principal.foundation_id,ServiceTimeEntry.user_id==user.id).order_by(ServiceTimeEntry.service_date.desc(),ServiceTimeEntry.created_at.desc()))).all()
    manuals=(await db.scalars(select(ManualTimeRequest).where(ManualTimeRequest.foundation_id==principal.foundation_id,ManualTimeRequest.user_id==user.id).order_by(ManualTimeRequest.created_at.desc()))).all()
    assignments={}
    for entry in entries:
        if entry.assignment_id:assignments[entry.assignment_id]=assignments.get(entry.assignment_id,0)+entry.delta_minutes
    count=sum(value>0 for value in assignments.values())
    pending=await db.scalar(select(func.count()).select_from(AttendanceEvent).where(AttendanceEvent.foundation_id==principal.foundation_id,AttendanceEvent.user_id==user.id,AttendanceEvent.ledger_state=='pending'))
    positive=[entry for entry in entries if entry.assignment_id and assignments.get(entry.assignment_id,0)>0]
    first=min((entry.service_date for entry in positive),default=None);months=0 if not first else max(0,(utcnow().year-first.year)*12+utcnow().month-first.month-(utcnow().day<first.day))
    planned=(await db.execute(select(Assignment.id,EventOccurrence.starts_at,Attendance.outcome).join(EventOccurrence,Assignment.occurrence_id==EventOccurrence.id).outerjoin(Attendance,Attendance.assignment_id==Assignment.id).where(Assignment.foundation_id==principal.foundation_id,Assignment.user_id==user.id,Assignment.status=='confirmed',EventOccurrence.status!='cancelled',EventOccurrence.ends_at<utcnow()).order_by(EventOccurrence.starts_at))).all()
    dates=[(id,start.astimezone(ZoneInfo('Europe/Moscow')).date(),outcome) for id,start,outcome in planned]
    month_earned=False;month_progress=0
    for _,start,_ in dates:
        end=start+timedelta(days=27)
        if end>=utcnow().date():continue
        window=[(id,day,outcome) for id,day,outcome in dates if start<=day<=end]
        passed=sum(outcome=='attended' and assignments.get(id,0)>0 for id,day,outcome in window)
        weeks=len({day.isocalendar()[:2] for id,day,outcome in window if outcome=='attended' and assignments.get(id,0)>0})
        month_progress=max(month_progress,min(passed,4))
        if passed==len(window) and passed>=4 and weeks>=4:month_earned=True
    achievements=[AchievementView(key='first',title='Первое занятие',earned=count>=1,progress=min(count,1),target=1,rule='Хотя бы одно посещение с подтверждёнными минутами'),AchievementView(key='month',title='Месяц без пропусков',earned=month_earned,progress=4 if month_earned else month_progress,target=4,rule='За завершившиеся 28 дней: минимум четыре подтверждённых занятия в четырёх разных неделях; каждое согласованное занятие в этом периоде посещено'),AchievementView(key='ten',title='10 занятий',earned=count>=10,progress=min(count,10),target=10,rule='Десять разных назначений с подтверждёнными минутами'),AchievementView(key='six_months',title='Полгода с нами',earned=months>=6,progress=min(months,6),target=6,rule='Шесть месяцев с первого подтверждённого занятия'),AchievementView(key='year',title='Год с фондом',earned=months>=12,progress=min(months,12),target=12,rule='Двенадцать месяцев с первого подтверждённого занятия')]
    gratitudes=(await db.scalars(select(Gratitude).where(Gratitude.foundation_id==principal.foundation_id,Gratitude.user_id==user.id).order_by(Gratitude.created_at.desc()))).all();thanks=[]
    for gratitude in gratitudes:
        basis=next((entry for entry in entries if entry.id==gratitude.basis_entry_id),None)
        basis_current=bool(basis and sum(entry.delta_minutes for entry in entries if entry.source_kind==basis.source_kind and entry.source_id==basis.source_id)>0)
        author=await db.get(User,gratitude.author_id);thanks.append(GratitudeView(id=gratitude.id,text=gratitude.text,author=author.display_name,created_at=gratitude.created_at,basis_current=basis_current))
    return HoursView(total_minutes=sum(entry.delta_minutes for entry in entries),confirmed_assignments=count,pending_minutes=sum(row.requested_minutes for row in manuals if row.state=='pending'),ledger_pending=pending,entries=[entry_view(row) for row in entries],manual_requests=[await manual_view(db,row) for row in manuals],achievements=achievements,gratitudes=thanks)

async def add_gratitude(db,principal,command):
    if command.user_id==principal.user_id:raise ApiError(403,'self_gratitude_forbidden','Благодарность пишет другой сотрудник')
    entry=await db.scalar(select(ServiceTimeEntry).where(ServiceTimeEntry.id==command.basis_entry_id,ServiceTimeEntry.foundation_id==principal.foundation_id,ServiceTimeEntry.user_id==command.user_id))
    if entry is None:raise ApiError(404,'service_time_not_found','Подтверждённая помощь не найдена')
    await subject_lock(db,principal.foundation_id,command.user_id)
    net=await db.scalar(select(func.sum(ServiceTimeEntry.delta_minutes)).where(ServiceTimeEntry.foundation_id==principal.foundation_id,ServiceTimeEntry.source_kind==entry.source_kind,ServiceTimeEntry.source_id==entry.source_id))
    if not net or net<=0:raise ApiError(409,'gratitude_basis_invalid','Нет подтверждённых часов для благодарности')
    row=Gratitude(foundation_id=principal.foundation_id,user_id=command.user_id,basis_entry_id=entry.id,text=command.text.strip(),author_id=principal.user_id)
    db.add(row);await db.flush();return GratitudeView(id=row.id,text=row.text,author=(await db.get(User,principal.user_id)).display_name,created_at=row.created_at,basis_current=True)

async def recognition_bases(db,principal):
    from .schemas import RecognitionBasisView
    groups=(await db.execute(select(ServiceTimeEntry.user_id,ServiceTimeEntry.source_kind,ServiceTimeEntry.source_id,func.sum(ServiceTimeEntry.delta_minutes)).where(ServiceTimeEntry.foundation_id==principal.foundation_id,ServiceTimeEntry.user_id!=principal.user_id).group_by(ServiceTimeEntry.user_id,ServiceTimeEntry.source_kind,ServiceTimeEntry.source_id).having(func.sum(ServiceTimeEntry.delta_minutes)>0).order_by(func.max(ServiceTimeEntry.created_at).desc()).limit(200))).all()
    values=[]
    for user_id,kind,source_id,total in groups:
        row=await db.scalar(select(ServiceTimeEntry).where(ServiceTimeEntry.foundation_id==principal.foundation_id,ServiceTimeEntry.user_id==user_id,ServiceTimeEntry.source_kind==kind,ServiceTimeEntry.source_id==source_id,ServiceTimeEntry.delta_minutes>0).order_by(ServiceTimeEntry.created_at).limit(1))
        user=await db.get(User,user_id)
        values.append(RecognitionBasisView(entry_id=row.id,user_id=user.id,display_name=user.display_name,title=row.title,service_date=row.service_date,confirmed_minutes=total))
    return values
