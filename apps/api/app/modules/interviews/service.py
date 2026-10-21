from datetime import date, datetime, timedelta, timezone
from math import lcm
from uuid import UUID
from sqlalchemy import and_, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from app.core.errors import ApiError
from app.core.audit import audit
from app.worker.queue import enqueue_outbox
from app.modules.applications.models import Application
from .models import AvailabilitySeries, AvailabilityException, InterviewSlot, InterviewBooking, BookingEvent, InterviewResult, InterviewPrivateNote
from .recurrence import expand, local_instant, matches
from .schemas import WindowView

UTC = timezone.utc

def fail(code, message, status=409, version=None):
    raise ApiError(status, code, message, current_version=version)

def check_version(row, expected):
    if row.version != expected: fail("version_conflict", "Запись изменилась. Обновите данные и повторите действие.", version=row.version)

async def coordinator_lock(db, coordinator_id):
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": "interview-coordinator:" + str(coordinator_id)})

def owner_clause(principal):
    return InterviewBooking.user_id == principal.user_id if principal.user_id else InterviewBooking.registration_id == principal.registration_id

async def application(db, p, application_id=None):
    q = select(Application).where(Application.foundation_id == p.foundation_id)
    if p.is_staff and application_id:
        q = q.where(Application.id == application_id)
    else:
        q = q.where(Application.user_id == p.user_id if p.user_id else Application.registration_id == p.registration_id)
        if application_id: q = q.where(Application.id == application_id)
    row = await db.scalar(q.with_for_update())
    if not row: fail("application_required", "Сначала отправьте анкету волонтёра.", 404)
    if row.submission_state != "submitted": fail("application_not_submitted", "Для записи нужна отправленная анкета.")
    return row

async def get_booking(db, p, booking_id, staff=False, lock=False):
    q = select(InterviewBooking).where(InterviewBooking.id == booking_id, InterviewBooking.foundation_id == p.foundation_id)
    if not staff: q = q.where(owner_clause(p))
    row = await db.scalar(q.with_for_update() if lock else q)
    if not row: fail("interview_not_found", "Встреча не найдена.", 404)
    return row

async def window(db, p, id, lock=False):
    q = select(AvailabilitySeries).where(AvailabilitySeries.id == id, AvailabilitySeries.foundation_id == p.foundation_id, AvailabilitySeries.coordinator_id == p.user_id)
    row = await db.scalar(q.with_for_update() if lock else q)
    if not row: fail("availability_not_found", "Окно доступности не найдено.", 404)
    return row

async def window_view(db, row):
    excs = (await db.scalars(select(AvailabilityException).where(AvailabilityException.series_id == row.id).order_by(AvailabilityException.origin_date))).all()
    result = WindowView.model_validate(row).model_dump(mode="json")
    result["exceptions"] = [{"origin_date": str(e.origin_date), "kind": e.kind, "start_minute": e.start_minute, "end_minute": e.end_minute} for e in excs]
    return result

async def validate_windows(db, row):
    if not row.active: return
    others = (await db.scalars(select(AvailabilitySeries).where(AvailabilitySeries.coordinator_id == row.coordinator_id, AvailabilitySeries.active.is_(True), AvailabilitySeries.id != row.id))).all()
    excs = (await db.scalars(select(AvailabilityException).where(AvailabilityException.series_id.in_([row.id] + [s.id for s in others])))).all()
    def intervals(s, start, end):
        emap = {e.origin_date: e for e in excs if e.series_id == s.id}
        day = start
        while day <= end:
            if matches(s, day):
                e = emap.get(day)
                if not e or e.kind != "skip":
                    a = local_instant(day, e.start_minute if e and e.kind == "override" else s.start_minute, s.timezone)
                    b = local_instant(day, e.end_minute if e and e.kind == "override" else s.end_minute, s.timezone)
                    if a is not None and b is not None: yield a,b
            day += timedelta(days=1)
    for other in others:
        start = max(row.local_start_date, other.local_start_date) - timedelta(days=1)
        end = start + timedelta(weeks=lcm(row.interval_weeks, other.interval_weeks) + 2)
        limits = [s.last_date for s in (row,other) if s.last_date]
        if row.recurrence == "once": limits.append(row.local_start_date)
        if other.recurrence == "once": limits.append(other.local_start_date)
        if limits: end = min(end, min(limits) + timedelta(days=1))
        # Ordered sweep also catches cross-midnight UTC windows in different zones.
        left, right = list(intervals(row,start,end)), list(intervals(other,start,end))
        i=j=0
        while i<len(left) and j<len(right):
            a,b=left[i]; c,d=right[j]
            if a<d and c<b: fail("availability_overlap", "Это время пересекается с другим окном доступности.")
            if b<=d: i+=1
            else: j+=1

async def assert_bookings_preserved(db, row):
    bookings = (await db.scalars(select(InterviewBooking).join(InterviewSlot, InterviewBooking.slot_id == InterviewSlot.id).where(InterviewSlot.series_id == row.id, InterviewBooking.status == "booked"))).all()
    if not bookings: return
    excs = (await db.scalars(select(AvailabilityException).where(AvailabilityException.series_id == row.id))).all()
    affected=[]
    for b in bookings:
        slot=await db.get(InterviewSlot,b.slot_id)
        choices=list(expand(row,slot.origin_date,slot.origin_date,excs))
        same=any(a==b.starts_at and end==b.ends_at and busy==b.busy_until and row.venue==b.venue and row.join_url==b.join_url for _,_,a,end,busy in choices)
        if not same: affected.append(str(b.id))
    if affected:
        raise ApiError(409,"affected_bookings","Сначала перенесите назначенные встречи.",field_errors={"booking_ids":affected})

async def materialize(db, p, start, end, view_timezone="Europe/Moscow"):
    if end<start or (end-start).days>92: fail("range_too_large","Выберите период до 93 дней; можно перейти к любой дате.",422)
    series=(await db.scalars(select(AvailabilitySeries).where(AvailabilitySeries.foundation_id==p.foundation_id,AvailabilitySeries.active.is_(True)).order_by(AvailabilitySeries.coordinator_id,AvailabilitySeries.id))).all()
    for row in series:
        await coordinator_lock(db,row.coordinator_id)
        # Refresh after waiting for an availability edit/pause.
        await db.refresh(row)
        if not row.active: continue
        excs=(await db.scalars(select(AvailabilityException).where(AvailabilityException.series_id==row.id))).all()
        for day,minute,a,b,busy in expand(row,start-timedelta(days=2),end+timedelta(days=2),excs):
            await db.execute(insert(InterviewSlot).values(foundation_id=p.foundation_id,series_id=row.id,coordinator_id=row.coordinator_id,origin_date=day,origin_minute=minute,starts_at=a,ends_at=b,busy_until=busy,available=True,version=row.version).on_conflict_do_update(index_elements=[InterviewSlot.series_id,InterviewSlot.origin_date,InterviewSlot.origin_minute],set_={"starts_at":a,"ends_at":b,"busy_until":busy,"available":True,"version":row.version}))
    first_instant=local_instant(start,0,view_timezone)
    last_instant=local_instant(end+timedelta(days=1),0,view_timezone)
    if first_instant is None or last_instant is None: fail("invalid_local_boundary","Выберите другой диапазон дат.",422)
    q=select(InterviewSlot,AvailabilitySeries).join(AvailabilitySeries,InterviewSlot.series_id==AvailabilitySeries.id).where(InterviewSlot.foundation_id==p.foundation_id,AvailabilitySeries.active.is_(True),InterviewSlot.available.is_(True),InterviewSlot.starts_at>=first_instant,InterviewSlot.starts_at<last_instant,InterviewSlot.starts_at>datetime.now(UTC)).order_by(InterviewSlot.starts_at)
    result=[]
    for slot,row in (await db.execute(q)).all():
        busy=await db.scalar(select(InterviewBooking.id).where(InterviewBooking.status=="booked",InterviewBooking.coordinator_id==slot.coordinator_id,InterviewBooking.starts_at<slot.busy_until,InterviewBooking.busy_until>slot.starts_at).limit(1))
        if not busy: result.append({"id":str(slot.id),"series_id":str(row.id),"coordinator_id":str(row.coordinator_id),"starts_at":slot.starts_at.isoformat(),"ends_at":slot.ends_at.isoformat(),"timezone":row.timezone,"venue":row.venue,"join_url":row.join_url,"version":slot.version})
    return result

async def available_slot(db,p,id,version):
    base=await db.get(InterviewSlot,id)
    if not base or base.foundation_id!=p.foundation_id: fail("slot_unavailable","Это время уже занято или закрыто.")
    await coordinator_lock(db,base.coordinator_id)
    await db.refresh(base)
    row=await db.get(AvailabilitySeries,base.series_id)
    await db.refresh(row)
    if not row.active or not base.available or base.version!=version or row.version!=version: fail("slot_unavailable","Выбранное время изменилось. Выберите его заново.")
    if base.starts_at<=datetime.now(UTC): fail("slot_in_past","Выберите будущее время.")
    excs=(await db.scalars(select(AvailabilityException).where(AvailabilityException.series_id==row.id))).all()
    if not any(a==base.starts_at and b==base.ends_at and busy==base.busy_until for _,_,a,b,busy in expand(row,base.origin_date,base.origin_date,excs)): fail("slot_unavailable","Это время больше недоступно.")
    return base,row

async def booking_view(db,row,staff=False):
    result=await db.scalar(select(InterviewResult).where(InterviewResult.booking_id==row.id))
    events=(await db.scalars(select(BookingEvent).where(BookingEvent.booking_id==row.id).order_by(BookingEvent.created_at))).all()
    out={k:getattr(row,k) for k in ("id","application_id","slot_id","coordinator_id","starts_at","ends_at","venue","join_url","status","version","cancel_reason")}
    out["result"]={"outcome":result.outcome,"public_agreement":result.public_agreement,"next_contact_date":result.next_contact_date} if result else None
    out["events"]=[{"kind":e.kind,"created_at":e.created_at,"before":e.before,"after":e.after} for e in events]
    if staff:
        note=await db.scalar(select(InterviewPrivateNote).where(InterviewPrivateNote.booking_id==row.id))
        out["private_note"]=note.text if note else None
    return out

def snapshot(row):
    return {"starts_at":row.starts_at.isoformat(),"ends_at":row.ends_at.isoformat(),"status":row.status,"version":row.version,"slot_id":str(row.slot_id)}

def record(db,p,row,kind,before=None):
    db.add(BookingEvent(booking_id=row.id,kind=kind,actor_id=p.actor_id,before=before,after=snapshot(row)))
    audit(db,p,"interviews."+kind,"interview",row.id,fields=("status","starts_at","version"))
    # Version fence lets the delivery consumer drop reminders for old arrangements.
    enqueue_outbox(db,p.foundation_id,"internal",{"event":"interview."+kind,"booking_id":str(row.id),"booking_version":row.version,"user_id":str(row.user_id) if row.user_id else None,"registration_id":str(row.registration_id) if row.registration_id else None})

async def reserve(db,row,active=True):
    """One global busy ledger shared with confirmed activities (P09)."""
    from app.core.models import ResourceReservation
    for kind,user_id,registration_id in (("interview_candidate",row.user_id,row.registration_id),("interview_coordinator",row.coordinator_id,None)):
        reservation=await db.scalar(select(ResourceReservation).where(ResourceReservation.source_type==kind,ResourceReservation.source_id==row.id))
        if not reservation:
            reservation=ResourceReservation(foundation_id=row.foundation_id,user_id=user_id,registration_id=registration_id,owner_key="user:"+str(user_id) if user_id else "registration:"+str(registration_id),source_type=kind,source_id=row.id,starts_at=row.starts_at,busy_until=row.busy_until,active=active)
            db.add(reservation)
        else:
            reservation.starts_at=row.starts_at;reservation.busy_until=row.busy_until;reservation.active=active
    await db.flush()

async def claim_registration(db, registration_id, user_id):
    """Adopt facts atomically with verification; constraints reject a busy target."""
    from app.core.models import ResourceReservation
    rows=(await db.scalars(select(InterviewBooking).where(InterviewBooking.registration_id==registration_id).with_for_update())).all()
    for row in rows:
        row.registration_id=None;row.user_id=user_id;row.candidate_key="user:"+str(user_id)
    reservations=(await db.scalars(select(ResourceReservation).where(ResourceReservation.registration_id==registration_id,ResourceReservation.source_type=="interview_candidate").with_for_update())).all()
    for reservation in reservations:
        reservation.registration_id=None;reservation.user_id=user_id;reservation.owner_key="user:"+str(user_id)
    await db.flush()
