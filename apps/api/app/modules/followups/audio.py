import asyncio
import shutil
from uuid import UUID
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.models import Job,MediaAsset,Session
from app.core.auth import resolve_principal
from app.integrations.ai.models import AIRun
from app.modules.assets.registry import create_upload_intent
from app.modules.assets.service import require_asset,asset_path
from app.worker.queue import enqueue_job
from .assets import PURPOSE,RESOURCE,authorize_audio_assignment
from .audio_media import audio_duration,MAX_BYTES
from .models import ReflectionAudioUpload
from .schemas import ReflectionAudioView

async def readiness(db,foundation_id):
    if not shutil.which('ffmpeg'):return {'available':False,'reason':'Голосовой ввод пока недоступен: обработчик аудио не настроен. Можно написать текст.'}
    from app.integrations.ai.transcription import transcription_readiness
    value=await transcription_readiness(db,foundation_id,task='reflection.transcribe')
    return value

async def own_audio(db,principal,assignment_id,asset_id,lock=False):
    await authorize_audio_assignment(db,principal,RESOURCE,assignment_id)
    query=select(ReflectionAudioUpload).where(ReflectionAudioUpload.asset_id==asset_id,ReflectionAudioUpload.assignment_id==assignment_id,ReflectionAudioUpload.foundation_id==principal.foundation_id,ReflectionAudioUpload.user_id==principal.user_id)
    row=await db.scalar((query.with_for_update() if lock else query).execution_options(populate_existing=True))
    if row is None:raise ApiError(404,'audio_not_found','Запись не найдена')
    asset=await require_asset(db,principal,asset_id,ready=False)
    await db.refresh(asset)
    if asset.purpose!=PURPOSE or asset.resource_type!=RESOURCE or asset.resource_id!=assignment_id or asset.owner_user_id!=principal.user_id:
        raise ApiError(404,'audio_not_found','Запись не найдена')
    return row,asset

async def view(db,row,asset):
    run=await db.get(AIRun,row.run_id) if row.run_id else None
    job=await db.get(Job,asset.processing_job_id) if asset.processing_job_id else None
    result=job.result or {} if job else {}
    state='cancelled' if row.cancelled_at else run.state if run else result['state'] if result.get('state') in ('failed','unavailable','cancelled') else 'failed' if asset.state=='rejected' or (job and job.state=='dead') else 'queued' if asset.state=='processing' else asset.state
    if state=='succeeded':state='ready' if asset.state=='ready' else 'processing'
    text=(run.output or {}).get('text') if state=='ready' else None
    return ReflectionAudioView(asset_id=asset.id,version=row.version,state=state,asset_state=asset.state,upload_url=f'/api/v1/assets/{asset.id}/upload',received_size=asset.received_size,expected_size=asset.expected_size,content_type=asset.content_type,duration_seconds=row.duration_seconds,transcript=text,error_code=run.error_code if run else result.get('error_code') or (job.error_code if job else None) or ('audio_validation_failed' if asset.state=='rejected' else None),can_retry=state in ('failed','unknown','unavailable','budget_exceeded'))

async def intent(db,principal,assignment_id,body):
    await authorize_audio_assignment(db,principal,RESOURCE,assignment_id)
    available=await readiness(db,principal.foundation_id)
    if not available['available']:raise ApiError(503,'transcription_unconfigured',available['reason'],retryable=False)
    asset=await create_upload_intent(db,principal,content_type=body.content_type,expected_size=body.expected_size,checksum=body.checksum,purpose=PURPOSE,resource_type=RESOURCE,resource_id=assignment_id)
    row=ReflectionAudioUpload(asset_id=asset.id,foundation_id=principal.foundation_id,assignment_id=assignment_id,user_id=principal.user_id,request_session_id=principal.session_id)
    db.add(row);await db.flush()
    return await view(db,row,asset)

def check_version(row,version):
    if row.version!=version:raise ApiError(409,'version_conflict','Запись уже изменилась. Обновите состояние.',current_version=row.version)

async def lock_current_run(db,principal,assignment_id,asset_id):
    # The gateway settles AIRun before its domain completion hook. Commands use
    # the same run -> intent ordering, so cancellation cannot deadlock delivery.
    row,_=await own_audio(db,principal,assignment_id,asset_id)
    if row.run_id:
        await db.scalar(select(AIRun).where(AIRun.id==row.run_id).with_for_update().execution_options(populate_existing=True))

async def cancel(db,principal,assignment_id,asset_id,body):
    await lock_current_run(db,principal,assignment_id,asset_id)
    row,asset=await own_audio(db,principal,assignment_id,asset_id,True);check_version(row,body.expected_version)
    row.cancelled_at=utcnow();row.version+=1;asset.state='rejected'
    if asset.processing_job_id:
        job=await db.get(Job,asset.processing_job_id)
        if job and job.state in ('queued','running'):job.state,job.lease_until='cancelled',None
    # The current-intent hook also closes a provider call already in flight.
    if row.run_id:
        run=await db.get(AIRun,row.run_id)
        if run:
            # Keep an in-flight calling marker durable until the gateway settles
            # its reservation, including recovery after a worker interruption.
            if run.state!='calling':run.state='cancelled'
            run.output,run.error_code=None,'user_cancelled'
    await db.flush();return await view(db,row,asset)

async def retry(db,principal,assignment_id,asset_id,body):
    await lock_current_run(db,principal,assignment_id,asset_id)
    row,asset=await own_audio(db,principal,assignment_id,asset_id,True);check_version(row,body.expected_version)
    previous=await view(db,row,asset)
    if row.cancelled_at or not previous.can_retry:raise ApiError(409,'audio_retry_closed','Для этой записи повторная обработка недоступна')
    available=await readiness(db,principal.foundation_id)
    if not available['available']:raise ApiError(503,'transcription_unconfigured',available['reason'])
    if not asset_path(asset).is_file() or asset.received_size!=asset.expected_size:raise ApiError(409,'audio_source_missing','Запишите аудио ещё раз')
    row.run_id=None;row.request_session_id=principal.session_id;row.version+=1;asset.state='processing'
    job=enqueue_job(db,principal.foundation_id,'followups.audio',{'asset_id':str(asset.id),'resource_type':RESOURCE,'resource_id':str(assignment_id),'source_checksum':asset.checksum})
    asset.processing_job_id=job.id;await db.flush();return await view(db,row,asset)

async def source_principal(db,row):
    session=await db.get(Session,row.request_session_id,populate_existing=True)
    if not session or session.user_id!=row.user_id or session.foundation_id!=row.foundation_id or session.revoked_at or session.expires_at<=utcnow():
        raise ApiError(403,'audio_session_revoked','Сессия записи завершена')
    return await resolve_principal(db,session)

async def process_audio(db,context):
    from app.integrations.ai.transcription import enqueue_transcription
    asset_id=UUID(context.payload['asset_id'])
    row=await db.scalar(select(ReflectionAudioUpload).where(ReflectionAudioUpload.asset_id==asset_id,ReflectionAudioUpload.foundation_id==context.foundation_id))
    asset=await db.get(MediaAsset,asset_id)
    if not row or not asset or row.cancelled_at or asset.processing_job_id!=context.job_id:return {'state':'cancelled'}
    try:
        principal=await source_principal(db,row)
        await own_audio(db,principal,row.assignment_id,row.asset_id)
        if context.payload.get('source_checksum')!=asset.checksum:raise ApiError(409,'audio_source_changed','Запись изменилась')
        def read():
            with asset_path(asset).open('rb') as source:return source.read(MAX_BYTES+1)
        data=await asyncio.to_thread(read)
        import hashlib
        if len(data)!=asset.expected_size or hashlib.sha256(data).hexdigest()!=asset.checksum:raise ValueError('audio_source_changed')
        duration=await asyncio.to_thread(audio_duration,data,asset.content_type)
        await context.fence(db)
        # Recheck after local decode, and lock the intent before linking the run.
        principal=await source_principal(db,row)
        row,asset=await own_audio(db,principal,row.assignment_id,row.asset_id,True)
        if row.cancelled_at or asset.processing_job_id!=context.job_id:return {'state':'cancelled'}
        if row.run_id:return {'state':'queued','run_id':str(row.run_id)}
        row.duration_seconds=duration
        run=await enqueue_transcription(db,principal,asset_id=asset.id,duration_seconds=duration,task='reflection.transcribe')
        row.run_id=run.id;row.version+=1;await db.flush()
        return {'state':'queued','run_id':str(run.id)}
    except ApiError as exc:
        await context.fence(db);asset.state='rejected'
        return {'state':'unavailable' if exc.status_code==503 else 'cancelled','error_code':exc.code}
    except (OSError,ValueError):
        await context.fence(db);asset.state='rejected'
        return {'state':'failed','error_code':'audio_validation_failed'}

async def validate_transcription(db,principal,run,phase):
    asset_id=UUID(run.input_data['asset_id'])
    row=await db.scalar(select(ReflectionAudioUpload).where(ReflectionAudioUpload.asset_id==asset_id,ReflectionAudioUpload.foundation_id==principal.foundation_id,ReflectionAudioUpload.run_id==run.id,ReflectionAudioUpload.user_id==principal.user_id).execution_options(populate_existing=True))
    if row is None or row.cancelled_at:raise ApiError(403,'audio_intent_revoked','Обработка записи отменена')
    await own_audio(db,principal,row.assignment_id,row.asset_id)
    return True

async def complete_transcription(db,run,context):
    await context.fence(db)
    principal=None
    row=await db.scalar(select(ReflectionAudioUpload).where(ReflectionAudioUpload.run_id==run.id,ReflectionAudioUpload.foundation_id==run.foundation_id).with_for_update().execution_options(populate_existing=True))
    if row is None or row.cancelled_at:raise ApiError(403,'audio_intent_revoked','Обработка записи отменена')
    principal=await source_principal(db,row)
    await validate_transcription(db,principal,run,'delivery')
    asset=await db.get(MediaAsset,row.asset_id)
    if run.state=='succeeded':asset.state='ready'
    row.version+=1
