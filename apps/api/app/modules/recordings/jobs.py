"""One isolated browser per leased job. Interrupted capture is terminal, never blindly restarted."""
import asyncio
import hashlib
import json
import os
import signal
import tempfile
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import UUID,uuid4
from sqlalchemy import select,update
from app.core.auth import resolve_principal,authz_guard
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.models import Session,MediaAsset
from app.modules.assets.service import asset_path
from app.modules.studio.models import StudioSession
from app.worker.registry import register_handler
from . import service
from .capture import CaptureSettings,encode_and_validate,verify_provider_scope,MAX_CAPTURE_SECONDS
from .models import RecordingTake,RecordingProject,StudioCaptureSession,RecordingRendererGrant,RecordingStageEvent,RecordingSourceFile,RecordingRenderVersion
from .renderer import issue_renderer_ticket

class CaptureFailure(Exception):
    def __init__(self,code):self.code=code

async def checked_take(db,context):
    await context.fence(db)
    row=await db.get(RecordingTake,UUID(context.payload['take_id']),populate_existing=True)
    if not row or row.capture_job_id!=context.job_id or row.generation!=context.payload['generation']:raise CaptureFailure('capture_superseded')
    capture=await db.get(StudioCaptureSession,row.capture_session_id)
    host=await db.get(Session,capture.host_auth_session_id,populate_existing=True)
    if not host or host.revoked_at or host.expires_at<=utcnow():raise CaptureFailure('capture_authority_revoked')
    try:
        principal=await resolve_principal(db,host)
        # Match interactive/renderer ordering: auth advisory key before project/take.
        await authz_guard(db,principal)
    except ApiError:raise CaptureFailure('capture_authority_revoked') from None
    owner=await db.scalar(select(RecordingProject).where(RecordingProject.id==row.project_id).with_for_update().execution_options(populate_existing=True))
    row=await db.scalar(select(RecordingTake).where(RecordingTake.id==row.id).with_for_update().execution_options(populate_existing=True))
    if owner.foundation_id!=context.foundation_id or owner.state=='archived':raise CaptureFailure('capture_superseded')
    studio=await db.get(StudioSession,capture.studio_session_id,populate_existing=True)
    if not studio or studio.generation!=row.generation or studio.state in ('closing','closed','failed') or studio.scene.get('take_id')!=str(row.id):raise CaptureFailure('capture_authority_revoked')
    try:
        await service.authorize(db,principal,owner)
        await service.authorize_capture_session(db,principal,owner,studio)
    except ApiError:raise CaptureFailure('capture_authority_revoked') from None
    if owner.privacy_state!='approved' or row.projection['capture_plan']['privacy_state']!='approved':raise CaptureFailure('capture_privacy_unapproved')
    return row,owner

def hash_path(path):
    digest=hashlib.sha256()
    with path.open('rb') as handle:
        while chunk:=handle.read(512*1024):digest.update(chunk)
    return digest.hexdigest()

async def read_event(process,timeout=30):
    line=await asyncio.wait_for(process.stdout.readline(),timeout)
    if not line or len(line)>8192:raise CaptureFailure('capture_process_lost')
    try:value=json.loads(line)
    except ValueError:raise CaptureFailure('capture_protocol_invalid') from None
    if value.get('event')=='failed':raise CaptureFailure(value['code'] if value.get('code') in ('capture_audio_source_unavailable','capture_audio_scope_invalid','capture_surface_mismatch','capture_tab_timeout','capture_viewport_mismatch','capture_budget_invalid','capture_browser_close_timeout') else 'capture_browser_failed')
    return value

async def send(process,**message):
    process.stdin.write((json.dumps(message)+'\n').encode());await process.stdin.drain()

async def capture_take(db,context):
    settings=CaptureSettings.configured(require_executables=True);process=None;row=None
    try:
        if settings is None:raise CaptureFailure('capture_unavailable')
        row,owner=await checked_take(db,context)
        if row.state in ('captured','failed','discarded'):return {'state':row.state}
        # No in-memory browser survives a worker restart. Existing intent/checkpoint is an
        # unknown capture outcome; create a retake instead of silently replacing sources.
        if row.capture_checkpoint:raise CaptureFailure('capture_interrupted')
        if row.state!='starting':raise CaptureFailure('capture_stopped_before_start')
        ticket=await issue_renderer_ticket(db,row,context=context)
        row.capture_phase='launching';row.capture_checkpoint={'schema_version':1,'job_id':str(context.job_id),'generation':row.generation,'phase':'launching'}
        await db.commit()
        with tempfile.TemporaryDirectory(prefix='opora-capture-') as directory:
            os.chmod(directory,0o700);source=Path(directory)/'capture.webm';output=Path(directory)/'output.mp4'
            script=Path(__file__).with_name('capture_runner.cjs')
            environment={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LANG':'C.UTF-8'}
            process=await asyncio.create_subprocess_exec(settings.node,str(script),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL,env=environment,start_new_session=True,limit=16384)
            from app.integrations.rtc.livekit import RtcSettings
            rtc=RtcSettings.from_env();provider_url=(rtc.public_url or rtc.url).replace('https://','wss://',1).replace('http://','ws://',1)
            await send(process,command='initialize',url=settings.url,chrome=settings.chrome,provider_url=provider_url,ticket=ticket,spool=str(source),audio_track_ids=[track['track_id'] for track in row.projection['capture_plan']['allowed_tracks'] if track['kind']=='audio'],development=settings.development,max_milliseconds=20*60*1000,max_bytes=500*1024*1024);ticket=None
            if (await read_event(process))['event']!='loaded':raise CaptureFailure('capture_protocol_invalid')
            deadline=asyncio.get_running_loop().time()+30
            while True:
                row,owner=await checked_take(db,context)
                if row.state=='stopping':raise CaptureFailure('capture_stopped_before_start')
                ready=service.readiness_current(row)
                if ready:
                    try:await verify_provider_scope(db,row,owner)
                    except Exception:raise CaptureFailure('capture_provider_scope_invalid') from None
                await db.commit()
                if ready:break
                if asyncio.get_running_loop().time()>deadline:raise CaptureFailure('capture_renderer_unready')
                await asyncio.sleep(.25)
            await send(process,command='capture')
            started=await read_event(process,15)
            if started.get('event')!='started' or (started.get('width'),started.get('height'),started.get('display_surface'),started.get('audio_tracks'))!=(1920,1080,'browser',1):raise CaptureFailure('capture_profile_invalid')
            row,owner=await checked_take(db,context)
            expected_audio=sorted(track['track_id'] for track in row.projection['capture_plan']['allowed_tracks'] if track['kind']=='audio')
            if started.get('audio_source')!='approved_rtc_webaudio' or sorted(started.get('audio_track_ids',[]))!=expected_audio:raise CaptureFailure('capture_audio_scope_invalid')
            if not service.capture_ready(row):raise CaptureFailure('capture_readiness_lost')
            row.started_at=datetime.fromtimestamp(started['media_started_at_ms']/1000,tz=timezone.utc)
            capture_started_mono=asyncio.get_running_loop().time()-max(0,(utcnow()-row.started_at).total_seconds())
            if abs((utcnow()-row.started_at).total_seconds())>15:raise CaptureFailure('capture_clock_invalid')
            if row.state!='stopping':row.state='capturing'
            row.capture_phase='capturing';row.version+=1
            row.capture_checkpoint={**row.capture_checkpoint,'phase':'capturing','start':started,'projection_hash':row.projection_hash}
            await db.commit()
            next_scope_check=0
            while True:
                await asyncio.sleep(.25)
                if process.returncode is not None:raise CaptureFailure('capture_process_lost')
                row,owner=await checked_take(db,context)
                if not service.capture_ready(row):raise CaptureFailure('capture_readiness_lost')
                if asyncio.get_running_loop().time()>=next_scope_check:
                    try:await verify_provider_scope(db,row,owner)
                    except Exception:raise CaptureFailure('capture_provider_scope_invalid') from None
                    next_scope_check=asyncio.get_running_loop().time()+1
                if row.state=='capturing' and asyncio.get_running_loop().time()-capture_started_mono>=MAX_CAPTURE_SECONDS:
                    row.state='stopping';row.capture_phase='stopping';row.version+=1;row.capture_checkpoint={**row.capture_checkpoint,'stop_reason':'duration_limit'}
                stopped=row.state=='stopping'
                if row.state not in ('capturing','stopping'):raise CaptureFailure('capture_superseded')
                await db.commit()
                if stopped:break
            await send(process,command='stop');final=await read_event(process,20)
            if final.get('event')!='finalized' or process.returncode not in (None,0) or source.stat().st_size!=final.get('size') or await asyncio.to_thread(hash_path,source)!=final.get('sha256'):raise CaptureFailure('capture_source_invalid')
            row,owner=await checked_take(db,context)
            if not service.capture_ready(row):raise CaptureFailure('capture_readiness_lost')
            row.stopped_at=row.started_at+timedelta(milliseconds=final['duration_ms']);row.capture_phase='closing_browser'
            row.capture_checkpoint={**row.capture_checkpoint,'phase':'closing_browser','source_sha256':final['sha256'],'duration_ms':final['duration_ms']}
            # Revoke only after final frame; closing the browser correctly withdraws its
            # readiness and cannot be interpreted as a failure during MP4 encoding.
            await db.execute(update(RecordingRendererGrant).where(RecordingRendererGrant.take_id==row.id,RecordingRendererGrant.revoked_at.is_(None)).values(revoked_at=utcnow()))
            await db.commit()
            await send(process,command='close')
            try:
                closed=await read_event(process,10)
                if closed.get('event')!='closed' or closed.get('browser_process_exited') is not True:raise CaptureFailure('capture_browser_close_timeout')
                await asyncio.wait_for(process.wait(),5)
            except TimeoutError:raise CaptureFailure('capture_browser_close_timeout') from None
            row,owner=await checked_take(db,context);row.capture_phase='encoding';row.capture_checkpoint={**row.capture_checkpoint,'phase':'encoding'};await db.commit()
            profile=await encode_and_validate(settings,source,output,final['duration_ms'])
            row,owner=await checked_take(db,context)
            events=(await db.scalars(select(RecordingStageEvent).where(RecordingStageEvent.take_id==row.id).order_by(RecordingStageEvent.sequence))).all()
            if not events or any(event.sequence!=index+1 or service.stable_hash(event.projection)!=event.projection_hash for index,event in enumerate(events)) or events[-1].projection_hash!=row.projection_hash:raise CaptureFailure('capture_journal_invalid')
            journal=[]
            for event in events:
                if event.created_at<=row.started_at:clock=0
                elif event.media_time_ms is not None:clock=event.media_time_ms
                else:raise CaptureFailure('capture_journal_frame_unconfirmed')
                if clock>final['duration_ms']+1000:raise CaptureFailure('capture_journal_clock_invalid')
                event.media_time_ms=min(clock,final['duration_ms']);journal.append({'sequence':event.sequence,'renderer_state_version':event.renderer_state_version,'projection_hash':event.projection_hash,'media_time_ms':event.media_time_ms})
            content_hash=await asyncio.to_thread(hash_path,output);size=output.stat().st_size
            if size>500*1024*1024:raise CaptureFailure('capture_output_quota')
            manifest={'schema_version':1,'take_id':str(row.id),'generation':row.generation,'render_profile_version':'opora-stage/1','kind':'validated_browser_composite','raw_fallback':'forbidden','source_sha256':final['sha256'],'output_sha256':content_hash,'media':profile,'start':started,'stop':final,'stage_events':journal,'journal_hash':service.stable_hash(journal)}
            render=RecordingRenderVersion(id=uuid4(),project_id=owner.id,take_id=row.id,generation=row.generation,state='preview_ready',job_id=context.job_id,manifest=manifest,render_hash=service.stable_hash(manifest),content_hash=content_hash,duration_ms=profile['duration_ms'],quality='verified')
            await context.fence(db)
            db.add(render);await db.flush()
            capture=await db.get(StudioCaptureSession,row.capture_session_id)
            host=await db.get(Session,capture.host_auth_session_id)
            principal=await resolve_principal(db,host)
            from app.modules.assets.registry import create_generated_asset_from_file
            asset=await create_generated_asset_from_file(db,principal,content_type='video/mp4',source_path=output,expected_checksum=content_hash,purpose='recording.output',resource_type='recording_render',resource_id=render.id)
            render.asset_id=asset.id
            db.add(RecordingSourceFile(take_id=row.id,asset_id=asset.id,kind='validated_composite',content_hash=content_hash,manifest=manifest,duration_ms=profile['duration_ms'],retained_until=utcnow()+timedelta(days=30)))
            row.state='captured';row.capture_phase='complete';row.version+=1;row.error_code=None;row.readiness_state='blocked';row.capture_checkpoint={'schema_version':1,'phase':'complete','render_id':str(render.id),'content_hash':content_hash,'stop_reason':row.capture_checkpoint.get('stop_reason','owner_requested')}
            await db.flush();return {'state':'captured','render_id':str(render.id)}
    except (CaptureFailure,ValueError,TimeoutError,OSError,KeyError,TypeError) as exc:
        await db.rollback();await context.fence(db)
        row=await db.get(RecordingTake,UUID(context.payload['take_id']),populate_existing=True)
        code=getattr(exc,'code','capture_media_failed')
        if row and row.capture_job_id==context.job_id and row.generation==context.payload['generation'] and row.state not in ('captured','discarded'):
            row.state='failed';row.capture_phase='failed';row.error_code=code;row.version+=1;row.readiness_state='blocked'
            if getattr(exc,'diagnostics',None):row.capture_checkpoint={**(row.capture_checkpoint or {}),'media_validation':exc.diagnostics}
            await db.execute(update(RecordingRendererGrant).where(RecordingRendererGrant.take_id==row.id,RecordingRendererGrant.revoked_at.is_(None)).values(revoked_at=utcnow()))
            # A fresh lease recovering an interrupted capture also removes its exact
            # hidden provider identities; transport loss has a provider grace period.
            await remove_private_participants(db,context,row)
        return {'state':'failed','error_code':code}
    finally:
        if process and process.returncode is None:
            # Give Node its private EOF/close path so Playwright closes Chromium's own
            # process group before the bounded TERM/KILL fallback.
            process.stdin.close()
            try:await asyncio.wait_for(process.wait(),5)
            except TimeoutError:
                try:process.terminate()
                except ProcessLookupError:pass
                try:await asyncio.wait_for(process.wait(),5)
                except TimeoutError:
                    try:os.killpg(process.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    await process.wait()

async def remove_private_participants(db,context,row):
    from app.integrations.rtc.livekit import LiveKitAdapter,RevocationPolicy,ProviderError
    await context.fence(db)
    capture=await db.get(StudioCaptureSession,row.capture_session_id)
    studio=await db.get(StudioSession,capture.studio_session_id)
    grants=(await db.scalars(select(RecordingRendererGrant).where(RecordingRendererGrant.take_id==row.id,RecordingRendererGrant.generation==row.generation,RecordingRendererGrant.purpose=='renderer',RecordingRendererGrant.revoked_at.is_not(None)))).all()
    for grant in grants:
        await context.fence(db)
        try:await LiveKitAdapter().remove_participant(studio.room_name,'opora-renderer-'+grant.id.hex,revoked_at=int(utcnow().timestamp()),policy=RevocationPolicy(studio.require_strict_revocation))
        except (ProviderError,ApiError):
            row.capture_checkpoint={**(row.capture_checkpoint or {}),'renderer_cleanup_pending':True}
            break

register_handler('recording.capture',capture_take,lease_seconds=120,heartbeat_seconds=10,timeout_seconds=1600,workload='media')
