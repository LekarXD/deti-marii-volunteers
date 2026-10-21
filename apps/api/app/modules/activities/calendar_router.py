from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal, get_principal
from app.core.db import get_db
from app.core.errors import ApiError
from .calendar_models import EventOccurrence, EventSeries
from .calendar_schemas import EventOccurrencePage, EventOccurrenceUpdate, EventOccurrenceView, EventSeriesApply, EventSeriesCreate, EventSeriesUpdate, EventSeriesView, SeriesChangePreview, StaffingNeedsUpdate, StaffingNeedView
from .schemas import VersionCommand
from . import calendar_service as service
from .router import command

router=APIRouter(tags=['calendar'])

def read_view(result,principal):
    if not principal.has_permission('schedule.manage'):result.allowed_actions=[]
    return result


async def calendar_staff(principal:Principal=Depends(get_principal)):
    if not (principal.has_permission('schedule.read') or principal.has_permission('schedule.manage')):raise ApiError(403,'permission_denied','Недостаточно прав.')
    return principal

async def calendar_writer(principal:Principal=Depends(get_principal)):
    if not principal.has_permission('schedule.manage'):raise ApiError(403,'permission_denied','Недостаточно прав.')
    return principal


@router.get('/event-occurrences',response_model=EventOccurrencePage,operation_id='listCalendarOccurrences')
async def list_occurrences(from_date:date=Query(alias='from'),to_date:date=Query(alias='to'),display_timezone:str=Query('Europe/Moscow',alias='timezone'),cursor:UUID|None=None,limit:int=Query(100,ge=1,le=500),principal:Principal=Depends(calendar_staff),db:AsyncSession=Depends(get_db)):
    if to_date<from_date or (to_date-from_date).days>366:raise ApiError(422,'calendar_range','Выберите диапазон до 366 дней. Для большого периода запрашивайте части последовательно.')
    entities=(await db.scalars(select(EventSeries).where(EventSeries.foundation_id==principal.foundation_id).order_by(EventSeries.id).with_for_update())).all()
    for entity in entities:await service.materialize(db,entity,from_date-timedelta(days=8),to_date+timedelta(days=1))
    try:zone=ZoneInfo(display_timezone)
    except ZoneInfoNotFoundError:raise ApiError(422,'unknown_timezone','Неизвестный часовой пояс.')
    lower=datetime.combine(from_date,time.min,tzinfo=zone).astimezone(timezone.utc)
    upper=datetime.combine(to_date+timedelta(days=1),time.min,tzinfo=zone).astimezone(timezone.utc)
    query=select(EventOccurrence).where(EventOccurrence.foundation_id==principal.foundation_id,EventOccurrence.starts_at<upper,EventOccurrence.ends_at>lower)
    if cursor:query=query.where(EventOccurrence.id>cursor)
    rows=list((await db.scalars(query.order_by(EventOccurrence.id).limit(limit+1))).all())
    result=EventOccurrencePage(items=[read_view(await service.occurrence_view(db,item),principal) for item in rows[:limit]],next_cursor=rows[limit-1].id if len(rows)>limit else None)
    await db.commit()
    return result


@router.get('/coord/event-series/{series_id}',response_model=EventSeriesView,operation_id='getCalendarSeries')
async def get_series(series_id:UUID,principal:Principal=Depends(calendar_staff),db:AsyncSession=Depends(get_db)):
    return read_view(await service.series_view(db,await service.series(db,principal,series_id)),principal)


@router.post('/coord/event-series',response_model=EventSeriesView,operation_id='createCalendarSeries')
async def create_series(body:EventSeriesCreate,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(calendar_writer),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,'calendar.create-series',key,body,lambda:service.create_series(db,principal,body),request)


@router.post('/coord/event-occurrences',response_model=EventOccurrenceView,operation_id='createCalendarStandaloneOccurrence')
async def create_standalone(body:EventSeriesCreate,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(calendar_writer),db:AsyncSession=Depends(get_db)):
    if body.recurrence.frequency!='once':raise ApiError(422,'standalone_must_be_once','Для повторений создайте серию.')
    async def action():
        created=await service.create_series(db,principal,body)
        entity=await db.scalar(select(EventOccurrence).where(EventOccurrence.series_id==created.id))
        return await service.occurrence_view(db,entity)
    return await command(db,principal,'calendar.create-occurrence',key,body,action,request)


@router.get('/event-occurrences/{occurrence_id}',response_model=EventOccurrenceView,operation_id='getCalendarOccurrence')
async def get_occurrence(occurrence_id:UUID,principal:Principal=Depends(calendar_staff),db:AsyncSession=Depends(get_db)):
    return read_view(await service.occurrence_view(db,await service.occurrence(db,principal,occurrence_id)),principal)


@router.patch('/coord/event-occurrences/{occurrence_id}',response_model=EventOccurrenceView,operation_id='updateCalendarOccurrence')
async def update_occurrence(occurrence_id:UUID,body:EventOccurrenceUpdate,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(calendar_writer),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'calendar.update:{occurrence_id}',key,body,lambda:service.patch_occurrence(db,principal,occurrence_id,body),request)


@router.post('/coord/event-occurrences/{occurrence_id}/cancel',response_model=EventOccurrenceView,operation_id='cancelCalendarOccurrence')
async def cancel_occurrence(occurrence_id:UUID,body:VersionCommand,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(calendar_writer),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'calendar.cancel:{occurrence_id}',key,body,lambda:service.change_occurrence_state(db,principal,occurrence_id,body,'cancelled'),request)


@router.post('/coord/event-occurrences/{occurrence_id}/restore',response_model=EventOccurrenceView,operation_id='restoreCalendarOccurrence')
async def restore_occurrence(occurrence_id:UUID,body:VersionCommand,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(calendar_writer),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'calendar.restore:{occurrence_id}',key,body,lambda:service.change_occurrence_state(db,principal,occurrence_id,body,'scheduled'),request)


@router.get('/coord/event-occurrences/{occurrence_id}/staffing-needs',response_model=list[StaffingNeedView],operation_id='getCalendarStaffingNeeds')
async def get_needs(occurrence_id:UUID,principal:Principal=Depends(calendar_staff),db:AsyncSession=Depends(get_db)):
    return await service.needs_view(db,await service.occurrence(db,principal,occurrence_id))


@router.patch('/coord/event-occurrences/{occurrence_id}/staffing-needs',response_model=EventOccurrenceView,operation_id='updateCalendarStaffingNeeds')
async def patch_needs(occurrence_id:UUID,body:StaffingNeedsUpdate,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(calendar_writer),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'calendar.staffing:{occurrence_id}',key,body,lambda:service.patch_staffing(db,principal,occurrence_id,body),request)


@router.post('/coord/event-series/{series_id}/preview-change',response_model=SeriesChangePreview,operation_id='previewCalendarSeriesChange')
async def preview_series(series_id:UUID,body:EventSeriesUpdate,principal:Principal=Depends(calendar_writer),db:AsyncSession=Depends(get_db)):
    preview,*_=await service.preview_change(db,principal,series_id,body)
    return preview


@router.post('/coord/event-series/{series_id}/apply-change',response_model=EventSeriesView,operation_id='applyCalendarSeriesChange')
async def apply_series(series_id:UUID,body:EventSeriesApply,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(calendar_writer),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'calendar.apply:{series_id}',key,body,lambda:service.apply_change(db,principal,series_id,body),request)


@router.post('/coord/event-series/{series_id}/cancel',response_model=EventSeriesView,operation_id='cancelCalendarSeries')
async def cancel_series(series_id:UUID,body:VersionCommand,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(calendar_writer),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'calendar.cancel-series:{series_id}',key,body,lambda:service.change_series_state(db,principal,series_id,body,'cancelled'),request)


@router.post('/coord/event-series/{series_id}/restore',response_model=EventSeriesView,operation_id='restoreCalendarSeries')
async def restore_series(series_id:UUID,body:VersionCommand,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(calendar_writer),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'calendar.restore-series:{series_id}',key,body,lambda:service.change_series_state(db,principal,series_id,body,'active'),request)
