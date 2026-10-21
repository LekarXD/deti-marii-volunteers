"""Dedicated fenced media work; never runs in the default outbox worker."""
import asyncio
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import time
from uuid import UUID,uuid4
from datetime import datetime,timezone
from sqlalchemy import select
from PIL import Image
from app.core.models import MediaAsset,User,Session
from app.modules.assets.service import asset_path
from app.worker.registry import register_handler
from app.integrations.rtc.livekit import LiveKitAdapter,RevocationPolicy,identity
from .models import StudioSession,WebinarEnrollment,SlideDeck,SlideDeckVersion,SlidePage
from .slides_convert import sniff,normalize_image,pdf_page_count,render_pdf_page,strip_external_links,soffice_command,converted_pdf,ConvertError,MAX_PAGES

async def converted_pages(data,workdir):
    import sys,signal
    source=workdir/'input.bin';await asyncio.to_thread(source.write_bytes,data)
    api_root=Path(__file__).resolve().parents[3]
    env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'LANG':'C.UTF-8','PYTHONPATH':str(api_root),'PYTHONDONTWRITEBYTECODE':'1'}
    if os.getenv('OPORA_STUDIO_SOFFICE'):env['OPORA_STUDIO_SOFFICE']=os.environ['OPORA_STUDIO_SOFFICE']
    process=await asyncio.create_subprocess_exec(sys.executable,'-m','app.modules.studio.convert_worker','--input',str(source),'--output',str(workdir),env=env,start_new_session=True,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
    try:
        await asyncio.wait_for(process.wait(),240)
        manifest=json.loads((workdir/'manifest.json').read_text())
        if process.returncode or manifest.get('state')!='ready':raise ConvertError(manifest.get('error_code','convert_failed'))
        count=manifest.get('pages')
        if not isinstance(count,int) or not 1<=count<=MAX_PAGES:raise ConvertError('page_limit')
        pages=[];total=0
        for index in range(count):
            page=await asyncio.to_thread((workdir/f'page-{index}.jpg').read_bytes);total+=len(page)
            if total>64*1024*1024:raise ConvertError('render_size_limit')
            pages.append(page)
        return pages
    finally:
        if process.returncode is None:
            # Kill the converter AND its LibreOffice child on timeout/lease cancellation.
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            await process.wait()

async def convert_slides(db,context):
    asset=await db.get(MediaAsset,UUID(context.payload['asset_id']))
    deck=await db.get(SlideDeck,UUID(context.payload['resource_id']))
    if not asset or not deck or deck.foundation_id!=context.foundation_id or asset.foundation_id!=context.foundation_id or deck.source_asset_id!=asset.id or asset.checksum!=context.payload.get('source_checksum') or asset.processing_job_id!=context.job_id:return {'state':'superseded'}
    if deck.state=='ready':return {'state':'ready'}
    error=None
    try:
        data=await asyncio.to_thread(asset_path(asset).read_bytes)
        if hashlib.sha256(data).hexdigest()!=asset.checksum:raise ConvertError('source_checksum_mismatch')
        with tempfile.TemporaryDirectory(prefix='opora-slides-') as directory:pages=await converted_pages(data,Path(directory))
    except (ConvertError,FileNotFoundError,ImportError,TimeoutError) as exc:
        error=getattr(exc,'code','conversion_timeout' if isinstance(exc,TimeoutError) else 'converter_unavailable' if isinstance(exc,ImportError) else 'source_unavailable')
    await context.fence(db)
    # Fence and source pointer are checked again before publishing immutable output rows.
    await db.refresh(deck,with_for_update=True);await db.refresh(asset,with_for_update=True)
    if deck.source_asset_id!=asset.id or asset.processing_job_id!=context.job_id:return {'state':'superseded'}
    if error:
        deck.state='failed';deck.error_code=error;deck.version+=1;asset.state='failed'
        await db.flush();return {'state':'failed','error_code':error}
    version=SlideDeckVersion(id=uuid4(),deck_id=deck.id,number=1,source_sha256=asset.checksum,conversion_profile='opora-slides/1');db.add(version);await db.flush()
    for ordinal,data in enumerate(pages):
        with Image.open(io.BytesIO(data)) as image:width,height=image.size
        checksum=hashlib.sha256(data).hexdigest()
        output=MediaAsset(id=uuid4(),foundation_id=deck.foundation_id,owner_user_id=deck.owner_user_id,storage_key=uuid4().hex,content_type='image/jpeg',expected_size=len(data),received_size=len(data),checksum=checksum,state='ready')
        path=asset_path(output)
        def write():
            path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
            with path.open('xb') as handle:handle.write(data);handle.flush();os.fsync(handle.fileno())
        await asyncio.to_thread(write)
        db.add(output);await db.flush()
        db.add(SlidePage(deck_version_id=version.id,ordinal=ordinal,asset_id=output.id,width=width,height=height,sha256=checksum))
    deck.state='ready';deck.error_code=None;deck.version+=1;asset.state='ready'
    await db.flush();return {'state':'ready','deck_version_id':str(version.id),'pages':len(pages)}

async def close_studio(db,context):
    row=await db.get(StudioSession,UUID(context.payload['session_id']))
    if not row or row.foundation_id!=context.foundation_id or row.generation!=context.payload['generation'] or row.state!='closing':return {'state':'superseded'}
    await LiveKitAdapter().close_room(row.room_name)
    await context.fence(db);await db.refresh(row,with_for_update=True)
    if row.state=='closing':row.state='closed';row.closed_at=datetime.now(timezone.utc);row.version+=1
    return {'state':row.state}

async def revoke_studio(db,context):
    webinar_id,user_id=UUID(context.payload['webinar_id']),UUID(context.payload['user_id'])
    enrollment=await db.scalar(select(WebinarEnrollment).where(WebinarEnrollment.webinar_id==webinar_id,WebinarEnrollment.user_id==user_id,WebinarEnrollment.foundation_id==context.foundation_id))
    if not enrollment or enrollment.version!=context.payload['enrollment_version'] or enrollment.state=='enrolled':return {'state':'superseded'}
    rows=(await db.scalars(select(StudioSession).where(StudioSession.foundation_id==context.foundation_id,StudioSession.resource_kind=='live_event',StudioSession.resource_id==webinar_id,StudioSession.state.in_(['opening','live','closing'])))).all()
    adapter=LiveKitAdapter()
    for row in rows:await adapter.remove_participant(row.room_name,identity(user_id),revoked_at=int(time.time()),policy=RevocationPolicy(row.require_strict_revocation))
    await context.fence(db);return {'state':'removed','strict_revocation':adapter.settings.capabilities().strict_token_revocation}

async def reconcile_participant(db,context):
    row=await db.get(StudioSession,UUID(context.payload['session_id']));participant_identity=context.payload.get('identity','')
    if not row or row.foundation_id!=context.foundation_id or row.generation!=context.payload['generation']:return {'state':'superseded'}
    from app.core.auth import resolve_principal,authz_guard
    from . import service as studio
    participants=await LiveKitAdapter().participants(row.room_name)
    participant=next((part for part in participants if part.get('identity')==participant_identity),None)
    if participant is None:return {'state':'absent'}
    allowed=False
    if participant_identity.startswith('opora-u'):
        try:
            metadata=json.loads(participant.get('metadata','{}'))
            auth_session=await db.get(Session,UUID(metadata['auth_session_id']))
            if not auth_session or auth_session.revoked_at or auth_session.expires_at<=datetime.now(timezone.utc):raise ValueError()
            principal=await resolve_principal(db,auth_session);await authz_guard(db,principal)
            if principal.foundation_id!=row.foundation_id or not principal.user_id or identity(principal.user_id)!=participant_identity:raise ValueError()
            context=await studio.authorize_resource(db,principal,row.resource_kind,row.resource_id)
            allowed=(context.can_host and row.state in ('opening','live')) or (not context.can_host and row.state=='live')
        except (ValueError,KeyError,TypeError):allowed=False
        except Exception as exc:
            from app.core.errors import ApiError
            if isinstance(exc,ApiError):allowed=False
            else:raise
    else:
        allowed=await studio.internal_participant_allowed(db,row,participant)
    if not allowed:await LiveKitAdapter().remove_participant(row.room_name,participant_identity,revoked_at=int(time.time()),policy=RevocationPolicy(row.require_strict_revocation))
    await context.fence(db);return {'state':'authorized' if allowed else 'removed'}

register_handler('slides.convert',convert_slides,lease_seconds=120,heartbeat_seconds=20,timeout_seconds=600,workload='media')
register_handler('studio.close',close_studio,lease_seconds=30,heartbeat_seconds=5,timeout_seconds=20,workload='io')
register_handler('studio.revoke',revoke_studio,lease_seconds=30,heartbeat_seconds=5,timeout_seconds=20,workload='io')
register_handler('studio.reconcile_participant',reconcile_participant,lease_seconds=30,heartbeat_seconds=5,timeout_seconds=20,workload='io')
