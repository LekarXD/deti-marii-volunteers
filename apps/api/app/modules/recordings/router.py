from uuid import UUID,uuid4
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter,Depends,Request,Query
from sqlalchemy import select,update,cast,String
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal,authz_guard
from app.core.audit import audit
from app.core.clock import utcnow
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.idempotency import begin_command,finish_command
from . import service
from .models import RecordingProject,RecordingTake,RecordingRendererGrant,RecordingRenderVersion,RecordingReview
from .schemas import RecordingProjectInput,RecordingProjectUpdate,RecordingVersionCommand,RecordingTakeInput,RecordingProjectView,RecordingTakeView,RecordingRenderView,RecordingReviewCommand,RecordingProjectPage,RecordingTakePage,RecordingPolicyCommand,RecordingRenderPage
from .renderer import router as renderer_router
router=APIRouter(prefix='/api/v1',tags=['recordings'])

def version(row,expected):
    if row.version!=expected:raise ApiError(409,'version_conflict','Данные изменились',current_version=row.version)
async def command(db,p,request,operation,body):return await begin_command(db,p,operation,request.headers.get('Idempotency-Key'),body.model_dump(mode='json'))
async def finish(db,p,request,operation,value):
    result=await finish_command(db,p,operation,request.headers.get('Idempotency-Key'),jsonable_encoder(value))
    await db.commit()
    return result

@router.get('/recording-projects',operation_id='recording_project_list',response_model=RecordingProjectPage)
async def listing(cursor:UUID|None=None,limit:int=Query(20,ge=1,le=50),p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    await authz_guard(db,p)
    if not p.user_id or not p.has_permission('recordings.manage'):raise ApiError(403,'permission_denied','Недостаточно прав для записи урока')
    query=select(RecordingProject).where(RecordingProject.foundation_id==p.foundation_id,RecordingProject.owner_user_id==p.user_id)
    if cursor:query=query.where(RecordingProject.id>cursor)
    rows=(await db.scalars(query.order_by(RecordingProject.id).limit(limit+1))).all()
    result={'items':[await service.project_view(db,row) for row in rows[:limit]],'next_cursor':rows[limit-1].id if len(rows)>limit else None}
    await db.commit();return result

@router.post('/recording-projects',operation_id='recording_project_create',response_model=RecordingProjectView)
async def create(body:RecordingProjectInput,request:Request,p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    await authz_guard(db,p)
    if not p.user_id or not p.has_permission('recordings.manage'):raise ApiError(403,'permission_denied','Недостаточно прав для записи урока')
    replay=await command(db,p,request,'recordings.create',body)
    if replay is not None:return replay
    await service.target(db,p,body.target_lesson_id)
    row=RecordingProject(id=uuid4(),foundation_id=p.foundation_id,owner_user_id=p.user_id,**body.model_dump())
    db.add(row);await db.flush()
    audit(db,p,'recording.create','recording_project',row.id,('title','target_lesson_id'))
    return await finish(db,p,request,'recordings.create',await service.project_view(db,row))

@router.get('/recording-projects/{id}',operation_id='recording_project_get',response_model=RecordingProjectView)
async def get(id:UUID,p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    row=await service.project(db,p,id)
    value=await service.project_view(db,row);await db.commit()
    return value

@router.patch('/recording-projects/{id}',operation_id='recording_project_edit',response_model=RecordingProjectView)
async def edit(id:UUID,body:RecordingProjectUpdate,request:Request,p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    row=await service.project(db,p,id,True);operation=f'recordings.edit:{id}'
    replay=await command(db,p,request,operation,body)
    if replay is not None:return replay
    version(row,body.expected_version)
    if row.state=='archived':raise ApiError(409,'recording_archived','Проект закрыт')
    if 'target_lesson_id' in body.model_fields_set:
        await service.target(db,p,body.target_lesson_id);row.target_lesson_id=body.target_lesson_id
    if body.title is not None:row.title=body.title
    row.version+=1
    audit(db,p,'recording.edit','recording_project',row.id,('title','target_lesson_id'))
    return await finish(db,p,request,operation,await service.project_view(db,row))

@router.post('/recording-projects/{id}/prepare',operation_id='recording_project_prepare',response_model=RecordingProjectView)
async def prepare(id:UUID,body:RecordingVersionCommand,request:Request,p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    row=await service.project(db,p,id,True);operation=f'recordings.prepare:{id}'
    replay=await command(db,p,request,operation,body)
    if replay is not None:return replay
    version(row,body.expected_version)
    if await db.scalar(select(RecordingTake.id).where(RecordingTake.project_id==id,RecordingTake.state.in_(('created','starting','capturing','stopping')))):
        raise ApiError(409,'recording_take_active','Сначала завершите текущий дубль')
    await service.prepare(db,p,row)
    audit(db,p,'recording.prepare','recording_project',id)
    return await finish(db,p,request,operation,await service.project_view(db,row))

@router.post('/recording-projects/{id}/takes',operation_id='recording_take_create',response_model=RecordingTakeView)
async def create_take(id:UUID,body:RecordingTakeInput,request:Request,p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    row=await service.project(db,p,id,True);operation=f'recordings.take:{id}'
    replay=await command(db,p,request,operation,body)
    if replay is not None:return replay
    version(row,body.expected_version)
    take=await service.create_take(db,p,row,body.expected_scene_revision)
    audit(db,p,'recording.take.create','recording_take',take.id)
    return await finish(db,p,request,operation,service.take_view(take))

@router.get('/recording-projects/{id}/takes',operation_id='recording_take_list',response_model=RecordingTakePage)
async def list_takes(id:UUID,before:int|None=Query(None,ge=1),limit:int=Query(20,ge=1,le=50),p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    await service.project(db,p,id)
    query=select(RecordingTake).where(RecordingTake.project_id==id)
    if before:query=query.where(RecordingTake.number<before)
    rows=(await db.scalars(query.order_by(RecordingTake.number.desc()).limit(limit+1))).all()
    value={'items':[service.take_view(row) for row in rows[:limit]],'next_cursor':rows[limit-1].number if len(rows)>limit else None}
    await db.commit();return value

@router.get('/recording-takes/{id}',operation_id='recording_take_get',response_model=RecordingTakeView)
async def get_take(id:UUID,p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    row,_=await service.take(db,p,id);value=service.take_view(row);await db.commit();return value

@router.post('/recording-takes/{id}/discard',operation_id='recording_take_discard',response_model=RecordingTakeView)
async def discard(id:UUID,body:RecordingVersionCommand,request:Request,p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    row,owner=await service.take(db,p,id,True);operation=f'recordings.discard:{id}'
    replay=await command(db,p,request,operation,body)
    if replay is not None:return replay
    version(row,body.expected_version)
    if row.state in ('starting','capturing','stopping'):raise ApiError(409,'capture_still_active','Сначала завершите захват')
    from .models import RecordingPublication
    published=await db.scalar(select(RecordingPublication.id).join(RecordingRenderVersion,RecordingRenderVersion.id==RecordingPublication.render_id).where(RecordingRenderVersion.take_id==id,RecordingPublication.state=='published'))
    from app.modules.learning.models import LessonBlock
    referenced=await db.scalar(select(LessonBlock.id).where(LessonBlock.content['asset_id'].astext.in_(select(cast(RecordingRenderVersion.asset_id,String)).where(RecordingRenderVersion.take_id==id))).limit(1))
    if published or referenced:raise ApiError(409,'recording_is_published','Опубликованный дубль нельзя удалить')
    row.state='discarded';row.version+=1;row.renderer_state_version+=1;row.readiness_state='blocked'
    await db.execute(update(RecordingRendererGrant).where(RecordingRendererGrant.take_id==id,RecordingRendererGrant.revoked_at.is_(None)).values(revoked_at=utcnow()))
    audit(db,p,'recording.discard','recording_take',id)
    return await finish(db,p,request,operation,service.take_view(row))

@router.post('/recording-takes/{id}/policy',operation_id='recording_take_policy',response_model=RecordingTakeView)
async def policy(id:UUID,body:RecordingPolicyCommand,request:Request,p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    from .capture import approve_policy
    row,owner=await service.take(db,p,id,True);operation=f'recordings.policy:{id}'
    replay=await command(db,p,request,operation,body)
    if replay is not None:return replay
    version(row,body.expected_version);await approve_policy(db,p,row,owner,body)
    audit(db,p,'recording.policy','recording_take',id,('privacy_state','allowed_tracks'))
    return await finish(db,p,request,operation,service.take_view(row))

@router.post('/recording-takes/{id}/start',operation_id='recording_take_start',response_model=RecordingTakeView)
async def start(id:UUID,body:RecordingVersionCommand,request:Request,p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    from .capture import start_capture
    row,owner=await service.take(db,p,id,True);operation=f'recordings.start:{id}'
    replay=await command(db,p,request,operation,body)
    if replay is not None:return replay
    version(row,body.expected_version);await start_capture(db,row,owner)
    audit(db,p,'recording.start','recording_take',id)
    return await finish(db,p,request,operation,service.take_view(row))

@router.post('/recording-takes/{id}/stop',operation_id='recording_take_stop',response_model=RecordingTakeView)
async def stop(id:UUID,body:RecordingVersionCommand,request:Request,p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    from .capture import stop_capture
    row,_=await service.take(db,p,id,True);operation=f'recordings.stop:{id}'
    replay=await command(db,p,request,operation,body)
    if replay is not None:return replay
    version(row,body.expected_version);await stop_capture(db,row)
    audit(db,p,'recording.stop','recording_take',id)
    return await finish(db,p,request,operation,service.take_view(row))

@router.get('/recording-projects/{id}/renders',operation_id='recording_render_list',response_model=RecordingRenderPage)
async def render_list(id:UUID,cursor:UUID|None=None,limit:int=Query(20,ge=1,le=50),p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    await service.project(db,p,id)
    query=select(RecordingRenderVersion).where(RecordingRenderVersion.project_id==id)
    if cursor:query=query.where(RecordingRenderVersion.id>cursor)
    rows=(await db.scalars(query.order_by(RecordingRenderVersion.id).limit(limit+1))).all()
    value={'items':[await service.render_view(db,row) for row in rows[:limit]],'next_cursor':rows[limit-1].id if len(rows)>limit else None}
    await db.commit();return value

@router.get('/recording-renders/{id}/status',operation_id='recording_render_status',response_model=RecordingRenderView)
async def render_status(id:UUID,p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    row=await db.get(RecordingRenderVersion,id)
    if row is None:service.deny()
    await service.project(db,p,row.project_id)
    value=await service.render_view(db,row);await db.commit();return value

async def review(db,p,id,body,request,decision):
    row=await db.get(RecordingRenderVersion,id)
    if row is None:service.deny()
    owner=await service.project(db,p,row.project_id,True)
    if not p.has_permission('recordings.review'):raise ApiError(403,'permission_denied','Недостаточно прав для проверки записи')
    row=await db.scalar(select(RecordingRenderVersion).where(RecordingRenderVersion.id==id).with_for_update().execution_options(populate_existing=True))
    operation=f'recordings.{decision}:{id}'
    replay=await command(db,p,request,operation,body)
    if replay is not None:return replay
    version(row,body.expected_version)
    if row.render_hash!=body.render_hash or row.state not in ('preview_ready','degraded') or not row.content_hash or owner.privacy_state!='approved':raise ApiError(409,'recording_review_unavailable','Сначала проверьте готовую запись и политику приватности')
    db.add(RecordingReview(render_id=id,render_hash=row.render_hash,content_hash=row.content_hash,decision=decision,reviewer_user_id=p.user_id,reason=body.reason))
    row.version+=1;await db.flush()
    audit(db,p,'recording.'+decision,'recording_render',id,('render_hash',))
    return await finish(db,p,request,operation,await service.render_view(db,row))

@router.post('/recording-renders/{id}/approve',operation_id='recording_render_approve',response_model=RecordingRenderView)
async def approve(id:UUID,body:RecordingReviewCommand,request:Request,p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await review(db,p,id,body,request,'approved')
@router.post('/recording-renders/{id}/reject',operation_id='recording_render_reject',response_model=RecordingRenderView)
async def reject(id:UUID,body:RecordingReviewCommand,request:Request,p:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await review(db,p,id,body,request,'rejected')

# Renderer routes have their own full prefix and never ordinary session authentication.
root_router=APIRouter()
root_router.include_router(router)
root_router.include_router(renderer_router)
router=root_router
