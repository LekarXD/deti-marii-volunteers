import json
from datetime import timedelta
from uuid import UUID
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.worker.queue import enqueue_job
from .contracts import TASKS
from .models import AIDailyUsage, AIRun, AISettings
from .provider import ProviderConfig, request_json

async def settings(db,foundation_id,lock=False):
    config=ProviderConfig()
    await db.execute(insert(AISettings).values(foundation_id=foundation_id,enabled=config.enabled).on_conflict_do_nothing())
    query=select(AISettings).where(AISettings.foundation_id==foundation_id)
    return await db.scalar((query.with_for_update() if lock else query).execution_options(populate_existing=True))

async def enqueue_ai_run(db,principal,task,input_data,source_refs=None,max_output_tokens=1200):
    spec=TASKS.get(task)
    if spec is None:
        raise ApiError(503,'ai_task_unavailable','Этот вид обработки пока недоступен')
    if not isinstance(input_data,dict) or set(input_data)-spec.allowed_inputs or len(json.dumps(input_data,ensure_ascii=False).encode())>spec.max_input_bytes or not 100<=max_output_tokens<=4000:
        raise ApiError(422,'ai_input_invalid','Проверьте объём и состав материалов')
    config=ProviderConfig()
    policy=await settings(db,principal.foundation_id)
    run=AIRun(foundation_id=principal.foundation_id,actor_id=principal.actor_id,request_session_id=principal.session_id,task=task,prompt_version=spec.prompt_version,model=config.model or 'unconfigured',input_data=input_data,source_refs=source_refs or [],max_output_tokens=max_output_tokens,state='queued' if policy.enabled and config.configured() else 'unavailable',error_code=None if policy.enabled and config.configured() else 'provider_unconfigured' if not config.configured() else 'ai_disabled')
    db.add(run)
    await db.flush()
    if run.state=='queued':
        enqueue_job(db,principal.foundation_id,'ai.generate',{'run_id':str(run.id)})
    return run

async def run_view(db,principal,run_id):
    value=await db.scalar(select(AIRun).where(AIRun.id==run_id,AIRun.foundation_id==principal.foundation_id,AIRun.actor_id==principal.actor_id))
    if value is None:
        raise ApiError(404,'ai_run_not_found','Обработка не найдена')
    state,error_code,output=value.state,value.error_code,value.output
    if value.task in {'mentor','builder.draft'}:
        from app.modules.knowledge.service import fragments_by_id
        visible=await fragments_by_id(db,principal,value.source_refs)
        if len(visible)!=len(value.source_refs):state,error_code,output='sources_unavailable','sources_unavailable',None
        elif output and not set(output.get('citation_ids',[])).issubset(set(value.source_refs)):
            state,error_code,output='failed','citation_invalid',None
    if value.task=='profile.suggest':
        from .profile import profile_run_view
        profile=await profile_run_view(db,principal,value.id)
        state,error_code,output=profile['state'],profile['error_code'],None
    return {'id':str(value.id),'state':state,'error_code':error_code,'task':value.task,'model':value.model,'prompt_version':value.prompt_version,'output':output,'charged_tokens':value.charged_tokens}

async def settle(db,run,result):
    policy=await settings(db,run.foundation_id,lock=True)
    if run.reservation_day:
        daily=await db.scalar(select(AIDailyUsage).where(AIDailyUsage.foundation_id==run.foundation_id,AIDailyUsage.day==run.reservation_day).with_for_update())
        if run.reserved_tokens:
            charged=result.tokens if result.tokens is not None else run.reserved_tokens
            daily.reserved_tokens=max(0,daily.reserved_tokens-run.reserved_tokens)
            daily.charged_tokens+=charged
            run.charged_tokens=charged
            run.reserved_tokens=0
    run.state,run.error_code,run.output=result.state,result.error_code,result.output
    run.provider_request_id=result.request_id
    run.completed_at=utcnow()
    if result.state=='succeeded':
        policy.failure_count=0
        policy.circuit_open_until=None
    else:
        policy.failure_count+=1
        if policy.failure_count>=3:
            policy.circuit_open_until=utcnow()+timedelta(seconds=60)

async def execute_run(db,context,transport=None):
    from .provider import ProviderResult
    run=await db.scalar(select(AIRun).where(AIRun.id==UUID(context.payload['run_id']),AIRun.foundation_id==context.foundation_id).with_for_update())
    if run is None:
        return {'state':'missing'}
    if run.state=='calling':
        await context.fence(db)
        await settle(db,run,ProviderResult('unknown','previous_call_outcome_unknown'))
        return {'state':'unknown'}
    if run.state!='queued':
        return {'state':run.state}
    if run.task not in TASKS or TASKS[run.task].prompt_version!=run.prompt_version:
        run.state,run.error_code='unavailable','prompt_version_unavailable'
        return {'state':run.state}
    from app.core.models import Session
    from app.core.auth import resolve_principal
    session=await db.get(Session,run.request_session_id)
    if session is None or session.revoked_at or session.expires_at<=utcnow():
        run.state,run.error_code='cancelled','session_expired'
        return {'state':run.state}
    principal=await resolve_principal(db,session)
    if run.task in {'mentor','builder.draft'}:
        from app.modules.knowledge.service import fragments_by_id
        visible=await fragments_by_id(db,principal,run.source_refs)
        if len(visible)!=len(run.source_refs):
            run.state,run.error_code='sources_unavailable','sources_unavailable'
            return {'state':run.state}
    if run.task=='profile.suggest':
        from .profile import validate_profile_source
        try:await validate_profile_source(db,principal,run)
        except ApiError as error:
            run.state,run.error_code='sources_changed',error.code
            return {'state':run.state}
    if run.task=='builder.draft' and not principal.has_permission('learning.write'):
        run.state,run.error_code='cancelled','permission_denied'
        return {'state':run.state}
    policy=await settings(db,run.foundation_id,lock=True)
    config=ProviderConfig()
    now=utcnow()
    if config.model!=run.model:
        run.state,run.error_code='unavailable','model_version_unavailable'
        return {'state':run.state}
    if not policy.enabled or not config.configured():
        run.state,run.error_code='unavailable','provider_unconfigured'
        return {'state':run.state}
    if policy.circuit_open_until and policy.circuit_open_until>now:
        run.state,run.error_code='unavailable','circuit_open'
        return {'state':run.state}
    active=await db.scalar(select(func.count()).select_from(AIRun).where(AIRun.foundation_id==run.foundation_id,AIRun.state=='calling'))
    if active>=policy.max_concurrent:
        run.state,run.error_code='unavailable','concurrency_budget_exceeded'
        return {'state':run.state}
    day=now.date()
    await db.execute(insert(AIDailyUsage).values(foundation_id=run.foundation_id,day=day).on_conflict_do_nothing())
    daily=await db.scalar(select(AIDailyUsage).where(AIDailyUsage.foundation_id==run.foundation_id,AIDailyUsage.day==day).with_for_update())
    spec=TASKS[run.task]
    reserved=len(json.dumps(run.input_data,ensure_ascii=False).encode())+len((spec.system_prompt+json.dumps(spec.output_model.model_json_schema())).encode())+run.max_output_tokens
    if daily.requests>=policy.daily_requests or daily.charged_tokens+daily.reserved_tokens+reserved>policy.daily_tokens:
        run.state,run.error_code='budget_exceeded','daily_budget_exceeded'
        return {'state':run.state}
    daily.requests+=1
    daily.reserved_tokens+=reserved
    run.state,run.reserved_tokens,run.reservation_day,run.calling_started_at='calling',reserved,day,now
    spec=TASKS[run.task]
    data,max_tokens,timeout=run.input_data,run.max_output_tokens,policy.timeout_seconds
    # Commit the calling marker before external IO. A lease-loss/crash can never
    # silently replay a possibly billed request on the next worker attempt.
    await context.fence(db)
    await db.commit()
    result=await request_json(spec,data,config,max_tokens,timeout,transport)
    await context.fence(db)
    run=await db.scalar(select(AIRun).where(AIRun.id==run.id).with_for_update().execution_options(populate_existing=True))
    current_policy=await settings(db,run.foundation_id,lock=True)
    if not current_policy.enabled:
        result=ProviderResult('cancelled','ai_disabled',tokens=result.tokens,request_id=result.request_id)
    await settle(db,run,result)
    await db.flush()
    return {'state':run.state,'run_id':str(run.id)}
