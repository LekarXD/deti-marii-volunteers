import hashlib
from urllib.parse import unquote
from uuid import UUID
from fastapi import APIRouter,Depends,Header,Query,Request
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal,require_permission,authz_guard
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.audit import audit
from app.core.idempotency import begin_command,finish_command
from app.core.models import StaffMembership,User
from . import service,imports
from .models import CrmVolunteer,FollowUpTask,ImportBatch
from .schemas import (CreateVolunteerCommand,AgreementCommand,ContactCommand,AvailabilityCommand,VerificationCommand,PreferenceCommand,CrmReviewCommand,
    TaskCreateCommand,TaskUpdateCommand,MergeCommand,ImportMappingCommand,ImportRowResolutionCommand,VersionCommand,SelfAvailabilityCommand,
    CrmVolunteerView,CrmVolunteerListView,FollowUpTaskView,ImportBatchView,ImportBatchSummary,OwnAvailabilityView,StaffOptionView,CrmApplicationOptionView)
router=APIRouter(prefix='/api/v1',tags=['crm'])


async def command(db,principal,operation,key,payload,action,permission=None):
    await authz_guard(db,principal)
    if permission and not principal.has_permission(permission):raise ApiError(403,'permission_denied','Недостаточно прав')
    encoded=payload.model_dump(mode='json') if hasattr(payload,'model_dump') else payload
    prior=await begin_command(db,principal,operation,key,encoded)
    if prior is not None:await db.commit();return prior
    result=await action();result=result.model_dump(mode='json') if hasattr(result,'model_dump') else result
    audit(db,principal,operation,'crm',result.get('volunteer_id',result.get('id','')),encoded.keys())
    await finish_command(db,principal,operation,key,result);await db.commit();return result


@router.get('/coord/volunteers',response_model=CrmVolunteerListView)
async def volunteers(q:str=Query(default='',max_length=200),state:str|None=None,no_contact:bool|None=None,offset:int=Query(default=0,ge=0),limit:int=Query(default=30,ge=1,le=100),
    principal:Principal=Depends(require_permission('crm.read')),db:AsyncSession=Depends(get_db)):
    query=select(CrmVolunteer).where(CrmVolunteer.foundation_id==principal.foundation_id,CrmVolunteer.merged_into_id.is_(None))
    if q.strip():query=query.where(CrmVolunteer.display_name.ilike('%'+q.strip().replace('%','').replace('_','')+'%'))
    if state:query=query.where(CrmVolunteer.relationship_state==state)
    if no_contact is not None:query=query.where(CrmVolunteer.no_contact==no_contact)
    total=await db.scalar(select(func.count()).select_from(query.subquery()))
    rows=(await db.scalars(query.order_by(CrmVolunteer.display_name,CrmVolunteer.id).offset(offset).limit(limit))).all()
    return CrmVolunteerListView(items=[await service.volunteer_view(db,row) for row in rows],total=total,offset=offset,limit=limit)


@router.get('/coord/volunteers/application-options',response_model=list[CrmApplicationOptionView])
async def application_options(q:str=Query(default='',max_length=200),principal:Principal=Depends(require_permission('crm.write')),db:AsyncSession=Depends(get_db)):
    from app.modules.applications.service import learning_recipient_options
    return await learning_recipient_options(db,principal,q)


@router.get('/coord/crm/staff',response_model=list[StaffOptionView])
async def staff_options(principal:Principal=Depends(require_permission('crm.read')),db:AsyncSession=Depends(get_db)):
    users=(await db.scalars(select(User).join(StaffMembership,StaffMembership.user_id==User.id).where(StaffMembership.foundation_id==principal.foundation_id,
        StaffMembership.revoked_at.is_(None),User.foundation_id==principal.foundation_id,User.account_state=='active').order_by(User.display_name,User.id))).all()
    return [StaffOptionView(id=user.id,display_name=user.display_name) for user in users]


@router.post('/coord/volunteers',response_model=CrmVolunteerView)
async def create_volunteer(body:CreateVolunteerCommand,principal:Principal=Depends(require_permission('crm.write')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    async def action():return await service.volunteer_view(db,await service.ensure_volunteer(db,principal.foundation_id,body.application_id),True,principal=principal)
    return await command(db,principal,'crm.create',idempotency_key,body,action,'crm.write')


@router.get('/coord/volunteers/{volunteer_id}',response_model=CrmVolunteerView)
async def volunteer(volunteer_id:UUID,principal:Principal=Depends(require_permission('crm.read')),db:AsyncSession=Depends(get_db)):
    return await service.volunteer_view(db,await service.scoped_volunteer(db,principal.foundation_id,volunteer_id),True,principal=principal)


@router.post('/coord/volunteers/{volunteer_id}/agreements',response_model=CrmVolunteerView)
async def agreement(volunteer_id:UUID,body:AgreementCommand,principal:Principal=Depends(require_permission('crm.write')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'crm.agreement:{volunteer_id}',idempotency_key,body,lambda:service.add_agreement(db,principal,volunteer_id,body),'crm.write')


@router.post('/coord/volunteers/{volunteer_id}/contact-events',response_model=CrmVolunteerView)
async def contact(volunteer_id:UUID,body:ContactCommand,principal:Principal=Depends(require_permission('crm.write')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'crm.contact:{volunteer_id}',idempotency_key,body,lambda:service.add_contact(db,principal,volunteer_id,body),'crm.write')


@router.put('/coord/volunteers/{volunteer_id}/availability',response_model=CrmVolunteerView)
async def availability(volunteer_id:UUID,body:AvailabilityCommand,principal:Principal=Depends(require_permission('crm.write')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'crm.availability:{volunteer_id}',idempotency_key,body,lambda:service.save_availability(db,principal,volunteer_id,body),'crm.write')


@router.post('/coord/volunteers/{volunteer_id}/availability-verifications',response_model=CrmVolunteerView)
async def verification(volunteer_id:UUID,body:VerificationCommand,principal:Principal=Depends(require_permission('contacts.review')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'crm.verify:{volunteer_id}',idempotency_key,body,lambda:service.verify_availability(db,principal,volunteer_id,body),'contacts.review')


@router.post('/coord/volunteers/{volunteer_id}/contact-preference',response_model=CrmVolunteerView)
async def preference(volunteer_id:UUID,body:PreferenceCommand,principal:Principal=Depends(require_permission('contacts.review')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'crm.preference:{volunteer_id}',idempotency_key,body,lambda:service.set_preference(db,principal,volunteer_id,body),'contacts.review')


@router.post('/coord/volunteers/{volunteer_id}/follow-up-tasks',response_model=FollowUpTaskView)
async def add_task(volunteer_id:UUID,body:TaskCreateCommand,principal:Principal=Depends(require_permission('crm.write')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'crm.task:{volunteer_id}',idempotency_key,body,lambda:service.create_task(db,principal,volunteer_id,body),'crm.write')


@router.get('/coord/follow-up-tasks',response_model=list[FollowUpTaskView])
async def tasks(state:str='open',principal:Principal=Depends(require_permission('crm.read')),db:AsyncSession=Depends(get_db)):
    rows=(await db.scalars(select(FollowUpTask).where(FollowUpTask.foundation_id==principal.foundation_id,FollowUpTask.state==state).order_by(FollowUpTask.due_on,FollowUpTask.id).limit(200))).all()
    return [service.task_view(task) for task in rows]


@router.post('/coord/follow-up-tasks/{task_id}',response_model=FollowUpTaskView)
async def task(task_id:UUID,body:TaskUpdateCommand,principal:Principal=Depends(require_permission('crm.write')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'crm.task.update:{task_id}',idempotency_key,body,lambda:service.update_task(db,principal,task_id,body),'crm.write')


@router.post('/coord/volunteers/{volunteer_id}/merge',response_model=CrmVolunteerView)
async def merge(volunteer_id:UUID,body:MergeCommand,principal:Principal=Depends(require_permission('crm.write')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'crm.merge:{volunteer_id}',idempotency_key,body,lambda:service.merge_volunteers(db,principal,volunteer_id,body),'crm.write')


@router.get('/coord/contact-reviews',response_model=CrmVolunteerListView)
async def reviews(state:str|None='unverified',q:str='',offset:int=Query(default=0,ge=0),limit:int=Query(default=30,ge=1,le=100),principal:Principal=Depends(require_permission('contacts.review')),db:AsyncSession=Depends(get_db)):
    return await volunteers(q,state,None,offset,limit,principal,db)


@router.post('/coord/contact-reviews/{volunteer_id}/record',response_model=CrmVolunteerView)
async def record_review(volunteer_id:UUID,body:CrmReviewCommand,principal:Principal=Depends(require_permission('contacts.review')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'crm.review:{volunteer_id}',idempotency_key,body,lambda:service.record_review(db,principal,volunteer_id,body),'contacts.review')


@router.get('/me/availability',response_model=OwnAvailabilityView)
async def own_availability(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.own_availability(db,principal)


@router.put('/me/availability',response_model=OwnAvailabilityView)
async def save_own_availability(body:SelfAvailabilityCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,'crm.own_availability',idempotency_key,body,lambda:service.save_own_availability(db,principal,body))


@router.post('/coord/import-batches/upload',response_model=ImportBatchView)
async def upload(request:Request,x_filename:str=Header(default='contacts.csv'),principal:Principal=Depends(require_permission('crm.write')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    chunks=[];size=0
    async for chunk in request.stream():
        size+=len(chunk)
        if size>imports.MAX_BYTES:raise ApiError(413,'import_too_large','Файл больше 5 МБ')
        chunks.append(chunk)
    blob=b''.join(chunks);filename=unquote(x_filename)
    payload=dict(checksum=hashlib.sha256(blob).hexdigest(),filename=filename)
    return await command(db,principal,'crm.import.upload',idempotency_key,payload,lambda:imports.upload(db,principal,blob,filename),'crm.write')


@router.get('/coord/import-batches',response_model=list[ImportBatchSummary])
async def batches(principal:Principal=Depends(require_permission('crm.read')),db:AsyncSession=Depends(get_db)):
    rows=(await db.scalars(select(ImportBatch).where(ImportBatch.foundation_id==principal.foundation_id).order_by(ImportBatch.created_at.desc()).limit(30))).all()
    return [await imports.batch_summary(db,batch) for batch in rows]


@router.get('/coord/import-batches/{batch_id}',response_model=ImportBatchView)
async def batch(batch_id:UUID,principal:Principal=Depends(require_permission('crm.read')),db:AsyncSession=Depends(get_db)):
    return await imports.batch_view(db,await imports.scoped_batch(db,principal,batch_id))


@router.post('/coord/import-batches/{batch_id}/map',response_model=ImportBatchView)
async def map_batch(batch_id:UUID,body:ImportMappingCommand,principal:Principal=Depends(require_permission('crm.write')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'crm.import.map:{batch_id}',idempotency_key,body,lambda:imports.map_batch(db,principal,batch_id,body),'crm.write')


@router.post('/coord/import-batches/{batch_id}/dry-run',response_model=ImportBatchView)
async def dry_run(batch_id:UUID,body:VersionCommand,principal:Principal=Depends(require_permission('crm.write')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'crm.import.preview:{batch_id}',idempotency_key,body,lambda:imports.dry_run(db,principal,batch_id,body),'crm.write')


@router.post('/coord/import-batches/{batch_id}/rows/{row_id}/resolve',response_model=ImportBatchView)
async def resolve_row(batch_id:UUID,row_id:UUID,body:ImportRowResolutionCommand,principal:Principal=Depends(require_permission('crm.write')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'crm.import.resolve:{row_id}',idempotency_key,body,lambda:imports.resolve_row(db,principal,batch_id,row_id,body),'crm.write')


@router.post('/coord/import-batches/{batch_id}/apply',response_model=ImportBatchView)
async def apply_batch(batch_id:UUID,body:VersionCommand,principal:Principal=Depends(require_permission('crm.write')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'crm.import.apply:{batch_id}',idempotency_key,body,lambda:imports.apply_batch(db,principal,batch_id,body),'crm.write')


from .schemas import FirstVisitOutcomeCommand
@router.post('/coord/volunteers/{volunteer_id}/first-visit-outcomes',response_model=CrmVolunteerView)
async def first_visit_outcome(volunteer_id:UUID,body:FirstVisitOutcomeCommand,principal:Principal=Depends(require_permission('crm.write')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'crm.first_visit:{volunteer_id}',idempotency_key,body,lambda:service.first_visit_outcome(db,principal,volunteer_id,body),'crm.write')
