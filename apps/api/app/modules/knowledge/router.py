from uuid import UUID
from fastapi import APIRouter,Depends,Header,Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,authz_guard,get_principal
from app.core.audit import audit
from app.core.clock import utcnow
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.idempotency import begin_command,finish_command
from app.integrations.ai.models import AIDailyUsage,AISettings
from app.integrations.ai.provider import ProviderConfig
from app.integrations.ai.service import run_view,settings
from . import service
from .schemas import AISettingsInput,AISettingsView,AIRunView,AnswerInput,ApplyBuilderAI,BuilderAIInput,EmptyInput,FragmentView,LibraryItemView,LibraryTextView,MentorInput,MentorView,QuestionView,SourceCreate,SourceSave,SourceView,VersionInput
router=APIRouter(prefix='/api/v1',tags=['knowledge'])

async def command(db,principal,request,key,operation,payload,action,permissions=()):
    await authz_guard(db,principal)
    for name in permissions:service.permission(principal,name)
    previous=await begin_command(db,principal,operation,key,payload)
    if previous is not None:
        if operation=='mentor.ask':previous=jsonable_encoder(await service.mentor_view(db,principal,UUID(previous['id'])))
        if operation=='profile.ai_request':
            from app.integrations.ai.profile import profile_run_view
            previous=jsonable_encoder(await profile_run_view(db,principal,UUID(previous['id'])))
        await db.commit()
        return previous
    if operation in {'mentor.ask','mentor.report'}:
        from app.core.rate_limit import rate_limit
        await rate_limit(db,principal.actor_id,operation,limit=20,seconds=3600)
    result=jsonable_encoder(await action())
    audit(db,principal,operation,'knowledge',payload.get('id','self'),fields=tuple(payload),request_id=getattr(request.state,'request_id',None))
    await finish_command(db,principal,operation,key,result)
    await db.commit()
    return result

@router.get('/coord/knowledge/sources',response_model=list[SourceView])
async def sources(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.source_list(db,principal)
@router.post('/coord/knowledge/sources',response_model=SourceView)
async def create_source(body:SourceCreate,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    return await command(db,principal,request,key,'knowledge.create',body.model_dump(mode='json'),lambda:service.create_source(db,principal,body),('knowledge.read','knowledge.write'))
@router.get('/coord/knowledge/sources/{source_id}',response_model=SourceView)
async def source_detail(source_id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    service.permission(principal,'knowledge.read')
    return service.source_view(principal,await service.source(db,principal,source_id))
@router.put('/coord/knowledge/sources/{source_id}',response_model=SourceView)
async def save_source(source_id:UUID,body:SourceSave,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    return await command(db,principal,request,key,'knowledge.save',{'id':str(source_id),**body.model_dump(mode='json')},lambda:service.save_source(db,principal,source_id,body),('knowledge.read','knowledge.write'))
@router.post('/coord/knowledge/sources/{source_id}/review',response_model=SourceView)
async def review_source(source_id:UUID,body:VersionInput,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    return await command(db,principal,request,key,'knowledge.review',{'id':str(source_id),**body.model_dump(mode='json')},lambda:service.review_source(db,principal,source_id,body.expected_version),('knowledge.read','knowledge.publish'))
@router.post('/coord/knowledge/sources/{source_id}/publish',response_model=SourceView)
async def publish_source(source_id:UUID,body:VersionInput,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    return await command(db,principal,request,key,'knowledge.publish',{'id':str(source_id),**body.model_dump(mode='json')},lambda:service.publish_source(db,principal,source_id,body.expected_version),('knowledge.read','knowledge.publish'))
@router.post('/coord/knowledge/sources/{source_id}/archive',response_model=SourceView)
async def archive_source(source_id:UUID,body:VersionInput,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    return await command(db,principal,request,key,'knowledge.archive',{'id':str(source_id),**body.model_dump(mode='json')},lambda:service.archive_source(db,principal,source_id,body.expected_version),('knowledge.read','knowledge.publish'))
@router.post('/coord/knowledge/sources/{source_id}/reindex',response_model=SourceView)
async def reindex(source_id:UUID,body:VersionInput,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    return await command(db,principal,request,key,'knowledge.reindex',{'id':str(source_id),**body.model_dump(mode='json')},lambda:service.reindex(db,principal,source_id,body.expected_version),('knowledge.read','knowledge.publish'))
@router.get('/knowledge/search',response_model=list[FragmentView])
async def search(q:str='',principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.search(db,principal,q) if q.strip() else []
@router.get('/knowledge/fragments/{chunk_id}',response_model=FragmentView)
async def fragment(chunk_id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    items=await service.fragments_by_id(db,principal,[chunk_id])
    if not items:raise ApiError(404,'fragment_unavailable','Источник недоступен')
    return items[0]
@router.get('/knowledge/library',response_model=list[LibraryItemView],operation_id='knowledge_library')
async def library(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.library(db,principal)
@router.get('/knowledge/library/{source_id}',response_model=LibraryTextView,operation_id='knowledge_library_item')
async def library_item(source_id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.library_item(db,principal,source_id)
@router.get('/mentor/runs',response_model=list[MentorView])
async def mentor_history(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.mentor_history(db,principal)
@router.post('/mentor/runs',response_model=MentorView)
async def ask(body:MentorInput,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    return await command(db,principal,request,key,'mentor.ask',body.model_dump(mode='json'),lambda:service.ask_mentor(db,principal,body.question.strip()))
@router.get('/mentor/runs/{run_id}',response_model=MentorView)
async def mentor_run(run_id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.mentor_view(db,principal,run_id)
@router.post('/mentor/runs/{run_id}/escalate')
async def escalate(run_id:UUID,body:EmptyInput,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    return await command(db,principal,request,key,'mentor.escalate',{'id':str(run_id)},lambda:service.escalate(db,principal,run_id))
@router.post('/mentor/runs/{run_id}/report')
async def report(run_id:UUID,body:EmptyInput,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    return await command(db,principal,request,key,'mentor.report',{'id':str(run_id)},lambda:service.escalate(db,principal,run_id,'report'))
@router.get('/coord/knowledge/questions',response_model=list[QuestionView])
async def questions(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.question_list(db,principal)
@router.put('/coord/knowledge/questions/{question_id}/answer')
async def save_answer(question_id:UUID,body:AnswerInput,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    return await command(db,principal,request,key,'knowledge.answer_save',{'id':str(question_id),**body.model_dump(mode='json')},lambda:service.save_answer(db,principal,question_id,body),('knowledge.read','knowledge.write'))
@router.post('/coord/knowledge/questions/{question_id}/answer/review')
async def review_answer(question_id:UUID,body:VersionInput,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    return await command(db,principal,request,key,'knowledge.answer_review',{'id':str(question_id),**body.model_dump(mode='json')},lambda:service.review_answer(db,principal,question_id,body.expected_version),('knowledge.read','knowledge.publish'))
@router.post('/coord/knowledge/questions/{question_id}/answer/publish')
async def publish_answer(question_id:UUID,body:VersionInput,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    return await command(db,principal,request,key,'knowledge.answer_publish',{'id':str(question_id),**body.model_dump(mode='json')},lambda:service.publish_answer(db,principal,question_id,body.expected_version),('knowledge.read','knowledge.write','knowledge.publish'))
@router.get('/coord/knowledge/index-jobs')
async def index_jobs(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    from app.core.models import Job
    service.permission(principal,'knowledge.read')
    jobs=(await db.scalars(select(Job).where(Job.foundation_id==principal.foundation_id,Job.kind.in_(['knowledge.index','knowledge.ingest'])).order_by(Job.created_at.desc()).limit(100))).all()
    return [dict(id=str(job.id),kind=job.kind,state=job.state,error_code=job.error_code,source_id=job.payload.get('source_id')) for job in jobs]
@router.post('/coord/learning/ai-drafts')
async def builder_draft(body:BuilderAIInput,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    return await command(db,principal,request,key,'knowledge.builder_ai',body.model_dump(mode='json'),lambda:service.builder_draft(db,principal,body),('learning.read','learning.write'))
@router.post('/coord/learning/lessons/{lesson_id}/ai-draft/apply')
async def apply_builder(lesson_id:UUID,body:ApplyBuilderAI,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    return await command(db,principal,request,key,'knowledge.builder_apply',{'id':str(lesson_id),**body.model_dump(mode='json')},lambda:service.apply_builder_draft(db,principal,lesson_id,body),('learning.read','learning.write'))
@router.get('/ai/runs/{run_id}',response_model=AIRunView)
async def ai_run(run_id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    result=await run_view(db,principal,run_id)
    if result['task']=='builder.draft':
        service.permission(principal,'learning.read')
        service.permission(principal,'learning.write')
    return result

async def settings_view(db,principal):
    value=await settings(db,principal.foundation_id)
    daily=await db.get(AIDailyUsage,(principal.foundation_id,utcnow().date()))
    config=ProviderConfig()
    return dict(configured=config.configured(),enabled=value.enabled,model=config.model or None,daily_tokens=value.daily_tokens,daily_requests=value.daily_requests,max_concurrent=value.max_concurrent,timeout_seconds=value.timeout_seconds,version=value.version,circuit_open=bool(value.circuit_open_until and value.circuit_open_until>utcnow()),charged_tokens=daily.charged_tokens if daily else 0,reserved_tokens=daily.reserved_tokens if daily else 0,requests=daily.requests if daily else 0)
@router.get('/coord/ai/settings',response_model=AISettingsView)
async def get_ai_settings(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    service.permission(principal,'ai.manage')
    result=await settings_view(db,principal)
    await db.commit()
    return result
@router.put('/coord/ai/settings',response_model=AISettingsView)
async def put_ai_settings(body:AISettingsInput,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    async def action():
        value=await settings(db,principal.foundation_id,True)
        service.check_version(value.version,body.expected_version)
        for name in ['enabled','daily_tokens','daily_requests','max_concurrent','timeout_seconds']:setattr(value,name,getattr(body,name))
        value.version+=1
        return await settings_view(db,principal)
    return await command(db,principal,request,key,'ai.settings',body.model_dump(mode='json'),action,('ai.manage',))


from .schemas import ProfileAIInput,ProfileAIRunView

@router.post('/me/profile/ai-runs',response_model=ProfileAIRunView)
async def request_profile_ai(body:ProfileAIInput,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(None,alias='Idempotency-Key')):
    from app.integrations.ai.profile import enqueue_profile_suggestion,profile_run_view
    async def action():
        run=await enqueue_profile_suggestion(db,principal,expected_profile_version=body.expected_profile_version)
        return await profile_run_view(db,principal,run.id)
    return await command(db,principal,request,key,'profile.ai_request',body.model_dump(mode='json'),action)

@router.get('/me/profile/ai-runs/{run_id}',response_model=ProfileAIRunView)
async def profile_ai_status(run_id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    from app.integrations.ai.profile import profile_run_view
    return await profile_run_view(db,principal,run_id)
