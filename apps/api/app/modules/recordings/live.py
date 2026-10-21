"""Host-only recording binds the current webinar room; audience membership never grants capture."""
import json
from uuid import UUID,uuid4
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.models import Session,User
from app.integrations.rtc.livekit import identity
from app.modules.studio import service as studio
from app.modules.studio.models import Webinar,WebinarEnrollment,StudioSession
from .models import RecordingProject,StudioCaptureSession

async def active_webinar(db,p,id):
    if not p.user_id or not p.has_permission('recordings.manage'):raise ApiError(403,'permission_denied','Недостаточно прав для записи эфира')
    context=await studio.authorize_resource(db,p,'live_event',id,True)
    row=await db.scalar(select(Webinar).where(Webinar.id==id).execution_options(populate_existing=True))
    if row.host_user_id!=p.user_id or row.recording_policy_id!=context.recording_policy_id:raise ApiError(404,'recording_not_found','Запись не найдена')
    if row.state!='published':raise ApiError(409,'recording_live_event_inactive','Эфир завершён или недоступен')
    return context

async def ensure_project(db,p,id,session_id,expected_revision):
    context=await active_webinar(db,p,id)
    await studio.resource_lock(db,'live_event',id)
    session=await db.scalar(select(StudioSession).where(StudioSession.id==session_id).execution_options(populate_existing=True))
    if not session or session.foundation_id!=p.foundation_id or session.resource_kind!='live_event' or session.resource_id!=id or session.host_user_id!=p.user_id or session.recording_policy_id!=context.recording_policy_id or session.state!='live':raise ApiError(409,'recording_live_session_inactive','Запись доступна в текущем открытом эфире')
    if session.scene_revision!=expected_revision:raise ApiError(409,'scene_revision_conflict','Кадр изменился',current_version=session.scene_revision)
    capture=await db.scalar(select(StudioCaptureSession).where(StudioCaptureSession.studio_session_id==session.id))
    if capture:
        from .service import project
        return await project(db,p,capture.project_id)
    row=RecordingProject(id=uuid4(),foundation_id=p.foundation_id,owner_user_id=p.user_id,live_event_id=id,title=context.title,mode='live',recording_policy_id=context.recording_policy_id,state='prepared')
    db.add(row);await db.flush()
    db.add(StudioCaptureSession(project_id=row.id,studio_session_id=session.id,host_auth_session_id=p.session_id,generation=session.generation))
    await db.flush()
    return row

async def audience_excluded(db,session,participant):
    """Only current server-issued subscribe-only enrollment may be excluded from the recording.

    JWT metadata is immutable to the client. Provider evidence of ANY published track
    blocks this exemption even if enrollment and login remain valid.
    """
    if session.resource_kind!='live_event' or session.state!='live' or participant.get('tracks'):return False
    try:
        metadata=json.loads(participant.get('metadata',''))
        if metadata.get('role')!='audience':return False
        auth_id=UUID(metadata['auth_session_id'])
    except (ValueError,TypeError,KeyError,AttributeError):return False
    login=await db.get(Session,auth_id,populate_existing=True)
    if not login or login.foundation_id!=session.foundation_id or not login.user_id or login.revoked_at or login.expires_at<=utcnow() or participant.get('identity')!=identity(login.user_id):return False
    user=await db.get(User,login.user_id,populate_existing=True)
    webinar=await db.get(Webinar,session.resource_id,populate_existing=True)
    if not user or user.foundation_id!=session.foundation_id or user.account_state!='active' or not webinar or webinar.state!='published' or webinar.host_user_id!=session.host_user_id:return False
    return bool(await db.scalar(select(WebinarEnrollment.id).where(WebinarEnrollment.foundation_id==session.foundation_id,WebinarEnrollment.webinar_id==session.resource_id,WebinarEnrollment.user_id==user.id,WebinarEnrollment.state=='enrolled')))
