import hashlib
import rfc8785
from uuid import UUID,uuid4
from sqlalchemy import select,func
from datetime import datetime,timedelta
from app.core.clock import utcnow
from app.core.auth import authz_guard
from app.core.errors import ApiError
from app.core.models import User,Session
from app.modules.studio import service as studio
from app.modules.studio.models import StudioSession
from app.modules.studio.scene import validate_capture_plan
from .models import RecordingProject,StudioCaptureSession,RecordingTake,RecordingStageEvent,RecordingReview,RecordingRenderVersion

def stable_hash(value):return hashlib.sha256(rfc8785.dumps(value)).hexdigest()
def deny():raise ApiError(404,'recording_not_found','Запись не найдена')
async def authorize(db,p,project):
    await authz_guard(db,p)
    if project.foundation_id!=p.foundation_id or not p.user_id or project.owner_user_id!=p.user_id or not p.has_permission('recordings.manage'):deny()
    return project
async def project(db,p,id,lock=False):
    await authz_guard(db,p)
    query=select(RecordingProject).where(RecordingProject.id==id,RecordingProject.foundation_id==p.foundation_id)
    row=await db.scalar(query.with_for_update() if lock else query)
    if row is None:deny()
    return await authorize(db,p,row)
async def target(db,p,id):
    if id is None:return
    from app.modules.learning.models import Lesson
    lesson=await db.scalar(select(Lesson).where(Lesson.id==id,Lesson.foundation_id==p.foundation_id))
    if lesson is None or not p.has_permission('learning.write'):raise ApiError(403,'lesson_target_unavailable','Выберите доступный урок')
async def resource_authorizer(db,p,id,need_host=False):
    row=await project(db,p,id)
    if row.state=='archived':deny()
    return studio.ResourceContext(row.foundation_id,row.id,'lesson_recording_project',row.owner_user_id,row.title,row.recording_policy_id,False,True)
async def take(db,p,id,lock=False):
    row=await db.get(RecordingTake,id)
    if row is None:deny()
    owner=await project(db,p,row.project_id,lock)
    if lock:row=await db.scalar(select(RecordingTake).where(RecordingTake.id==id).with_for_update())
    return row,owner

def capabilities():
    from .capture import CaptureSettings
    available=CaptureSettings.configured() is not None
    return {'capture_available':available,'capture_reason':'Захват готов' if available else 'Захват медиа не настроен','private_renderer_available':True,'raw_fallback':'forbidden'}
async def project_view(db,row):
    capture=await db.scalar(select(StudioCaptureSession).where(StudioCaptureSession.project_id==row.id).order_by(StudioCaptureSession.generation.desc()).limit(1))
    takes=(await db.scalars(select(RecordingTake).where(RecordingTake.project_id==row.id).order_by(RecordingTake.number.desc()).limit(51))).all()
    return {k:getattr(row,k) for k in ('id','owner_user_id','title','mode','target_lesson_id','state','privacy_state','version')}|{'studio_session_id':capture.studio_session_id if capture else None,'takes':[t.id for t in takes[:50]],'takes_next_cursor':takes[49].number if len(takes)>50 else None,'capabilities':capabilities()}
def readiness_current(row,now=None):
    if row.readiness_state!='ready' or not row.readiness or row.readiness.get('renderer_state_version')!=row.renderer_state_version or row.readiness.get('projection_hash')!=row.projection_hash:return False
    try:expiry=datetime.fromisoformat(row.readiness.get('valid_until',''))
    except (ValueError,TypeError):return False
    return expiry>(now or utcnow())
def take_view(row):
    value={k:getattr(row,k) for k in ('id','project_id','number','generation','state','version','renderer_state_version','projection_hash','readiness_state','capture_job_id','capture_phase','started_at','stopped_at','error_code')}
    if value['readiness_state']=='ready' and not readiness_current(row):value['readiness_state']='expired'
    return value
async def prepare(db,p,row):
    if row.state=='archived':raise ApiError(409,'recording_archived','Проект закрыт')
    session,_=await studio.create_session(db,p,'lesson_recording_project',row.id,resource_authorizer=resource_authorizer)
    capture=await db.scalar(select(StudioCaptureSession).where(StudioCaptureSession.studio_session_id==session.id))
    if capture is None:
        capture=StudioCaptureSession(project_id=row.id,studio_session_id=session.id,host_auth_session_id=p.session_id,generation=session.generation)
        db.add(capture)
    else:capture.host_auth_session_id=p.session_id
    row.state='prepared';row.version+=1
    await db.flush()
    return capture,session
async def bind_authorizer(db,p,session,take_id):
    row,owner=await take(db,p,take_id)
    capture=await db.get(StudioCaptureSession,row.capture_session_id)
    if capture.studio_session_id!=session.id or row.generation!=session.generation or owner.id!=session.resource_id:deny()
async def create_take(db,p,owner,expected_scene_revision):
    capture=await db.scalar(select(StudioCaptureSession).where(StudioCaptureSession.project_id==owner.id).order_by(StudioCaptureSession.generation.desc()).limit(1))
    if capture is None:raise ApiError(409,'recording_not_prepared','Сначала подготовьте студию')
    if await db.scalar(select(RecordingTake.id).where(RecordingTake.project_id==owner.id,RecordingTake.state.in_(('created','starting','capturing','stopping')))):
        raise ApiError(409,'recording_take_active','Завершите или отмените текущий дубль')
    session=await db.get(StudioSession,capture.studio_session_id)
    if session.scene_revision!=expected_scene_revision:raise ApiError(409,'scene_revision_conflict','Кадр изменился',current_version=session.scene_revision)
    number=(await db.scalar(select(func.max(RecordingTake.number)).where(RecordingTake.project_id==owner.id)) or 0)+1
    row=RecordingTake(id=uuid4(),project_id=owner.id,capture_session_id=capture.id,number=number,generation=session.generation,projection={},projection_hash='0'*64)
    db.add(row);await db.flush()
    session=await studio.bind_capture_take(db,p,session.id,row.id,expected_scene_revision,take_authorizer=bind_authorizer)
    capture.host_auth_session_id=p.session_id
    await snapshot(db,owner,row,session,privacy_state='unknown',allowed_tracks=[])
    owner.state='has_takes';owner.version+=1
    await db.flush()
    return row
async def snapshot(db,owner,row,session,*,privacy_state,allowed_tracks,media_time_ms=None):
    """Internal policy adapter only. Any pixel, asset or allowlist change increments the fence."""
    plan=validate_capture_plan(dict(schema_version=1,foundation_id=str(owner.foundation_id),resource_id=str(owner.id),session_id=str(session.id),take_id=str(row.id),generation=row.generation,scene_revision=session.scene_revision,render_profile_version='opora-stage/1',recording_policy_id=str(owner.recording_policy_id),privacy_state=privacy_state,raw_fallback='forbidden',allowed_tracks=allowed_tracks))
    projection={'scene':session.scene,'capture_plan':plan,'resolved_assets':[session.scene['content_asset']] if session.scene['content_asset'] else []}
    digest=stable_hash(projection)
    if row.projection_hash!=digest:
        previous=row.projection.get('capture_plan',{})
        transition=bool(row.state=='capturing' and readiness_current(row) and privacy_state=='approved' and previous.get('privacy_state')=='approved' and previous.get('allowed_tracks')==allowed_tracks and previous.get('recording_policy_id')==plan['recording_policy_id'] and previous.get('scene_revision')!=plan['scene_revision'])
        old_version,old_hash=row.renderer_state_version,row.projection_hash
        row.renderer_state_version=(row.renderer_state_version or 0)+1
        row.projection=projection;row.projection_hash=digest;row.readiness_state='waiting';row.readiness=None
        if row.capture_checkpoint is not None:
            row.capture_checkpoint={key:value for key,value in row.capture_checkpoint.items() if key!='scene_transition'}
            if transition:row.capture_checkpoint={**row.capture_checkpoint,'scene_transition':{'from_renderer_state_version':old_version,'from_projection_hash':old_hash,'expires_at':(utcnow()+timedelta(seconds=5)).isoformat(),'to_renderer_state_version':row.renderer_state_version}}
        sequence=(await db.scalar(select(func.max(RecordingStageEvent.sequence)).where(RecordingStageEvent.take_id==row.id)) or 0)+1
        db.add(RecordingStageEvent(take_id=row.id,sequence=sequence,renderer_state_version=row.renderer_state_version,projection_hash=digest,projection=projection,media_time_ms=media_time_ms))
    await db.flush()
    return row
async def render_view(db,row):
    review=await db.scalar(select(RecordingReview).where(RecordingReview.render_id==row.id).order_by(RecordingReview.created_at.desc(),RecordingReview.id.desc()).limit(1))
    approved=bool(review and review.decision=='approved' and review.render_hash==row.render_hash and review.content_hash==row.content_hash)
    return {k:getattr(row,k) for k in ('id','project_id','take_id','generation','state','version','asset_id','render_hash','content_hash','duration_ms','quality','error_code')}|{'approval_state':'approved' if approved else 'rejected' if review and review.decision=='rejected' else 'pending'}

studio.register_resource_authorizer('lesson_recording_project',resource_authorizer)

def scene_transition(row):
    value=(row.capture_checkpoint or {}).get('scene_transition')
    if not value or value.get('to_renderer_state_version')!=row.renderer_state_version:return None
    try:active=datetime.fromisoformat(value['expires_at'])>utcnow()
    except (ValueError,TypeError,KeyError):return None
    return {key:value[key] for key in ('from_renderer_state_version','from_projection_hash','expires_at')} if active else None
def capture_ready(row):
    if readiness_current(row):return True
    transition=scene_transition(row)
    if not transition:return False
    reasons=(row.readiness or {}).get('reasons',[])
    return row.readiness_state=='waiting' or (row.readiness_state=='blocked' and set(reasons)<=set(['visual_frame_unready']))
