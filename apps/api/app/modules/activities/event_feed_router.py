from datetime import date
from uuid import UUID
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from fastapi import APIRouter,Depends,Header,Query,Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal,require_permission
from app.core.db import get_db
from app.core.errors import ApiError
from .assignment_schemas import AssignmentParticipationView
from .event_feed_schemas import MatchingOptionsView,ReserveView,SignUpCommand,VolunteerEventDetail,VolunteerEventFeed,VolunteerReservePage
from .schemas import VersionCommand
from .router import command
from . import assignment_service as service
from . import event_feed

router=APIRouter(tags=['event-feed'])


@router.get('/me/events',response_model=VolunteerEventFeed,operation_id='listOwnEventFeed')
async def own_feed(from_date:date=Query(alias='from'),to_date:date=Query(alias='to'),display_timezone:str=Query('Europe/Moscow',alias='timezone'),limit:int=Query(60,ge=1,le=200),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    try:zone=ZoneInfo(display_timezone)
    except (ZoneInfoNotFoundError,ValueError):raise ApiError(422,'unknown_timezone','Неизвестный часовой пояс.')
    lower,upper=event_feed.window(from_date,to_date,zone)
    result=await event_feed.feed(db,principal,lower,upper,limit)
    # Reading the feed projects recurring series into the period, like the staff calendar does.
    await db.commit()
    return result


@router.get('/me/reserves',response_model=VolunteerReservePage,operation_id='listOwnReserves')
async def own_reserves(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await event_feed.own_reserves(db,principal)


@router.get('/me/events/{occurrence_id}',response_model=VolunteerEventDetail,operation_id='getOwnEvent')
async def own_event(occurrence_id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await event_feed.detail(db,principal,occurrence_id)


@router.post('/staffing-needs/{need_id}/sign-up',response_model=AssignmentParticipationView,operation_id='signUpForStaffingNeed')
async def sign_up(need_id:UUID,body:SignUpCommand,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'participation.sign-up:{need_id}',key,body,lambda:service.sign_up(db,principal,need_id,body),request)


@router.post('/staffing-needs/{need_id}/reserve',response_model=ReserveView,operation_id='joinStaffingNeedReserve')
async def join_reserve(need_id:UUID,body:VersionCommand,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'participation.reserve:{need_id}',key,body,lambda:service.join_reserve(db,principal,need_id,body),request)


@router.post('/reserves/{reserve_id}/leave',response_model=ReserveView,operation_id='leaveStaffingNeedReserve')
async def leave_reserve(reserve_id:UUID,body:VersionCommand,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'participation.reserve-leave:{reserve_id}',key,body,lambda:service.leave_reserve(db,principal,reserve_id,body),request)


@router.get('/coord/role-matching-options',response_model=MatchingOptionsView,operation_id='getRoleMatchingOptions')
async def matching_options(principal:Principal=Depends(require_permission('roles.manage'))):
    from .directions import matching_options as options
    return MatchingOptionsView(**options())
