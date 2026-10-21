from dataclasses import asdict,dataclass
from datetime import datetime,timezone
import time
from typing import Awaitable,Callable
from uuid import UUID,uuid4
from sqlalchemy import select,func,text
from app.core.auth import Principal
from app.core.errors import ApiError
from app.core.models import User,MediaAsset
from app.integrations.rtc.livekit import RtcSettings,RevocationPolicy,identity,room_name,LiveKitAdapter,join_token
from .models import Webinar,WebinarEnrollment,StudioSession,StudioSceneEvent,StudioBoardGrant,SlideDeck,SlideDeckVersion,SlidePage,StudioBoardSnapshot
from .scene import validate_scene

@dataclass(frozen=True)
class ResourceContext:
    foundation_id:UUID
    resource_id:UUID
    resource_kind:str
    host_user_id:UUID
    title:str
    recording_policy_id:UUID
    require_strict_revocation:bool
    can_host:bool

ResourceAuthorizer=Callable[...,Awaitable[ResourceContext]]
_authorizers:dict[str,ResourceAuthorizer]={}
def register_resource_authorizer(kind:str,authorizer:ResourceAuthorizer):
    if kind=='live_event':raise ValueError('webinar_authorizer_is_builtin')
    _authorizers[kind]=authorizer

def deny():raise ApiError(404,'studio_resource_not_found','Занятие не найдено.')
def version(row,expected):
    if row.version!=expected:raise ApiError(409,'version_conflict','Данные изменились. Обновите страницу.',current_version=row.version)
async def webinar_context(db,p,id,need_host=False):
    row=await db.scalar(select(Webinar).where(Webinar.id==id,Webinar.foundation_id==p.foundation_id))
    if not row:deny()
    can_host=p.user_id==row.host_user_id and (p.has_permission('studio.manage') or p.has_permission('studio.host','webinar',row.id))
    if need_host and not can_host:deny()
    if not can_host:
        if row.state!='published' or p.user_id is None:deny()
        enrollment=await db.scalar(select(WebinarEnrollment).where(WebinarEnrollment.webinar_id==id,WebinarEnrollment.user_id==p.user_id,WebinarEnrollment.foundation_id==p.foundation_id,WebinarEnrollment.state=='enrolled'))
        if not enrollment:deny()
    return ResourceContext(row.foundation_id,row.id,'live_event',row.host_user_id,row.title,row.recording_policy_id,row.require_strict_revocation,can_host)
async def authorize_resource(db,p,kind,id,need_host=False):
    if not p.user_id:raise ApiError(401,'studio_login_required','Войдите в аккаунт перед подключением.')
    if kind=='live_event':return await webinar_context(db,p,id,need_host)
    validator=_authorizers.get(kind)
    if not validator:raise ApiError(503,'recording_resource_unavailable','Запись уроков ещё не подключена.')
    context=await validator(db,p,id,need_host=need_host)
    if context.foundation_id!=p.foundation_id or context.resource_id!=id or context.resource_kind!=kind or (need_host and not context.can_host):deny()
    return context
async def session(db,p,id,need_host=False,lock=False):
    query=select(StudioSession).where(StudioSession.id==id,StudioSession.foundation_id==p.foundation_id)
    row=await db.scalar(query.with_for_update() if lock else query)
    if not row:deny()
    context=await authorize_resource(db,p,row.resource_kind,row.resource_id,need_host)
    if context.host_user_id!=row.host_user_id:deny()
    if not context.can_host and row.state!='live':raise ApiError(409,'studio_not_live','Ведущий ещё не открыл комнату.')
    return row,context
async def resource_lock(db,kind,id):
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'studio:{kind}:{id}'})
async def create_session(db,p,resource_kind,resource_id,*,resource_authorizer=None):
    context=await (resource_authorizer(db,p,resource_id,need_host=True) if resource_authorizer else authorize_resource(db,p,resource_kind,resource_id,True))
    if context.foundation_id!=p.foundation_id or context.resource_id!=resource_id or context.resource_kind!=resource_kind or not context.can_host:deny()
    await resource_lock(db,resource_kind,resource_id)
    existing=await db.scalar(select(StudioSession).where(StudioSession.resource_kind==resource_kind,StudioSession.resource_id==resource_id,StudioSession.state.in_(['prepared','opening','live','closing'])))
    if existing:return existing,context
    generation=(await db.scalar(select(func.max(StudioSession.generation)).where(StudioSession.resource_kind==resource_kind,StudioSession.resource_id==resource_id)) or 0)+1
    host=await db.get(User,context.host_user_id)
    if not host or host.foundation_id!=p.foundation_id or host.id!=p.user_id:deny()
    id=uuid4()
    scene=validate_scene({'schema_version':1,'foundation_id':str(p.foundation_id),'resource_kind':resource_kind,'resource_id':str(resource_id),'session_id':str(id),'take_id':None,'revision':0,'render_profile_version':'opora-stage/1','content_kind':'camera','content_asset':None,'deck_version_id':None,'slide_id':None,'board_snapshot_id':None,'presenter_identity':identity(host.id),'presenter_display_name':host.display_name[:160] or 'Ведущий','presenter_camera':False,'screen_track_id':None,'content_ratio':16/9,'layout':'camera_only','presenter_size':28,'theme_id':'opora-warm','recording_policy_id':str(context.recording_policy_id)})
    row=StudioSession(id=id,foundation_id=p.foundation_id,resource_kind=resource_kind,resource_id=resource_id,host_user_id=host.id,room_name=room_name(p.foundation_id,id,generation),generation=generation,state='prepared',scene=scene,scene_revision=0,recording_policy_id=context.recording_policy_id,require_strict_revocation=context.require_strict_revocation,version=1)
    db.add(row);await db.flush()
    db.add(StudioSceneEvent(session_id=id,revision=0,scene=scene,actor_id=p.user_id));await db.flush()
    return row,context

def session_view(row,context,settings=None):
    settings=settings or RtcSettings.from_env()
    return {k:getattr(row,k) for k in ('id','resource_kind','resource_id','host_user_id','state','generation','scene','scene_revision','version')}|{'capabilities':asdict(settings.capabilities()),'can_host':context.can_host,'board_available':settings.capabilities().board_configured}
async def update_scene(db,p,row,body):
    if row.state not in ('prepared','opening','live'):raise ApiError(409,'studio_closed','Комната уже закрывается или завершена.')
    if row.scene_revision!=body.expected_revision:raise ApiError(409,'scene_revision_conflict','Ведущий уже изменил кадр. Обновляем сцену.',current_version=row.scene_revision)
    scene=validate_scene(body.scene)
    for field in ('foundation_id','resource_kind','resource_id','session_id','take_id','presenter_identity','recording_policy_id','render_profile_version'):
        if scene[field]!=row.scene[field]:raise ApiError(422,'scene_scope_mismatch','Кадр относится к другой комнате или записи.')
    if scene['content_kind']=='slides':
        page=await db.get(SlidePage,UUID(scene['slide_id']));deck_version=await db.get(SlideDeckVersion,page.deck_version_id) if page else None
        deck=await db.get(SlideDeck,deck_version.deck_id) if deck_version else None
        if not deck or deck.foundation_id!=p.foundation_id or deck.resource_kind!=row.resource_kind or deck.resource_id!=row.resource_id or str(deck_version.id)!=scene['deck_version_id']:deny()
        asset={'asset_id':str(page.asset_id),'sha256':page.sha256,'width':page.width,'height':page.height}
        if scene['content_asset']!=asset:raise ApiError(422,'scene_asset_mismatch','Слайд изменился. Выберите его заново.')
    elif scene['content_kind']=='board':
        snapshot=await db.get(StudioBoardSnapshot,UUID(scene['board_snapshot_id']))
        if not snapshot or snapshot.session_id!=row.id:deny()
        if scene['content_asset']!={'asset_id':str(snapshot.asset_id),'sha256':snapshot.sha256,'width':snapshot.width,'height':snapshot.height}:deny()
    elif scene['content_kind']=='screen':
        participants=await LiveKitAdapter().participants(row.room_name)
        allowed=any(part.get('identity')==row.scene['presenter_identity'] and any(track.get('sid')==scene['screen_track_id'] and track.get('source') in ('SCREEN_SHARE',3) for track in part.get('tracks',[])) for part in participants)
        if not allowed:raise ApiError(409,'screen_track_unavailable','Демонстрация экрана ещё не подтверждена сервером.')
    host=await db.get(User,row.host_user_id)
    scene['presenter_display_name']=host.display_name[:160] or 'Ведущий'
    scene['revision']=row.scene_revision+1
    row.scene=scene;row.scene_revision+=1;row.version+=1
    db.add(StudioSceneEvent(session_id=row.id,revision=row.scene_revision,scene=scene,actor_id=p.user_id));await db.flush()
    return row

async def issue_join(db,p,row,context,settings=None):
    settings=settings or RtcSettings.from_env()
    if row.state not in (('opening','live') if context.can_host else ('live',)):raise ApiError(409,'studio_not_live','Ведущий ещё не открыл комнату.')
    user=await db.get(User,p.user_id)
    token=join_token(settings,room=row.room_name,participant_identity=identity(user.id),name=user.display_name,host=context.can_host,policy=RevocationPolicy(row.require_strict_revocation),auth_session_id=p.session_id)
    return {'provider':'livekit','url':(settings.public_url or settings.url).replace('https://','wss://',1).replace('http://','ws://',1),'token':token,'identity':identity(user.id),'host_identity':identity(row.host_user_id),'role':'host' if context.can_host else 'audience','session_id':row.id,'generation':row.generation,'expires_in':settings.join_ttl_seconds,'strict_revocation':settings.capabilities().strict_token_revocation}

async def board_rights(db,p,row,context):
    if context.can_host:return True
    grant=await db.scalar(select(StudioBoardGrant).where(StudioBoardGrant.session_id==row.id,StudioBoardGrant.user_id==p.user_id))
    return bool(grant and grant.can_draw)

async def deck_context(db,p,id,need_host=False,lock=False):
    query=select(SlideDeck).where(SlideDeck.id==id,SlideDeck.foundation_id==p.foundation_id)
    row=await db.scalar(query.with_for_update() if lock else query)
    if not row:deny()
    context=await authorize_resource(db,p,row.resource_kind,row.resource_id,need_host)
    return row,context

async def deck_view(db,p,row):
    from app.modules.assets.router import view as asset_view
    deck_version=await db.scalar(select(SlideDeckVersion).where(SlideDeckVersion.deck_id==row.id).order_by(SlideDeckVersion.number.desc()))
    pages=(await db.scalars(select(SlidePage).where(SlidePage.deck_version_id==deck_version.id).order_by(SlidePage.ordinal))).all() if deck_version else []
    asset=await db.get(MediaAsset,row.source_asset_id) if row.source_asset_id else None
    from app.core.models import Job
    job=await db.get(Job,asset.processing_job_id) if asset and asset.processing_job_id else None
    terminal_failure=bool(job and job.state=='dead' and row.state not in ('ready','failed'))
    return {'id':row.id,'title':row.title,'state':'failed' if terminal_failure else 'converting' if asset and asset.state=='processing' and row.state=='uploading' else row.state,'error_code':('conversion_worker_failed' if terminal_failure else row.error_code),'version':row.version,'deck_version_id':deck_version.id if deck_version else None,'pages':[{'id':page.id,'ordinal':page.ordinal,'asset_id':page.asset_id,'sha256':page.sha256,'width':page.width,'height':page.height,'content_url':f'/api/v1/slide-pages/{page.id}/content'} for page in pages],'upload':asset_view(asset) if asset and asset.owner_user_id==p.user_id and asset.state in ('uploading','processing') else None}

_internal_participant_authorizers=[]
def register_internal_participant_authorizer(authorizer):
    if authorizer not in _internal_participant_authorizers:_internal_participant_authorizers.append(authorizer)
async def internal_participant_allowed(db,row,participant):
    for authorizer in _internal_participant_authorizers:
        if await authorizer(db,row,participant):return True
    return False

_close_guards=[]
def register_close_guard(guard):
    if guard not in _close_guards:_close_guards.append(guard)
async def assert_capture_can_close(db,row):
    if row.scene.get('take_id') and not _close_guards:raise ApiError(503,'capture_status_unavailable','Сначала подтвердите завершение записи.')
    for guard in _close_guards:
        if not await guard(db,row):raise ApiError(409,'capture_still_active','Сначала завершите запись и дождитесь подтверждения.')

async def bind_capture_take(db,p,session_id,take_id,expected_revision,*,take_authorizer):
    """P18C-only binding after its project/take locks, in the same transaction.

    A take authorizer validates project/session/generation; the browser scene API cannot bind it.
    """
    row,context=await session(db,p,session_id,True,True)
    if row.state not in ('prepared','opening','live'):raise ApiError(409,'studio_closed','Комната уже закрывается.')
    if row.scene_revision!=expected_revision:raise ApiError(409,'scene_revision_conflict','Кадр изменился.',current_version=row.scene_revision)
    await take_authorizer(db,p,row,take_id)
    scene=dict(row.scene);scene['take_id']=str(take_id);scene['revision']=row.scene_revision+1
    row.scene=validate_scene(scene);row.scene_revision+=1;row.version+=1
    db.add(StudioSceneEvent(session_id=row.id,revision=row.scene_revision,scene=row.scene,actor_id=p.user_id));await db.flush()
    return row
