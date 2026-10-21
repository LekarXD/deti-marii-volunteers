from datetime import datetime,timezone
from dataclasses import asdict
from uuid import UUID,uuid4
import time
from fastapi import APIRouter,Depends,Header,Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal,authz_guard,resolve_principal
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.audit import audit
from app.core.idempotency import begin_command,finish_command
from app.core.models import Session,User
from app.core.rate_limit import rate_limit
from app.worker.queue import enqueue_job
from app.integrations.rtc.livekit import RtcSettings,LiveKitAdapter,RevocationPolicy,ProviderError,identity
from .models import Webinar,WebinarEnrollment,StudioSession,StudioBoardGrant
from .schemas import WebinarInput,WebinarView,WebinarUpdate,StudioVersionCommand,StudioSessionCreate,StudioSessionView,StudioSceneCommand,StudioJoinView,StudioEnrollmentView,StudioBoardPass,StudioBoardGrantInput,SlideDeckView,SlideUploadInput,StudioBoardSnapshotInput,StudioParticipantView
from . import service as s
router=APIRouter(prefix='/api/v1',tags=['studio'])

def require_manage(p):
    if not p.has_permission('studio.manage'):raise ApiError(403,'permission_denied','Недостаточно прав для управления занятиями.')
async def execute(db,p,operation,key,payload,authorize,action):
    try:
        await authz_guard(db,p)
        scope=await authorize()
        receipt=await begin_command(db,p,operation,key,payload)
        if receipt is not None:await db.commit();return receipt
        result=jsonable_encoder(await action(scope))
        await finish_command(db,p,operation,key,result);await db.commit();return result
    except IntegrityError as exc:
        await db.rollback()
        if getattr(exc.orig,'sqlstate',None)=='23505':raise ApiError(409,'studio_conflict','Комната или запись уже изменилась. Обновите данные.') from None
        raise
    except ProviderError as exc:
        await db.rollback();raise ApiError(503,'rtc_provider_unavailable','Не удалось подтвердить действие на сервере видеосвязи. Повторите попытку.',retryable=True) from None
    except BaseException:await db.rollback();raise
async def manage_scope(p):require_manage(p)
async def webinar_view(db,p,row):
    enrollment=await db.scalar(select(WebinarEnrollment).where(WebinarEnrollment.webinar_id==row.id,WebinarEnrollment.user_id==p.user_id)) if p.user_id else None
    current=await db.scalar(select(StudioSession).where(StudioSession.resource_kind=='live_event',StudioSession.resource_id==row.id,StudioSession.state.in_(['prepared','opening','live','closing'])))
    return WebinarView.model_validate(row).model_dump()|{'enrollment_state':enrollment.state if enrollment else None,'enrollment_version':enrollment.version if enrollment else None,'can_host':p.user_id==row.host_user_id and (p.has_permission('studio.manage') or p.has_permission('studio.host','webinar',row.id)),'session_id':current.id if current else None}

@router.get('/webinars',response_model=list[WebinarView])
async def webinars(db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    query=select(Webinar).where(Webinar.foundation_id==p.foundation_id)
    if not p.has_permission('studio.manage'):query=query.where(Webinar.state=='published')
    rows=(await db.scalars(query.order_by(Webinar.starts_at))).all()
    return [await webinar_view(db,p,row) for row in rows]

@router.post('/webinars',response_model=WebinarView,status_code=201)
async def create_webinar(body:WebinarInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def action(_):
        row=Webinar(foundation_id=p.foundation_id,host_user_id=p.user_id,**body.model_dump(),state='draft',version=1)
        db.add(row);await db.flush();audit(db,p,'studio.webinar.create','webinar',row.id,('title','starts_at'))
        return await webinar_view(db,p,row)
    return await execute(db,p,'studio.webinar.create',key,body.model_dump(mode='json'),lambda:manage_scope(p),action)

async def hosted_webinar(db,p,id,lock=False):
    row=await db.scalar(select(Webinar).where(Webinar.id==id,Webinar.foundation_id==p.foundation_id).with_for_update() if lock else select(Webinar).where(Webinar.id==id,Webinar.foundation_id==p.foundation_id))
    if not row:s.deny()
    await s.authorize_resource(db,p,'live_event',id,True)
    return row

@router.patch('/webinars/{id}',response_model=WebinarView)
async def edit_webinar(id:UUID,body:WebinarUpdate,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def action(row):
        s.version(row,body.expected_version)
        if row.state in ('cancelled','ended'):raise ApiError(409,'webinar_closed','Занятие завершено или отменено.')
        for name,value in body.model_dump(exclude={'expected_version'}).items():setattr(row,name,value)
        row.version+=1;audit(db,p,'studio.webinar.update','webinar',id,('title','starts_at','require_strict_revocation'))
        return await webinar_view(db,p,row)
    return await execute(db,p,'studio.webinar.update:'+str(id),key,body.model_dump(mode='json'),lambda:hosted_webinar(db,p,id,True),action)

@router.post('/webinars/{id}/publish',response_model=WebinarView)
async def publish_webinar(id:UUID,body:StudioVersionCommand,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def action(row):
        s.version(row,body.expected_version)
        if row.state not in ('draft','published'):raise ApiError(409,'webinar_closed','Занятие завершено или отменено.')
        row.state='published';row.version+=1;audit(db,p,'studio.webinar.publish','webinar',id,('state',));await db.flush()
        return await webinar_view(db,p,row)
    return await execute(db,p,'studio.webinar.publish:'+str(id),key,body.model_dump(mode='json'),lambda:hosted_webinar(db,p,id,True),action)

@router.post('/webinars/{id}/enroll',response_model=StudioEnrollmentView)
async def enroll(id:UUID,body:StudioVersionCommand|None=None,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def authorize():
        if not p.user_id:raise ApiError(401,'studio_login_required','Войдите в аккаунт для участия.')
        row=await db.scalar(select(Webinar).where(Webinar.id==id,Webinar.foundation_id==p.foundation_id,Webinar.state=='published'))
        if not row:s.deny()
        return row
    async def action(_):
        row=await db.scalar(select(WebinarEnrollment).where(WebinarEnrollment.webinar_id==id,WebinarEnrollment.user_id==p.user_id).with_for_update())
        if row is None:row=WebinarEnrollment(foundation_id=p.foundation_id,webinar_id=id,user_id=p.user_id,state='enrolled',version=1);db.add(row)
        elif row.state=='revoked':raise ApiError(403,'webinar_enrollment_revoked','Доступ отозван координатором.')
        elif row.state!='enrolled':
            if not body:raise ApiError(428,'version_required','Обновите состояние записи.')
            s.version(row,body.expected_version);row.state='enrolled';row.version+=1
        await db.flush();audit(db,p,'studio.enroll','webinar',id,('enrollment',));return {'webinar_id':id,'state':row.state,'version':row.version}
    return await execute(db,p,'studio.enroll:'+str(id),key,body.model_dump(mode='json') if body else {},authorize,action)

@router.post('/webinars/{id}/withdraw',response_model=StudioEnrollmentView)
async def withdraw(id:UUID,body:StudioVersionCommand,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def authorize():return await s.authorize_resource(db,p,'live_event',id)
    async def action(_):
        row=await db.scalar(select(WebinarEnrollment).where(WebinarEnrollment.webinar_id==id,WebinarEnrollment.user_id==p.user_id).with_for_update())
        if not row:s.deny()
        s.version(row,body.expected_version);row.state='withdrawn';row.version+=1
        enqueue_job(db,p.foundation_id,'studio.revoke',{'webinar_id':str(id),'user_id':str(p.user_id),'enrollment_version':row.version})
        audit(db,p,'studio.withdraw','webinar',id,('enrollment',));await db.flush()
        return {'webinar_id':id,'state':row.state,'version':row.version}
    return await execute(db,p,'studio.withdraw:'+str(id),key,body.model_dump(mode='json'),authorize,action)

@router.post('/webinars/{id}/enrollments/{user_id}/revoke',response_model=StudioEnrollmentView)
async def revoke(id:UUID,user_id:UUID,body:StudioVersionCommand,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def action(_):
        row=await db.scalar(select(WebinarEnrollment).where(WebinarEnrollment.webinar_id==id,WebinarEnrollment.user_id==user_id).with_for_update())
        if not row:s.deny()
        s.version(row,body.expected_version);row.state='revoked';row.version+=1
        enqueue_job(db,p.foundation_id,'studio.revoke',{'webinar_id':str(id),'user_id':str(user_id),'enrollment_version':row.version})
        audit(db,p,'studio.enrollment.revoke','webinar',id,('enrollment',));await db.flush()
        return {'webinar_id':id,'state':row.state,'version':row.version}
    return await execute(db,p,'studio.enrollment.revoke:'+str(id)+':'+str(user_id),key,body.model_dump(mode='json'),lambda:hosted_webinar(db,p,id,True),action)

@router.post('/studio-sessions',response_model=StudioSessionView,status_code=201)
async def prepare(body:StudioSessionCreate,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def action(_):
        row,context=await s.create_session(db,p,body.resource_kind,body.resource_id)
        audit(db,p,'studio.session.prepare','studio_session',row.id,('state',));return s.session_view(row,context)
    return await execute(db,p,'studio.session.prepare',key,body.model_dump(mode='json'),lambda:s.authorize_resource(db,p,body.resource_kind,body.resource_id,True),action)

@router.get('/studio-sessions/{id}',response_model=StudioSessionView)
async def get_session(id:UUID,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    row,context=await s.session(db,p,id);return s.session_view(row,context)

@router.get('/studio-sessions/{id}/scene')
async def get_scene(id:UUID,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    row,_=await s.session(db,p,id);return row.scene

@router.patch('/studio-sessions/{id}/scene',response_model=StudioSessionView)
async def patch_scene(id:UUID,body:StudioSceneCommand,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def action(scope):
        row,context=scope;await s.update_scene(db,p,row,body);audit(db,p,'studio.scene.patch','studio_session',id,('scene','scene_revision'));return s.session_view(row,context)
    return await execute(db,p,'studio.scene.patch:'+str(id),key,body.model_dump(mode='json'),lambda:s.session(db,p,id,True,True),action)

@router.post('/studio-sessions/{id}/start',response_model=StudioSessionView)
async def start(id:UUID,body:StudioVersionCommand,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def action(scope):
        row,context=scope;s.version(row,body.expected_version)
        if row.state not in ('prepared','opening'):raise ApiError(409,'studio_already_started','Комната уже открыта или завершена.')
        adapter=LiveKitAdapter();adapter.settings.assert_policy(RevocationPolicy(row.require_strict_revocation))
        row.provider_sid=await adapter.create_room(row.room_name);row.state='opening';row.version+=1
        audit(db,p,'studio.session.start','studio_session',id,('state',));return s.session_view(row,context)
    return await execute(db,p,'studio.session.start:'+str(id),key,body.model_dump(mode='json'),lambda:s.session(db,p,id,True,True),action)

@router.post('/studio-sessions/{id}/join-token',response_model=StudioJoinView)
async def join(id:UUID,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    await authz_guard(db,p);row,context=await s.session(db,p,id)
    await rate_limit(db,p.actor_id,'studio.join',limit=20,seconds=60)
    result=await s.issue_join(db,p,row,context);audit(db,p,'studio.join_token','studio_session',id,());await db.commit();return result

@router.post('/studio-sessions/{id}/ready',response_model=StudioSessionView)
async def ready(id:UUID,body:StudioVersionCommand,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def action(scope):
        row,context=scope;s.version(row,body.expected_version)
        if row.state!='opening':raise ApiError(409,'studio_not_opening','Обновите состояние комнаты.')
        participants=await LiveKitAdapter().participants(row.room_name)
        if not any(part.get('identity')==identity(row.host_user_id) for part in participants):raise ApiError(409,'host_not_connected','Подключение ведущего ещё не подтверждено.')
        row.state='live';row.opened_at=datetime.now(timezone.utc);row.version+=1
        audit(db,p,'studio.session.ready','studio_session',id,('state',));return s.session_view(row,context)
    return await execute(db,p,'studio.session.ready:'+str(id),key,body.model_dump(mode='json'),lambda:s.session(db,p,id,True,True),action)

@router.post('/studio-sessions/{id}/close',response_model=StudioSessionView)
async def close(id:UUID,body:StudioVersionCommand,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def action(scope):
        row,context=scope;s.version(row,body.expected_version)
        if row.state=='closed':return s.session_view(row,context)
        await s.assert_capture_can_close(db,row)
        if row.state=='prepared':row.state='closed';row.closed_at=datetime.now(timezone.utc)
        else:
            row.state='closing'
            enqueue_job(db,p.foundation_id,'studio.close',{'session_id':str(row.id),'generation':row.generation})
        row.version+=1;audit(db,p,'studio.session.close','studio_session',id,('state',));return s.session_view(row,context)
    return await execute(db,p,'studio.session.close:'+str(id),key,body.model_dump(mode='json'),lambda:s.session(db,p,id,True,True),action)

@router.post('/studio-sessions/{id}/board-token',response_model=StudioBoardPass)
async def board_token(id:UUID,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    import jwt
    await authz_guard(db,p);row,context=await s.session(db,p,id)
    if row.state not in (('prepared','opening','live') if context.can_host else ('live',)):raise ApiError(409,'board_closed','Доска уже закрыта.')
    settings=RtcSettings.from_env()
    if not settings.board_url or len(settings.board_secret)<32:raise ApiError(503,'board_unavailable','Совместная доска ещё не настроена.')
    await rate_limit(db,p.actor_id,'studio.board_token',limit=30,seconds=60)
    can_draw=await s.board_rights(db,p,row,context);now=int(time.time())
    token=jwt.encode({'iss':'opora-api','aud':'opora-board','sub':identity(p.user_id),'room':row.room_name,'foundation_id':str(p.foundation_id),'session_id':str(row.id),'auth_session_id':str(p.session_id),'can_draw':can_draw,'iat':now,'exp':now+60},settings.board_secret,algorithm='HS256')
    await db.commit();return {'url':settings.board_url.rstrip('/')+'/board/'+row.room_name,'token':token,'can_draw':can_draw,'expires_in':60}

@router.post('/studio-board/authorize')
async def authorize_board(request:Request,db:AsyncSession=Depends(get_db)):
    import jwt
    settings=RtcSettings.from_env();token=request.headers.get('authorization','').removeprefix('Bearer ')
    if len(settings.board_secret)<32 or not token or len(token)>8192:raise ApiError(401,'board_token_invalid','Доступ к доске недействителен.')
    try:claims=jwt.decode(token,settings.board_secret,algorithms=['HS256'],issuer='opora-api',audience='opora-board',leeway=5,options={'require':['sub','exp','room','session_id','foundation_id','auth_session_id']})
    except jwt.PyJWTError:raise ApiError(401,'board_token_invalid','Доступ к доске недействителен.') from None
    try:
        auth_session=await db.get(Session,UUID(claims['auth_session_id']))
        if not auth_session or auth_session.revoked_at or auth_session.expires_at<=datetime.now(timezone.utc):raise ValueError()
        p=await resolve_principal(db,auth_session);await authz_guard(db,p)
        row,context=await s.session(db,p,UUID(claims['session_id']))
        if str(p.foundation_id)!=claims['foundation_id'] or identity(p.user_id)!=claims['sub'] or row.room_name!=claims['room'] or row.state not in (('prepared','opening','live') if context.can_host else ('live',)):raise ValueError()
        can_draw=await s.board_rights(db,p,row,context)
        if can_draw!=(claims.get('can_draw') is True):raise ValueError()
        await db.commit();return {'allowed':True,'can_draw':can_draw}
    except (ValueError,TypeError,KeyError,ApiError):
        await db.rollback();raise ApiError(403,'board_access_revoked','Доступ к доске изменился.') from None

@router.post('/studio-sessions/{id}/board-grants',response_model=StudioSessionView)
async def board_grant(id:UUID,body:StudioBoardGrantInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def action(scope):
        row,context=scope;s.version(row,body.expected_version)
        if row.resource_kind!='live_event':raise ApiError(422,'board_audience_unavailable','В личной записи нет аудитории.')
        enrollment=await db.scalar(select(WebinarEnrollment).where(WebinarEnrollment.webinar_id==row.resource_id,WebinarEnrollment.user_id==body.user_id,WebinarEnrollment.state=='enrolled'))
        if not enrollment:s.deny()
        grant=await db.scalar(select(StudioBoardGrant).where(StudioBoardGrant.session_id==id,StudioBoardGrant.user_id==body.user_id))
        if not grant:grant=StudioBoardGrant(session_id=id,user_id=body.user_id,can_draw=body.can_draw,version=1);db.add(grant)
        else:grant.can_draw=body.can_draw;grant.version+=1
        row.version+=1;audit(db,p,'studio.board.grant','studio_session',id,('board_grants',));await db.flush();return s.session_view(row,context)
    return await execute(db,p,'studio.board.grant:'+str(id)+':'+str(body.user_id),key,body.model_dump(mode='json'),lambda:s.session(db,p,id,True,True),action)

@router.post('/slide-decks/upload-intents',response_model=SlideDeckView,status_code=201)
async def slide_intent(body:SlideUploadInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    from . import assets
    from .models import SlideDeck
    from app.modules.assets.registry import create_upload_intent
    async def action(_):
        deck=SlideDeck(id=uuid4(),foundation_id=p.foundation_id,owner_user_id=p.user_id,resource_kind=body.resource_kind,resource_id=body.resource_id,title=body.title,state='uploading',version=1)
        db.add(deck);await db.flush()
        asset=await create_upload_intent(db,p,content_type=body.content_type,expected_size=body.expected_size,checksum=body.checksum,purpose='studio.slides',resource_type='slide_deck',resource_id=deck.id)
        deck.source_asset_id=asset.id;audit(db,p,'studio.slides.intent','slide_deck',deck.id,('source_asset_id',));await db.flush();return await s.deck_view(db,p,deck)
    return await execute(db,p,'studio.slides.intent',key,body.model_dump(mode='json'),lambda:s.authorize_resource(db,p,body.resource_kind,body.resource_id,True),action)

@router.get('/slide-decks/{id}/status',response_model=SlideDeckView)
async def slide_status(id:UUID,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    deck,_=await s.deck_context(db,p,id);return await s.deck_view(db,p,deck)

@router.get('/slide-pages/{id}/content')
async def slide_content(id:UUID,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    from .models import SlidePage,SlideDeckVersion
    from app.core.models import MediaAsset
    from app.modules.assets.service import asset_content
    page=await db.get(SlidePage,id);version=await db.get(SlideDeckVersion,page.deck_version_id) if page else None
    if not version:s.deny()
    deck,context=await s.deck_context(db,p,version.deck_id)
    if not context.can_host:
        row=await db.scalar(select(StudioSession).where(StudioSession.resource_kind==deck.resource_kind,StudioSession.resource_id==deck.resource_id,StudioSession.state=='live'))
        if not row or row.scene.get('slide_id')!=str(page.id):s.deny()
    asset=await db.get(MediaAsset,page.asset_id)
    if not asset or asset.checksum!=page.sha256 or asset.foundation_id!=p.foundation_id:s.deny()
    return await asset_content(db,asset)

@router.post('/slide-decks/{id}/retry',response_model=SlideDeckView)
async def slide_retry(id:UUID,body:StudioVersionCommand,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    from app.core.models import MediaAsset,Job
    async def action(scope):
        deck,_=scope;s.version(deck,body.expected_version)
        asset=await db.get(MediaAsset,deck.source_asset_id,with_for_update=True)
        previous=await db.get(Job,asset.processing_job_id) if asset and asset.processing_job_id else None
        if deck.state!='failed' and not (previous and previous.state=='dead' and deck.state!='ready'):raise ApiError(409,'slides_not_failed','Обработка презентации уже идёт или завершена.')
        if not asset:raise ApiError(409,'slides_source_unavailable','Исходный файл недоступен. Загрузите презентацию заново.')
        job=enqueue_job(db,p.foundation_id,'slides.convert',{'asset_id':str(asset.id),'resource_type':'slide_deck','resource_id':str(deck.id),'source_checksum':asset.checksum})
        asset.state='processing';asset.processing_job_id=job.id;deck.state='converting';deck.error_code=None;deck.version+=1
        audit(db,p,'studio.slides.retry','slide_deck',id,('state',));return await s.deck_view(db,p,deck)
    return await execute(db,p,'studio.slides.retry:'+str(id),key,body.model_dump(mode='json'),lambda:s.deck_context(db,p,id,True,True),action)

@router.post('/studio-sessions/{id}/board-snapshots')
async def board_snapshot(id:UUID,body:StudioBoardSnapshotInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    import asyncio,io
    from PIL import Image
    from app.core.models import MediaAsset
    from app.modules.assets.service import asset_path
    from .models import StudioBoardSnapshot
    async def action(scope):
        row,_=scope
        asset=await db.scalar(select(MediaAsset).where(MediaAsset.id==body.asset_id,MediaAsset.foundation_id==p.foundation_id,MediaAsset.owner_user_id==p.user_id,MediaAsset.state=='ready',MediaAsset.content_type=='image/png'))
        if not asset or asset.expected_size>5*1024*1024:s.deny()
        def dimensions():
            with Image.open(asset_path(asset)) as image:
                if image.width*image.height>16_000_000:raise ApiError(422,'board_snapshot_too_large','Уменьшите размер снимка доски.')
                image.load();return image.width,image.height
        width,height=await asyncio.to_thread(dimensions)
        snapshot=StudioBoardSnapshot(session_id=id,asset_id=asset.id,width=width,height=height,sha256=asset.checksum)
        db.add(snapshot);await db.flush();audit(db,p,'studio.board.snapshot','studio_session',id,('snapshot',))
        return {'id':str(snapshot.id),'asset_id':str(asset.id),'sha256':asset.checksum,'width':width,'height':height,'content_url':f'/api/v1/studio-board-snapshots/{snapshot.id}/content'}
    return await execute(db,p,'studio.board.snapshot:'+str(id),key,body.model_dump(mode='json'),lambda:s.session(db,p,id,True),action)

@router.get('/studio-board-snapshots/{id}/content')
async def board_snapshot_content(id:UUID,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    from .models import StudioBoardSnapshot
    from app.core.models import MediaAsset
    from app.modules.assets.service import asset_content
    snapshot=await db.get(StudioBoardSnapshot,id)
    if not snapshot:s.deny()
    row,context=await s.session(db,p,snapshot.session_id)
    if not context.can_host and (row.state!='live' or row.scene.get('board_snapshot_id')!=str(id)):s.deny()
    asset=await db.get(MediaAsset,snapshot.asset_id)
    if not asset or asset.foundation_id!=p.foundation_id or asset.checksum!=snapshot.sha256:s.deny()
    return await asset_content(db,asset)

@router.post('/studio-provider/webhook')
async def webhook(request:Request,db:AsyncSession=Depends(get_db)):
    import json
    from app.integrations.rtc.livekit import verify_webhook
    from .models import StudioWebhookEvent
    parts=[];size=0
    async for part in request.stream():
        size+=len(part)
        if size>256*1024:raise ApiError(413,'webhook_too_large','Слишком большой запрос.')
        parts.append(part)
    body=b''.join(parts)
    if not verify_webhook(RtcSettings.from_env(),body,request.headers.get('authorization')):raise ApiError(401,'webhook_invalid','Подпись события недействительна.')
    try:event=json.loads(body);event_id=event['id'];kind=event['event'];room=event['room']['name']
    except (ValueError,KeyError,TypeError):raise ApiError(422,'webhook_invalid','Неверный формат события.') from None
    if not isinstance(event_id,str) or len(event_id)>100 or not isinstance(kind,str) or len(kind)>60 or not isinstance(room,str) or len(room)>128:raise ApiError(422,'webhook_invalid','Неверный формат события.')
    if await db.get(StudioWebhookEvent,event_id):return {'accepted':True}
    row=await db.scalar(select(StudioSession).where(StudioSession.room_name==room).with_for_update())
    if not row:raise ApiError(404,'studio_session_not_found','Комната не найдена.')
    from sqlalchemy.dialects.postgresql import insert
    stored=await db.scalar(insert(StudioWebhookEvent).values(id=event_id,event_type=kind,room_name=room).on_conflict_do_nothing(index_elements=[StudioWebhookEvent.id]).returning(StudioWebhookEvent.id))
    if stored is None:await db.commit();return {'accepted':True}
    if kind=='participant_joined':
        participant=event.get('participant') or {};participant_identity=participant.get('identity','')
        # Reconciliation rechecks enrollment/state instead of trusting webhook role metadata.
        enqueue_job(db,row.foundation_id,'studio.reconcile_participant',{'session_id':str(row.id),'generation':row.generation,'identity':participant_identity})
    await db.commit();return {'accepted':True}

@router.get('/webinars/{id}',response_model=WebinarView)
async def webinar_detail(id:UUID,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    row=await db.scalar(select(Webinar).where(Webinar.id==id,Webinar.foundation_id==p.foundation_id))
    if not row or (row.state!='published' and not (p.has_permission('studio.manage') and row.host_user_id==p.user_id)):s.deny()
    return await webinar_view(db,p,row)

@router.post('/webinars/{id}/join-token',response_model=StudioJoinView)
async def webinar_join(id:UUID,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    row=await db.scalar(select(StudioSession).where(StudioSession.foundation_id==p.foundation_id,StudioSession.resource_kind=='live_event',StudioSession.resource_id==id,StudioSession.state.in_(['opening','live'])))
    if not row:raise ApiError(409,'studio_not_live','Ведущий ещё не открыл комнату.')
    return await join(row.id,db,p)


@router.get('/webinars/{id}/enrollments',response_model=list[StudioParticipantView])
async def webinar_participants(id:UUID,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    await s.authorize_resource(db,p,'live_event',id,True)
    current=await db.scalar(select(StudioSession).where(StudioSession.foundation_id==p.foundation_id,StudioSession.resource_kind=='live_event',StudioSession.resource_id==id,StudioSession.state.in_(['prepared','opening','live','closing'])))
    grants=dict((await db.execute(select(StudioBoardGrant.user_id,StudioBoardGrant.can_draw).where(StudioBoardGrant.session_id==current.id))).all()) if current else {}
    rows=(await db.execute(select(WebinarEnrollment,User.display_name).join(User,User.id==WebinarEnrollment.user_id).where(WebinarEnrollment.webinar_id==id,WebinarEnrollment.foundation_id==p.foundation_id).order_by(User.display_name,User.id))).all()
    return [{'user_id':enrollment.user_id,'display_name':name,'enrollment_state':enrollment.state,'enrollment_version':enrollment.version,'can_draw':grants.get(enrollment.user_id,False)} for enrollment,name in rows]
