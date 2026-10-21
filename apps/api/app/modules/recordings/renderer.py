"""Header-only purpose credentials; no cookie or query authentication on this surface."""
import secrets
from datetime import timedelta
from uuid import UUID
from fastapi import APIRouter,Depends,Header,Query,Response,Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import resolve_principal,authz_guard
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.models import Session,MediaAsset
from app.integrations.rtc.livekit import RtcSettings,RevocationPolicy,renderer_token
from app.modules.assets.service import asset_content
from app.modules.studio.models import StudioSession
from . import service
from .models import RecordingRendererGrant,RecordingTake,RecordingProject,StudioCaptureSession
from .schemas import RendererBootstrapView,RendererStateView,RendererReadinessInput,RendererReadinessView
router=APIRouter(prefix='/api/v1/recording-renderer',tags=['private-renderer'])

def rejected():raise ApiError(401,'renderer_grant_invalid','Доступ к записи недействителен')
async def issue_renderer_ticket(db,take,*,context):
    """Trusted orchestration only: fence the leased capture job before minting a one-shot ticket."""
    await context.fence(db)
    owner=await db.get(RecordingProject,take.project_id)
    if context.foundation_id!=owner.foundation_id or context.payload.get('take_id')!=str(take.id) or take.state not in ('created','starting'):rejected()
    raw=secrets.token_urlsafe(48)
    db.add(RecordingRendererGrant(take_id=take.id,generation=take.generation,token_hash=digest(raw),purpose='bootstrap',expires_at=utcnow()+timedelta(minutes=3)))
    await db.flush()
    return raw

async def renderer_scope(request:Request,authorization:str|None=Header(None),db:AsyncSession=Depends(get_db)):
    if any(key in request.query_params for key in ('ticket','token','access_token')):rejected()
    if not authorization or not authorization.startswith('Bearer ') or not 40<=len(authorization)<=200:rejected()
    raw=authorization[7:]
    grant=await db.scalar(select(RecordingRendererGrant).where(RecordingRendererGrant.token_hash==digest(raw)))
    if grant is None:rejected()
    take=await db.get(RecordingTake,grant.take_id)
    capture=await db.get(StudioCaptureSession,take.capture_session_id) if take else None
    host_session=await db.get(Session,capture.host_auth_session_id,populate_existing=True) if capture else None
    if host_session is None or host_session.revoked_at or host_session.expires_at<=utcnow():rejected()
    try:principal=await resolve_principal(db,host_session)
    except ApiError:rejected()
    await authz_guard(db,principal)
    owner=await service.project(db,principal,take.project_id,lock=True)
    take=await db.scalar(select(RecordingTake).where(RecordingTake.id==take.id).with_for_update())
    grant=await db.scalar(select(RecordingRendererGrant).where(RecordingRendererGrant.id==grant.id).with_for_update())
    if grant.revoked_at or grant.expires_at<=utcnow() or grant.generation!=take.generation or (grant.purpose=='bootstrap' and grant.consumed_at) or owner.state=='archived' or take.state in ('failed','discarded','captured') or owner.owner_user_id!=principal.user_id:rejected()
    session=await db.get(StudioSession,capture.studio_session_id,populate_existing=True)
    if not session or session.generation!=take.generation or session.scene.get('take_id')!=str(take.id) or session.recording_policy_id!=owner.recording_policy_id or session.state in ('closing','closed','failed'):rejected()
    plan=take.projection.get('capture_plan',{})
    # Studio scene changes invalidate readiness until the authoritative policy snapshot is refreshed.
    if session.scene_revision!=plan.get('scene_revision'):
        await service.snapshot(db,owner,take,session,privacy_state='unknown',allowed_tracks=[])
    return db,grant,take,owner,session

async def state_view(db,grant,take,owner,session,*,with_provider=False):
    value={'foundation_id':owner.foundation_id,'project_id':owner.id,'take_id':take.id,'session_id':session.id,'generation':take.generation,'renderer_state_version':take.renderer_state_version,'projection_hash':take.projection_hash,**take.projection,'provider_grant':None,'invalidated':take.projection['capture_plan']['privacy_state']!='approved'}
    settings=RtcSettings.from_env()
    if with_provider and settings.capabilities().configured and not value['invalidated']:
        hidden_identity='opora-renderer-'+grant.id.hex
        token=renderer_token(settings,room=session.room_name,participant_identity=hidden_identity,capture_grant_id=grant.id,take_id=take.id,generation=take.generation,policy=RevocationPolicy(session.require_strict_revocation))
        value['provider_grant']={'url':(settings.public_url or settings.url).replace('https://','wss://',1).replace('http://','ws://',1),'token':token,'identity':hidden_identity,'session_id':session.id,'generation':take.generation,'expires_in':min(60,settings.join_ttl_seconds),'provider':'livekit'}
    return value

@router.post('/bootstrap',operation_id='recording_renderer_bootstrap',response_model=RendererBootstrapView)
async def bootstrap(response:Response,scope=Depends(renderer_scope)):
    db,grant,take,owner,session=scope
    if grant.purpose!='bootstrap':rejected()
    grant.consumed_at=utcnow()
    raw=secrets.token_urlsafe(48)
    access=RecordingRendererGrant(take_id=take.id,generation=take.generation,token_hash=digest(raw),purpose='renderer',expires_at=utcnow()+timedelta(hours=2))
    db.add(access);await db.flush()
    value=await state_view(db,access,take,owner,session,with_provider=True)
    value.update(access_token=raw,expires_at=access.expires_at)
    response.headers['Cache-Control']='no-store';response.headers['Referrer-Policy']='no-referrer'
    await db.commit()
    return value

async def active_renderer(scope=Depends(renderer_scope)):
    if scope[1].purpose!='renderer':rejected()
    return scope

@router.get('/state',operation_id='recording_renderer_state',response_model=RendererStateView)
async def state(response:Response,after_revision:int|None=Query(None,ge=0),scope=Depends(active_renderer)):
    db,grant,take,owner,session=scope
    value=await state_view(db,grant,take,owner,session)
    response.headers['Cache-Control']='no-store'
    await db.commit()
    return value

@router.post('/provider-grant',operation_id='recording_renderer_provider_grant',response_model=RendererStateView)
async def provider_grant(response:Response,scope=Depends(active_renderer)):
    db,grant,take,owner,session=scope
    value=await state_view(db,grant,take,owner,session,with_provider=True)
    if value['provider_grant'] is None:raise ApiError(503,'renderer_provider_unavailable','Медиадоступ к согласованной записи пока недоступен')
    response.headers['Cache-Control']='no-store'
    await db.commit();return value

@router.post('/readiness',operation_id='recording_renderer_readiness',response_model=RendererReadinessView)
async def readiness(body:RendererReadinessInput,scope=Depends(active_renderer)):
    db,grant,take,owner,session=scope
    if body.renderer_state_version!=take.renderer_state_version or body.projection_hash!=take.projection_hash:
        raise ApiError(409,'renderer_state_conflict','Композиция записи изменилась',current_version=take.renderer_state_version)
    reasons=[]
    if not body.visual_ready:reasons.append('visual_frame_unready')
    plan=take.projection['capture_plan']
    if plan['privacy_state']!='approved':reasons.append('privacy_not_approved')
    if (body.viewport_width,body.viewport_height,body.device_pixel_ratio)!=(1920,1080,1):reasons.append('viewport_mismatch')
    expected={(x['identity'],x['track_id'],x['source'],x['kind']):x for x in plan['allowed_tracks']}
    seen={}
    for track in body.observed_tracks:
        key=(track.identity,track.track_id,track.source,track.kind)
        if key in seen:reasons.append('duplicate_track')
        seen[key]=track
        if key not in expected:reasons.append('unknown_track')
        if track.privacy_state!='approved':reasons.append('track_privacy_unknown')
    for key,track in expected.items():
        if track['required'] and (key not in seen or seen[key].state!='ready'):reasons.append('required_track_unavailable')
    wanted={str(x['asset_id']):x['sha256'] for x in take.projection['resolved_assets']}
    proofs={str(x.asset_id):x.sha256 for x in body.asset_proofs}
    if len(proofs)!=len(body.asset_proofs) or proofs!=wanted:reasons.append('asset_checksum_mismatch')
    valid_until=utcnow()+timedelta(seconds=10) if not reasons else None
    take.readiness_state='ready' if not reasons else 'blocked'
    take.readiness=body.model_dump(mode='json')|{'reasons':sorted(set(reasons)),'grant_id':str(grant.id),'received_at':utcnow().isoformat(),'valid_until':valid_until.isoformat() if valid_until else None}
    value={'ready':not reasons,'reasons':sorted(set(reasons)),'renderer_state_version':take.renderer_state_version,'projection_hash':take.projection_hash,'capture_state':take.state,'valid_until':valid_until}
    await db.commit()
    return value

@router.get('/assets/{asset_id}',operation_id='recording_renderer_asset')
async def asset(asset_id:UUID,scope=Depends(active_renderer)):
    db,grant,take,owner,session=scope
    if take.projection['capture_plan']['privacy_state']!='approved':raise ApiError(403,'renderer_policy_unapproved','Политика записи ещё не согласована')
    descriptor=next((x for x in take.projection['resolved_assets'] if x['asset_id']==str(asset_id)),None)
    if descriptor is None:raise ApiError(404,'renderer_asset_not_found','Файл недоступен для этого кадра')
    row=await db.scalar(select(MediaAsset).where(MediaAsset.id==asset_id,MediaAsset.foundation_id==owner.foundation_id,MediaAsset.state=='ready',MediaAsset.checksum==descriptor['sha256']))
    if row is None:raise ApiError(404,'renderer_asset_not_found','Файл недоступен для этого кадра')
    result=await asset_content(db,row)
    result.headers['Cache-Control']='no-store'
    await db.commit()
    return result

async def internal_participant_authorizer(db,studio_session,participant):
    import json
    try:
        metadata=json.loads(participant.get('metadata') or '{}')
        if metadata.get('role')!='recording_renderer':return False
        grant_id=UUID(metadata.get('capture_grant_id',''));take_id=UUID(metadata.get('take_id',''))
    except (ValueError,TypeError):return False
    grant=await db.get(RecordingRendererGrant,grant_id)
    take=await db.get(RecordingTake,take_id)
    capture=await db.get(StudioCaptureSession,take.capture_session_id) if take else None
    owner=await db.get(RecordingProject,take.project_id) if take else None
    host=await db.get(Session,capture.host_auth_session_id,populate_existing=True) if capture else None
    if not grant or grant.purpose!='renderer' or grant.take_id!=take_id or grant.revoked_at or grant.expires_at<=utcnow() or not take or take.state in ('failed','discarded','captured') or not capture or capture.studio_session_id!=studio_session.id or take.generation!=studio_session.generation or metadata.get('generation')!=take.generation or participant.get('identity')!='opora-renderer-'+grant.id.hex or not host or host.revoked_at or host.expires_at<=utcnow() or not owner or owner.owner_user_id!=host.user_id or owner.foundation_id!=studio_session.foundation_id or owner.state=='archived':return False
    try:principal=await resolve_principal(db,host)
    except ApiError:return False
    return principal.has_permission('recordings.manage')

async def capture_close_guard(db,session):
    row=await db.scalar(select(RecordingTake.id).join(StudioCaptureSession,StudioCaptureSession.id==RecordingTake.capture_session_id).where(StudioCaptureSession.studio_session_id==session.id,RecordingTake.state.in_(('starting','capturing','stopping'))).limit(1))
    return row is None

from app.modules.studio.service import register_internal_participant_authorizer,register_close_guard
register_internal_participant_authorizer(internal_participant_authorizer)
register_close_guard(capture_close_guard)
