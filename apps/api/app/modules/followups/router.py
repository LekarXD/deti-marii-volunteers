from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,Header,Query,Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal,authz_guard
from app.core.audit import audit
from app.core.contact_policy import contact_guard
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.idempotency import begin_command,finish_command
from . import service
from .models import AssignmentQuestion,Reflection,ReflectionReview,ReflectionReviewNote,SupportSignal
from .schemas import AssignmentPreparationView,AssignmentQuestionInput,AssignmentQuestionView,ChecklistCommand,FollowupCommand,FollowupStaffOptions,OwnReflectionView,QuestionAnswerCommand,ReflectionDraftCommand,ReflectionPrivateNoteView,ReflectionReviewCommand,ReflectionStaffPage,SignalActionCommand,StaffReflectionView,SupportSignalPage,SupportSignalView


def private_response(response:Response):response.headers['Cache-Control']='private, no-store'
router=APIRouter(prefix='/api/v1',tags=['followups'],dependencies=[Depends(private_response)])

async def command(db,principal,operation,key,body,authorize,action,entity_type,entity_id,fields):
    await authz_guard(db,principal)
    # Same outer ordering as CRM opt-outs and notification dispatch decisions.
    await contact_guard(db,principal.foundation_id)
    await authorize() # Entity scope/private permission is rechecked BEFORE replay.
    replay=await begin_command(db,principal,operation,key,body.model_dump(mode='json'))
    if replay is not None:
        await db.commit();return replay
    result=await action();value=result.model_dump(mode='json')
    audit(db,principal,operation,entity_type,entity_id,fields=fields)
    await finish_command(db,principal,operation,key,value);await db.commit();return value

async def authorize_own(db,principal,id,confirmed=False):
    item,event=await service.own_assignment(db,principal,id)
    if confirmed and (item.status!='confirmed' or event.status=='cancelled'):raise ApiError(409,'assignment_inactive','Нужно действующее подтверждённое назначение.')

@router.get('/me/assignments/{assignment_id}/preparation',response_model=AssignmentPreparationView)
async def preparation(assignment_id:UUID,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal)):
    return await service.preparation(db,principal,assignment_id)

@router.put('/me/assignments/{assignment_id}/checklist',response_model=AssignmentPreparationView)
async def checklist(assignment_id:UUID,body:ChecklistCommand,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    return await command(db,principal,f'followups.checklist:{assignment_id}',key,body,lambda:authorize_own(db,principal,assignment_id,True),lambda:service.save_checklist(db,principal,assignment_id,body),'assignment',assignment_id,['checklist'])

@router.post('/me/assignments/{assignment_id}/questions',response_model=AssignmentQuestionView)
async def question(assignment_id:UUID,body:AssignmentQuestionInput,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    return await command(db,principal,f'followups.question:{assignment_id}',key,body,lambda:authorize_own(db,principal,assignment_id),lambda:service.create_question(db,principal,assignment_id,body),'assignment',assignment_id,['question'])

@router.get('/me/assignments/{assignment_id}/reflection',response_model=OwnReflectionView)
async def reflection(assignment_id:UUID,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal)):
    return await service.reflection_view(db,principal,assignment_id)

@router.put('/me/assignments/{assignment_id}/reflection',response_model=OwnReflectionView)
async def save_reflection(assignment_id:UUID,body:ReflectionDraftCommand,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    return await command(db,principal,f'followups.reflection.save:{assignment_id}',key,body,lambda:authorize_own(db,principal,assignment_id,True),lambda:service.save_reflection(db,principal,assignment_id,body),'assignment',assignment_id,['reflection_draft'])

@router.post('/me/assignments/{assignment_id}/reflection/submit',response_model=OwnReflectionView)
async def submit_reflection(assignment_id:UUID,body:FollowupCommand,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    return await command(db,principal,f'followups.reflection.submit:{assignment_id}',key,body,lambda:authorize_own(db,principal,assignment_id,True),lambda:service.submit_reflection(db,principal,assignment_id,body),'assignment',assignment_id,['reflection_submitted'])

@router.post('/me/assignments/{assignment_id}/reflection/audio-intent')
async def audio_unavailable(assignment_id:UUID,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal)):
    await authorize_own(db,principal,assignment_id,True)
    raise ApiError(503,'transcription_unconfigured','Голосовой ввод пока недоступен. Можно написать текст.',retryable=False)

@router.get('/coord/reflections',response_model=ReflectionStaffPage)
async def reflections(limit:int=Query(100,ge=1,le=200),db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal)):
    service.any_permission(principal,'followups.read')
    rows=(await db.scalars(select(Reflection).where(Reflection.submitted_at.is_not(None),service.scope(principal,'followups.read',Reflection),service.privacy(principal,Reflection)).order_by(Reflection.submitted_at.desc(),Reflection.id).limit(limit))).all()
    return {'items':[await service.reflection_view(db,principal,row.assignment_id,staff_row=row) for row in rows]}

@router.get('/coord/reflections/{reflection_id}',response_model=StaffReflectionView)
async def staff_reflection(reflection_id:UUID,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal)):
    row=await service.staff_reflection(db,principal,reflection_id)
    return await service.reflection_view(db,principal,row.assignment_id,staff_row=row)

async def authorize_review(db,principal,id,body):
    row=await service.staff_reflection(db,principal,id,'followups.manage')
    if body.internal_note.strip() and not service.has(principal,'followups.private_notes',row.group_id):service.denied()

@router.post('/coord/reflections/{reflection_id}/review',response_model=StaffReflectionView)
async def review(reflection_id:UUID,body:ReflectionReviewCommand,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    return await command(db,principal,f'followups.reflection.review:{reflection_id}',key,body,lambda:authorize_review(db,principal,reflection_id,body),lambda:service.review_reflection(db,principal,reflection_id,body),'reflection',reflection_id,['public_review','private_note' if body.internal_note.strip() else 'decision'])

@router.get('/coord/reflections/{reflection_id}/private-notes',response_model=list[ReflectionPrivateNoteView])
async def private_notes(reflection_id:UUID,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal)):
    row=await service.staff_reflection(db,principal,reflection_id)
    if not service.has(principal,'followups.private_notes',row.group_id):service.denied()
    rows=(await db.execute(select(ReflectionReviewNote,ReflectionReview.id).join(ReflectionReview,ReflectionReview.id==ReflectionReviewNote.review_id).where(ReflectionReview.reflection_id==row.id).order_by(ReflectionReviewNote.created_at))).all()
    return [ReflectionPrivateNoteView(review_id=review_id,text=note.text,author_id=note.author_id,created_at=note.created_at) for note,review_id in rows]

@router.get('/coord/followups/staff-options',response_model=FollowupStaffOptions)
async def staff_options(group_id:UUID|None=None,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal)):
    service.any_permission(principal,'followups.manage')
    rows=await service.staff_options(db,principal.foundation_id)
    return {'items':[{'id':row.id,'display_name':row.display_name,'restricted_eligible':await service.owner_eligible(db,principal.foundation_id,row.id,group_id,True)} for row in rows]}

@router.get('/coord/signals',response_model=SupportSignalPage)
async def signals(state:Literal['open','in_progress','resolved','dismissed']|None=None,limit:int=Query(100,ge=1,le=200),db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal)):
    service.any_permission(principal,'followups.read')
    query=select(SupportSignal).where(service.scope(principal,'followups.read',SupportSignal),service.privacy(principal,SupportSignal))
    if state:query=query.where(SupportSignal.state==state)
    rows=(await db.scalars(query.order_by(SupportSignal.created_at.desc(),SupportSignal.id).limit(limit))).all()
    return {'items':[await service.signal_view(db,row,principal) for row in rows]}

@router.get('/coord/signals/{signal_id}',response_model=SupportSignalView)
async def signal(signal_id:UUID,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal)):
    return await service.signal_view(db,await service.staff_signal(db,principal,signal_id),principal)

def signal_endpoint(action):
    async def endpoint(signal_id:UUID,body:SignalActionCommand,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
        return await command(db,principal,f'followups.signal.{action}:{signal_id}',key,body,lambda:service.staff_signal(db,principal,signal_id,'followups.manage'),lambda:service.signal_action(db,principal,signal_id,body,action),'signal',signal_id,[action])
    return endpoint
for _action in ('assign','resolve','dismiss','reopen'):
    router.add_api_route('/coord/signals/{signal_id}/'+_action,signal_endpoint(_action),methods=['POST'],response_model=SupportSignalView,operation_id='support_signal_'+_action)

@router.post('/coord/assignment-questions/{question_id}/answer',response_model=AssignmentQuestionView)
async def answer(question_id:UUID,body:QuestionAnswerCommand,db:AsyncSession=Depends(get_db),principal:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    return await command(db,principal,f'followups.question.answer:{question_id}',key,body,lambda:service.staff_question(db,principal,question_id),lambda:service.answer_question(db,principal,question_id,body),'assignment_question',question_id,['public_answer'])
