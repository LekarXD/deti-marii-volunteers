from datetime import date, datetime, timezone
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, Header, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal, get_principal, require_permission, authz_guard
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.idempotency import begin_command, finish_command
from app.core.audit import audit
from .models import AvailabilitySeries, AvailabilityException, InterviewSlot, InterviewBooking, InterviewResult, InterviewPrivateNote
from .schemas import WindowInput, WindowUpdate, WindowView, PauseCommand, ExceptionCommand, BookingInput, MoveInput, CancelInput, CompleteInput, BookingView, StaffBookingView, SlotView
from . import service as s

router=APIRouter(prefix="/api/v1",tags=["interviews"])
staff_dep=require_permission("interviews.manage")

async def command(db,p,operation,key,payload,action):
    try:
        await authz_guard(db,p)
        if operation.startswith("interviews.availability.") or operation.startswith("interviews.complete:") or operation.startswith("interviews.missed:"):
            if not p.has_permission("interviews.manage"): raise ApiError(403,"permission_denied","Недостаточно прав.")
        replay=await begin_command(db,p,operation,key,payload)
        if replay is not None:
            await db.commit()
            return replay
        result=jsonable_encoder(await action())
        await finish_command(db,p,operation,key,result)
        await db.commit()
        return result
    except IntegrityError as exc:
        await db.rollback()
        # PostgreSQL unique/exclusion constraints resolve simultaneous slot claims.
        if getattr(exc.orig,"sqlstate",None) in {"23505","23P01"}:
            raise ApiError(409,"interview_conflict","Это время уже занято. Выберите другое.") from None
        raise
    except BaseException:
        await db.rollback()
        raise

@router.get("/interview-slots",response_model=list[SlotView])
async def slots(from_:date=Query(alias="from"),to:date=Query(),timezone_:str=Query(default="Europe/Moscow",alias="timezone"),db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
    try: ZoneInfo(timezone_)
    except (ValueError,ZoneInfoNotFoundError): raise ApiError(422,"invalid_timezone","Неизвестный часовой пояс")
    # Query dates are interpreted in the viewer timezone; responses retain UTC instants.
    result=await s.materialize(db,p,from_,to,timezone_)
    await db.commit()
    return result

@router.get("/coord/interview-availability",response_model=list[WindowView])
async def windows(db:AsyncSession=Depends(get_db),p:Principal=Depends(staff_dep)):
    rows=(await db.scalars(select(AvailabilitySeries).where(AvailabilitySeries.foundation_id==p.foundation_id,AvailabilitySeries.coordinator_id==p.user_id).order_by(AvailabilitySeries.local_start_date))).all()
    return [await s.window_view(db,row) for row in rows]

@router.get("/coord/interview-availability/{id}",response_model=WindowView)
async def get_window(id:UUID,db:AsyncSession=Depends(get_db),p:Principal=Depends(staff_dep)):
    return await s.window_view(db,await s.window(db,p,id))

@router.post("/coord/interview-availability",response_model=WindowView,status_code=201)
async def create_window(body:WindowInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(staff_dep),key:str|None=Header(default=None,alias="Idempotency-Key")):
    async def action():
        await s.coordinator_lock(db,p.user_id)
        row=AvailabilitySeries(id=uuid4(),foundation_id=p.foundation_id,coordinator_id=p.user_id,version=1,**body.model_dump(mode="json"))
        # Date is a SQL date, not a JSON string.
        row.local_start_date=body.local_start_date; row.last_date=body.last_date
        db.add(row)
        await db.flush()
        await s.validate_windows(db,row)
        audit(db,p,"interviews.availability.create","interview_availability",row.id,fields=type(body).model_fields.keys())
        return await s.window_view(db,row)
    return await command(db,p,"interviews.availability.create",key,body.model_dump(mode="json"),action)

async def apply_window(db,p,id,body,preview=False):
    await s.coordinator_lock(db,p.user_id)
    row=await s.window(db,p,id,lock=True)
    s.check_version(row,body.expected_version)
    for k,v in body.model_dump(exclude={"expected_version"}).items(): setattr(row,k,str(v) if k=="join_url" and v else v)
    await s.assert_bookings_preserved(db,row)
    await s.validate_windows(db,row)
    if not preview:
        row.version+=1
        await db.execute(update(InterviewSlot).where(InterviewSlot.series_id==id).values(available=False))
        audit(db,p,"interviews.availability.update","interview_availability",id,fields=type(body).model_fields.keys())
        await db.flush()
    return await s.window_view(db,row)

@router.post("/coord/interview-availability/{id}/preview-change",response_model=WindowView)
async def preview_window(id:UUID,body:WindowUpdate,db:AsyncSession=Depends(get_db),p:Principal=Depends(staff_dep)):
    try: return await apply_window(db,p,id,body,preview=True)
    finally: await db.rollback()

@router.patch("/coord/interview-availability/{id}",response_model=WindowView)
async def edit_window(id:UUID,body:WindowUpdate,db:AsyncSession=Depends(get_db),p:Principal=Depends(staff_dep),key:str|None=Header(default=None,alias="Idempotency-Key")):
    return await command(db,p,"interviews.availability.update:"+str(id),key,body.model_dump(mode="json"),lambda:apply_window(db,p,id,body))

@router.post("/coord/interview-availability/{id}/pause",response_model=WindowView)
async def pause_window(id:UUID,body:PauseCommand,db:AsyncSession=Depends(get_db),p:Principal=Depends(staff_dep),key:str|None=Header(default=None,alias="Idempotency-Key")):
    async def action():
        await s.coordinator_lock(db,p.user_id)
        row=await s.window(db,p,id,lock=True); s.check_version(row,body.expected_version)
        row.active=body.active
        await s.validate_windows(db,row)
        row.version+=1
        audit(db,p,"interviews.availability.pause","interview_availability",id,fields=("active",))
        await db.flush()
        return await s.window_view(db,row)
    return await command(db,p,"interviews.availability.pause:"+str(id),key,body.model_dump(mode="json"),action)

@router.post("/coord/interview-availability/{id}/exceptions",response_model=WindowView)
async def exception(id:UUID,body:ExceptionCommand,db:AsyncSession=Depends(get_db),p:Principal=Depends(staff_dep),key:str|None=Header(default=None,alias="Idempotency-Key")):
    async def action():
        await s.coordinator_lock(db,p.user_id)
        row=await s.window(db,p,id,lock=True);s.check_version(row,body.expected_version)
        if not s.matches(row,body.origin_date): s.fail("exception_not_occurrence","В этот день серия не повторяется.",422)
        exc=await db.scalar(select(AvailabilityException).where(AvailabilityException.series_id==id,AvailabilityException.origin_date==body.origin_date))
        if body.kind=="restore":
            if exc: await db.delete(exc)
        else:
            if body.kind=="override" and body.end_minute-body.start_minute<row.duration_minutes: s.fail("invalid_interval","В интервал должна помещаться встреча.",422)
            if not exc:
                exc=AvailabilityException(series_id=id,origin_date=body.origin_date);db.add(exc)
            exc.kind=body.kind;exc.start_minute=body.start_minute;exc.end_minute=body.end_minute
        await db.flush()
        await s.assert_bookings_preserved(db,row);await s.validate_windows(db,row)
        row.version+=1
        await db.execute(update(InterviewSlot).where(InterviewSlot.series_id==id,InterviewSlot.origin_date==body.origin_date).values(available=False))
        audit(db,p,"interviews.availability.exception","interview_availability",id,fields=("exceptions",))
        return await s.window_view(db,row)
    return await command(db,p,"interviews.availability.exception:"+str(id),key,body.model_dump(mode="json"),action)

@router.get("/me/interviews",response_model=list[BookingView])
async def own_bookings(db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    rows=(await db.scalars(select(InterviewBooking).where(InterviewBooking.foundation_id==p.foundation_id,s.owner_clause(p)).order_by(InterviewBooking.starts_at.desc()))).all()
    return [await s.booking_view(db,row) for row in rows]

@router.get("/coord/interviews",response_model=list[StaffBookingView])
async def staff_bookings(db:AsyncSession=Depends(get_db),p:Principal=Depends(staff_dep)):
    rows=(await db.scalars(select(InterviewBooking).where(InterviewBooking.foundation_id==p.foundation_id).order_by(InterviewBooking.starts_at))).all()
    return [await s.booking_view(db,row,staff=True) for row in rows]

@router.post("/interviews",response_model=BookingView,status_code=201)
async def book(body:BookingInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias="Idempotency-Key")):
    async def action():
        if body.application_id and p.is_staff and not p.has_permission("interviews.manage"): s.fail("permission_denied","Недостаточно прав.",403)
        app=await s.application(db,p,body.application_id)
        slot,window=await s.available_slot(db,p,body.slot_id,body.slot_version)
        row=InterviewBooking(id=uuid4(),foundation_id=p.foundation_id,application_id=app.id,user_id=app.user_id,registration_id=app.registration_id,candidate_key=("user:"+str(app.user_id)) if app.user_id else ("registration:"+str(app.registration_id)),slot_id=slot.id,coordinator_id=slot.coordinator_id,starts_at=slot.starts_at,ends_at=slot.ends_at,busy_until=slot.busy_until,venue=window.venue,join_url=window.join_url,status="booked",version=1)
        db.add(row);await db.flush();await s.reserve(db,row);s.record(db,p,row,"booked");await db.flush()
        return await s.booking_view(db,row)
    return await command(db,p,"interviews.book",key,body.model_dump(mode="json"),action)

def can_manage(p): return p.is_staff and p.has_permission("interviews.manage")

@router.post("/interviews/{id}/reschedule",response_model=BookingView)
async def move(id:UUID,body:MoveInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias="Idempotency-Key")):
    async def action():
        row=await s.get_booking(db,p,id,staff=can_manage(p),lock=True);s.check_version(row,body.expected_version)
        if row.status!="booked": s.fail("interview_not_active","Встреча уже завершена или отменена.")
        # Lock application as well, making concurrent candidate commands serial.
        await db.scalar(select(Application).where(Application.id==row.application_id).with_for_update())
        slot,window=await s.available_slot(db,p,body.slot_id,body.slot_version)
        before=s.snapshot(row)
        row.slot_id=slot.id;row.coordinator_id=slot.coordinator_id;row.starts_at=slot.starts_at;row.ends_at=slot.ends_at;row.busy_until=slot.busy_until;row.venue=window.venue;row.join_url=window.join_url;row.version+=1
        await db.flush();await s.reserve(db,row);s.record(db,p,row,"rescheduled",before);await db.flush()
        return await s.booking_view(db,row)
    from app.modules.applications.models import Application
    return await command(db,p,"interviews.reschedule:"+str(id),key,body.model_dump(mode="json"),action)

@router.post("/interviews/{id}/cancel",response_model=BookingView)
async def cancel(id:UUID,body:CancelInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias="Idempotency-Key")):
    async def action():
        row=await s.get_booking(db,p,id,staff=can_manage(p),lock=True);s.check_version(row,body.expected_version)
        if row.status!="booked": s.fail("interview_not_active","Встреча уже завершена или отменена.")
        if not body.reason.strip(): s.fail("reason_required","Укажите причину отмены.",422)
        before=s.snapshot(row);row.status="cancelled";row.cancel_reason=body.reason.strip();row.version+=1
        await db.flush();await s.reserve(db,row,False);s.record(db,p,row,"cancelled",before);await db.flush()
        return await s.booking_view(db,row)
    return await command(db,p,"interviews.cancel:"+str(id),key,body.model_dump(mode="json"),action)

async def finish(db,p,id,body,missed):
    row=await s.get_booking(db,p,id,staff=True,lock=True);s.check_version(row,body.expected_version)
    if row.status!="booked":s.fail("interview_not_active","Встреча уже завершена или отменена.")
    if row.starts_at>datetime.now(timezone.utc):s.fail("interview_not_started","Итог можно записать после начала встречи.")
    if not body.outcome.strip() or not body.public_agreement.strip():s.fail("agreement_required","Запишите итог и договорённость для волонтёра.",422)
    before=s.snapshot(row);row.status="missed" if missed else "completed";row.version+=1
    db.add(InterviewResult(booking_id=id,outcome=body.outcome.strip(),public_agreement=body.public_agreement.strip(),next_contact_date=body.next_contact_date,author_id=p.user_id))
    if body.private_note.strip():db.add(InterviewPrivateNote(booking_id=id,author_id=p.user_id,text=body.private_note.strip()))
    await db.flush();await s.reserve(db,row,False);s.record(db,p,row,row.status,before);await db.flush()
    return await s.booking_view(db,row,staff=True)

@router.post("/interviews/{id}/complete",response_model=StaffBookingView)
async def complete(id:UUID,body:CompleteInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(staff_dep),key:str|None=Header(default=None,alias="Idempotency-Key")):
    return await command(db,p,"interviews.complete:"+str(id),key,body.model_dump(mode="json"),lambda:finish(db,p,id,body,False))

@router.post("/interviews/{id}/mark-missed",response_model=StaffBookingView)
async def missed(id:UUID,body:CompleteInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(staff_dep),key:str|None=Header(default=None,alias="Idempotency-Key")):
    return await command(db,p,"interviews.missed:"+str(id),key,body.model_dump(mode="json"),lambda:finish(db,p,id,body,True))
