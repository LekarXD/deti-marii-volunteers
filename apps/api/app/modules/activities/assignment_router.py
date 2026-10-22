from datetime import date,datetime,time,timedelta,timezone
from typing import Literal
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from uuid import UUID
from fastapi import APIRouter,Depends,Header,Query,Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal,require_permission
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.models import User
from .calendar_models import EventOccurrence
from .assignment_models import Assignment,OpportunityResponse
from .assignment_schemas import AssignmentInvite,AssignmentParticipationPage,AssignmentParticipationView,AssignmentRequirementDecision,AssignmentSuggestion,AttendanceCommand,OwnAssignmentDecision,ParticipationDecision,ParticipationResponseCreate,ParticipationResponsePage,ParticipationResponseView
from .schemas import VersionCommand
from .router import command
from . import assignment_service as service
from .event_feed import plural

router=APIRouter(tags=['participation'])
coordinator=require_permission('assignments.manage')


@router.post('/opportunities/{opportunity_id}/responses',response_model=ParticipationResponseView,operation_id='respondToOpportunity')
async def respond(opportunity_id:UUID,body:ParticipationResponseCreate,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'participation.respond:{opportunity_id}',key,body,lambda:service.respond(db,principal,opportunity_id,body),request)


async def responses_list(db,principal,staff,cursor,limit,opportunity_id=None,awaiting=False):
    query=select(OpportunityResponse).where(OpportunityResponse.foundation_id==principal.foundation_id)
    if not staff:query=query.where(OpportunityResponse.user_id==principal.user_id)
    if opportunity_id:query=query.where(OpportunityResponse.opportunity_id==opportunity_id)
    if awaiting:query=query.where(OpportunityResponse.state.in_(('submitted','under_review','preparation_requested')))
    if cursor:query=query.where(OpportunityResponse.id>cursor)
    rows=list((await db.scalars(query.order_by(OpportunityResponse.id).limit(limit+1))).all())
    return ParticipationResponsePage(items=[await service.response_view(db,row,principal) for row in rows[:limit]],next_cursor=rows[limit-1].id if len(rows)>limit else None)


@router.get('/me/responses',response_model=ParticipationResponsePage,operation_id='getOwnOpportunityResponses')
async def own_responses(opportunity_id:UUID|None=None,cursor:UUID|None=None,limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    service.require_user(principal)
    return await responses_list(db,principal,False,cursor,limit,opportunity_id)


@router.get('/coord/responses',response_model=ParticipationResponsePage,operation_id='getStaffOpportunityResponses')
async def staff_responses(opportunity_id:UUID|None=None,awaiting:bool=False,cursor:UUID|None=None,limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(coordinator),db:AsyncSession=Depends(get_db)):
    return await responses_list(db,principal,True,cursor,limit,opportunity_id,awaiting)


@router.post('/responses/{response_id}/withdraw',response_model=ParticipationResponseView,operation_id='withdrawOpportunityResponse')
async def withdraw(response_id:UUID,body:VersionCommand,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'participation.withdraw:{response_id}',key,body,lambda:service.decide_response(db,principal,response_id,body,'withdrawn',True),request)


@router.post('/responses/{response_id}/resubmit',response_model=ParticipationResponseView,operation_id='resubmitOpportunityResponse')
async def resubmit(response_id:UUID,body:VersionCommand,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'participation.resubmit:{response_id}',key,body,lambda:service.decide_response(db,principal,response_id,body,'submitted',True),request)


@router.post('/coord/responses/{response_id}/approve',response_model=ParticipationResponseView,operation_id='approveOpportunityResponse')
async def approve_response(response_id:UUID,body:ParticipationDecision,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(coordinator),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'assignments.response-approve:{response_id}',key,body,lambda:service.decide_response(db,principal,response_id,body,'approved'),request)


@router.post('/coord/responses/{response_id}/decline',response_model=ParticipationResponseView,operation_id='declineOpportunityResponse')
async def decline_response(response_id:UUID,body:ParticipationDecision,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(coordinator),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'assignments.response-decline:{response_id}',key,body,lambda:service.decide_response(db,principal,response_id,body,'declined'),request)


@router.post('/coord/responses/{response_id}/request-preparation',response_model=ParticipationResponseView,operation_id='requestOpportunityPreparation')
async def prepare_response(response_id:UUID,body:ParticipationDecision,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(coordinator),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'assignments.response-prepare:{response_id}',key,body,lambda:service.decide_response(db,principal,response_id,body,'preparation_requested'),request)


@router.get('/coord/staffing-needs/{need_id}/suggestions',response_model=list[AssignmentSuggestion],operation_id='suggestAssignmentVolunteers')
async def suggestions(need_id:UUID,q:str=Query('',max_length=200),principal:Principal=Depends(coordinator),db:AsyncSession=Depends(get_db)):
    from app.core.clock import utcnow
    from .calendar_models import StaffingNeed
    from . import ranking
    need=await db.get(StaffingNeed,need_id)
    if need is None or need.foundation_id!=principal.foundation_id:raise ApiError(404,'need_not_found','Потребность не найдена.')
    occurrence=await db.get(EventOccurrence,need.occurrence_id);now=utcnow()
    names=dict((await db.execute(select(User.id,User.display_name).where(User.foundation_id==principal.foundation_id,User.account_state=='active',User.display_name.ilike('%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%',escape='\\')))).all())
    facts=await ranking.load_facts(db,principal.foundation_id,list(names),now)
    role=(await ranking.load_roles(db,principal.foundation_id,[need.role_id])).get(need.role_id)
    statuses=dict((await db.execute(select(Assignment.user_id,Assignment.status).where(Assignment.foundation_id==principal.foundation_id,Assignment.occurrence_id==need.occurrence_id))).all())
    ranked=sorted(((ranking.score_need(item,occurrence,role,now),item) for item in facts.values() if ranking.exclusion(item,occurrence) is None),
        key=lambda pair:(-pair[0].score,-pair[0].familiar_visits,names[pair[1].user_id],str(pair[1].user_id)))[:50]
    texts={'skill':'Подходит по навыку «{value}»','direction':'Подходит по направлению «{value}»','unknown_direction':'В анкете: «Пока не знаю»',
        'familiar_new':'Недавно в этой группе','time_history':'Обычно приходит: {value}','time_window':'Удобно по графику: {value}'}
    def text(reason):
        if reason.code!='familiar':return texts[reason.code].format(value=reason.value)
        return f'{reason.count} {plural(reason.count,"посещение","посещения","посещений")} этой группы за полгода'
    return [AssignmentSuggestion(user_id=item.user_id,display_name=names[item.user_id],reasons=[text(reason) for reason in score.reasons],missing_data=ranking.missing_data(item),
        facts={'invited':item.invited_count,'confirmed':item.confirmed_count,'attended':item.attended_count},invitation_status=statuses.get(item.user_id)) for score,item in ranked]


@router.post('/coord/staffing-needs/{need_id}/invitations',response_model=AssignmentParticipationView,operation_id='inviteAssignmentVolunteer')
async def invite(need_id:UUID,body:AssignmentInvite,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(coordinator),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'assignments.invite:{need_id}',key,body,lambda:service.invite(db,principal,need_id,body),request)


async def assignment_list(db,principal,staff,occurrence_id,cursor,limit):
    query=select(Assignment).where(Assignment.foundation_id==principal.foundation_id)
    if not staff:query=query.where(Assignment.user_id==principal.user_id)
    if occurrence_id:query=query.where(Assignment.occurrence_id==occurrence_id)
    if cursor:query=query.where(Assignment.id>cursor)
    rows=list((await db.scalars(query.order_by(Assignment.id).limit(limit+1))).all())
    return AssignmentParticipationPage(items=[await service.assignment_view(db,row,principal) for row in rows[:limit]],next_cursor=rows[limit-1].id if len(rows)>limit else None)


@router.get('/me/assignments',response_model=AssignmentParticipationPage,operation_id='listOwnAssignments')
async def own_assignments(cursor:UUID|None=None,limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    service.require_user(principal)
    return await assignment_list(db,principal,False,None,cursor,limit)


@router.get('/me/schedule',response_model=AssignmentParticipationPage,operation_id='listOwnSchedule')
async def own_schedule(from_date:date=Query(alias='from'),to_date:date=Query(alias='to'),display_timezone:str=Query('Europe/Moscow',alias='timezone'),state:Literal['all','active','cancelled']='all',cursor:UUID|None=None,limit:int=Query(100,ge=1,le=500),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    service.require_user(principal)
    if to_date<from_date or (to_date-from_date).days>366:
        raise ApiError(422,'schedule_range','Выберите диапазон до 366 дней. Другие даты можно запросить отдельно.')
    try:zone=ZoneInfo(display_timezone)
    except (ZoneInfoNotFoundError,ValueError):raise ApiError(422,'unknown_timezone','Неизвестный часовой пояс.')
    lower=datetime.combine(from_date,time.min,tzinfo=zone).astimezone(timezone.utc)
    upper=datetime.combine(to_date+timedelta(days=1),time.min,tzinfo=zone).astimezone(timezone.utc)
    query=select(Assignment).join(EventOccurrence,Assignment.occurrence_id==EventOccurrence.id).where(
        Assignment.foundation_id==principal.foundation_id,Assignment.user_id==principal.user_id,
        EventOccurrence.foundation_id==principal.foundation_id,EventOccurrence.starts_at<upper,EventOccurrence.ends_at>lower)
    if state=='active':query=query.where(Assignment.status.in_(('invited','confirmed')),EventOccurrence.status=='scheduled')
    elif state=='cancelled':query=query.where(Assignment.status.in_(('declined','cancelled','expired')) | (EventOccurrence.status=='cancelled'))
    if cursor:query=query.where(Assignment.id>cursor)
    rows=list((await db.scalars(query.order_by(Assignment.id).limit(limit+1))).all())
    return AssignmentParticipationPage(items=[await service.assignment_view(db,row,principal) for row in rows[:limit]],next_cursor=rows[limit-1].id if len(rows)>limit else None)


@router.get('/coord/assignments',response_model=AssignmentParticipationPage,operation_id='listStaffAssignments')
async def staff_assignments(occurrence_id:UUID|None=None,cursor:UUID|None=None,limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(coordinator),db:AsyncSession=Depends(get_db)):
    return await assignment_list(db,principal,True,occurrence_id,cursor,limit)


@router.get('/assignments/{assignment_id}',response_model=AssignmentParticipationView,operation_id='getParticipationAssignment')
async def detail(assignment_id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    service.require_user(principal)
    return await service.assignment_view(db,await service.assignment(db,principal,assignment_id),principal)


@router.post('/coord/assignments/{assignment_id}/approve',response_model=AssignmentParticipationView,operation_id='approveAssignment')
async def approve(assignment_id:UUID,body:ParticipationDecision,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(coordinator),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'assignments.approve:{assignment_id}',key,body,lambda:service.approve(db,principal,assignment_id,body),request)


@router.post('/coord/assignments/{assignment_id}/requirements',response_model=AssignmentParticipationView,operation_id='reviewAssignmentRequirement')
async def review_requirement(assignment_id:UUID,body:AssignmentRequirementDecision,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(coordinator),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'assignments.review:{assignment_id}',key,body,lambda:service.review_requirement(db,principal,assignment_id,body),request)


@router.post('/assignments/{assignment_id}/confirm',response_model=AssignmentParticipationView,operation_id='confirmOwnAssignment')
async def confirm(assignment_id:UUID,body:VersionCommand,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'participation.confirm:{assignment_id}',key,body,lambda:service.confirm(db,principal,assignment_id,body),request)


@router.post('/assignments/{assignment_id}/decline',response_model=AssignmentParticipationView,operation_id='declineOwnAssignment')
async def decline(assignment_id:UUID,body:OwnAssignmentDecision,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'participation.decline:{assignment_id}',key,body,lambda:service.cancel(db,principal,assignment_id,body,'declined',True),request)


@router.post('/assignments/{assignment_id}/cancel',response_model=AssignmentParticipationView,operation_id='cancelOwnAssignment')
async def cancel_own(assignment_id:UUID,body:OwnAssignmentDecision,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'participation.cancel:{assignment_id}',key,body,lambda:service.cancel(db,principal,assignment_id,body,'cancelled',True),request)


@router.post('/coord/assignments/{assignment_id}/cancel',response_model=AssignmentParticipationView,operation_id='cancelStaffAssignment')
async def cancel_staff(assignment_id:UUID,body:ParticipationDecision,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(coordinator),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'assignments.cancel:{assignment_id}',key,body,lambda:service.cancel(db,principal,assignment_id,body),request)


@router.post('/coord/assignments/{assignment_id}/attendance',response_model=AssignmentParticipationView,operation_id='recordAssignmentAttendance')
async def attendance(assignment_id:UUID,body:AttendanceCommand,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(coordinator),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'assignments.attendance:{assignment_id}',key,body,lambda:service.record_attendance(db,principal,assignment_id,body),request)


@router.post('/coord/assignments/{assignment_id}/attendance/correct',response_model=AssignmentParticipationView,operation_id='correctAssignmentAttendance')
async def correct_attendance(assignment_id:UUID,body:AttendanceCommand,request:Request,key:str=Header(alias='Idempotency-Key'),principal:Principal=Depends(coordinator),db:AsyncSession=Depends(get_db)):
    return await command(db,principal,f'assignments.attendance-correct:{assignment_id}',key,body,lambda:service.record_attendance(db,principal,assignment_id,body,True),request)
