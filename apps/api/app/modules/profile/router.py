from uuid import UUID
from fastapi import APIRouter,Depends,Header
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal,require_permission,authz_guard
from app.core.audit import audit
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.models import User
from app.core.idempotency import begin_command,finish_command
from app.modules.applications.consents import consent_events
from app.modules.applications.models import ConsentEvent
from . import service,ledger
from . import schemas as dto
from .models import ProfileChangeSuggestion,ManualTimeRequest,ProfileDocument,ProfileDataRequest
router=APIRouter(prefix='/api/v1',tags=['profile'])

async def command(db,principal,operation,key,body,action,permission=None):
    await authz_guard(db,principal)
    service.require_user(principal)
    if permission and not principal.has_permission(permission):raise ApiError(403,'permission_denied','Недостаточно прав')
    payload=body.model_dump(mode='json')
    prior=await begin_command(db,principal,operation,key,payload)
    if prior is not None:await db.commit();return prior
    result=await action();result=result.model_dump(mode='json') if hasattr(result,'model_dump') else result
    audit(db,principal,operation,'profile',result.get('id',principal.user_id),payload.keys())
    await finish_command(db,principal,operation,key,result);await db.commit();return result

@router.get('/me/profile',response_model=dto.ProfileView)
async def profile(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.profile_view(db,principal)

@router.put('/me/profile',response_model=dto.ProfileView)
async def update_profile(body:dto.ProfileUpdateCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,'profile.update',idempotency_key,body,lambda:service.update_profile(db,principal,body))

@router.get('/me/profile/consents',response_model=list[dto.ProfileConsentView])
async def consents(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    service.require_user(principal)
    return [dto.ProfileConsentView(id=e.id,purpose=e.purpose,granted=e.granted,document=e.document,document_version=e.document_version,source=e.source,created_at=e.created_at) for e in await consent_events(db,principal.foundation_id,user_id=principal.user_id)]

@router.post('/me/profile/consents',response_model=dto.ProfileConsentView)
async def change_consent(body:dto.ProfileConsentCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    async def action():
        await service.own_user(db,principal,True)
        if body.granted and body.document_version!='4':raise ApiError(409,'consent_document_outdated','Прочитайте актуальную версию документа')
        event=ConsentEvent(subject_user_id=principal.user_id,document='news' if body.purpose=='news' else 'privacy',document_version=body.document_version,purpose=body.purpose,granted=body.granted,source='profile',author_id=principal.actor_id)
        db.add(event);await db.flush()
        return dto.ProfileConsentView(id=event.id,purpose=event.purpose,granted=event.granted,document=event.document,document_version=event.document_version,source=event.source,created_at=event.created_at)
    return await command(db,principal,'profile.consent',idempotency_key,body,action)

@router.get('/me/profile/suggestions',response_model=list[dto.ProfileSuggestionView])
async def suggestions(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    service.require_user(principal)
    rows=(await db.scalars(select(ProfileChangeSuggestion).where(ProfileChangeSuggestion.foundation_id==principal.foundation_id,ProfileChangeSuggestion.user_id==principal.user_id).order_by(ProfileChangeSuggestion.created_at.desc()).limit(100))).all()
    return [service.suggestion_view(row) for row in rows]

@router.post('/me/profile/suggestions/{suggestion_id}/decision',response_model=dto.ProfileSuggestionView)
async def decide_suggestion(suggestion_id:UUID,body:dto.SuggestionDecisionCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'profile.suggestion:{suggestion_id}',idempotency_key,body,lambda:service.decide_suggestion(db,principal,suggestion_id,body))

@router.get('/me/hours',response_model=dto.HoursView)
async def hours(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await ledger.hours_view(db,principal)

@router.post('/me/hours/requests',response_model=dto.ManualTimeView)
async def request_hours(body:dto.ManualTimeCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,'profile.time.request',idempotency_key,body,lambda:ledger.request_manual_time(db,principal,body))

@router.post('/me/hours/requests/{request_id}/cancel',response_model=dto.ManualTimeView)
async def cancel_hours(request_id:UUID,body:dto.ProfileVersionCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'profile.time.cancel:{request_id}',idempotency_key,body,lambda:ledger.cancel_manual_time(db,principal,request_id,body))

@router.get('/coord/hours/requests',response_model=list[dto.ManualTimeView])
async def review_hours_queue(principal:Principal=Depends(require_permission('hours.review')),db:AsyncSession=Depends(get_db)):
    rows=(await db.scalars(select(ManualTimeRequest).where(ManualTimeRequest.foundation_id==principal.foundation_id).order_by(ManualTimeRequest.created_at.desc()).limit(200))).all()
    return [await ledger.manual_view(db,row) for row in rows]

@router.post('/coord/hours/requests/{request_id}/review',response_model=dto.ManualTimeView)
async def review_hours(request_id:UUID,body:dto.ManualTimeReviewCommand,principal:Principal=Depends(require_permission('hours.review')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'profile.time.review:{request_id}',idempotency_key,body,lambda:ledger.review_manual_time(db,principal,request_id,body),'hours.review')

@router.post('/coord/gratitudes',response_model=dto.GratitudeView)
async def gratitude(body:dto.GratitudeCommand,principal:Principal=Depends(require_permission('recognition.manage')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,'profile.gratitude',idempotency_key,body,lambda:ledger.add_gratitude(db,principal,body),'recognition.manage')

from . import documents,data_requests
@router.get('/me/profile/documents',response_model=list[dto.ProfileDocumentView])
async def documents_list(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    service.require_user(principal)
    rows=(await db.scalars(select(ProfileDocument).where(ProfileDocument.foundation_id==principal.foundation_id,ProfileDocument.user_id==principal.user_id).order_by(ProfileDocument.created_at.desc()).limit(100))).all()
    return [documents.document_view(row) for row in rows]

@router.post('/me/profile/documents',response_model=dto.ProfileDocumentView)
async def request_document(body:dto.ProfileDocumentCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,'profile.document.request',idempotency_key,body,lambda:documents.request_document(db,principal,body))

@router.get('/coord/profile/documents',response_model=list[dto.ProfileDocumentView])
async def documents_queue(principal:Principal=Depends(require_permission('recognition.manage')),db:AsyncSession=Depends(get_db)):
    rows=(await db.scalars(select(ProfileDocument).where(ProfileDocument.foundation_id==principal.foundation_id).order_by(ProfileDocument.created_at.desc()).limit(200))).all()
    return [documents.document_view(row).model_copy(update={'display_name':(await db.get(User,row.user_id)).display_name}) for row in rows]

@router.post('/coord/profile/documents/{document_id}/review',response_model=dto.ProfileDocumentView)
async def document_review(document_id:UUID,body:dto.ProfileDocumentReviewCommand,principal:Principal=Depends(require_permission('recognition.manage')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'profile.document.review:{document_id}',idempotency_key,body,lambda:documents.review_document(db,principal,document_id,body),'recognition.manage')

@router.get('/me/profile/data-requests',response_model=list[dto.ProfileDataView])
async def data_list(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    service.require_user(principal)
    rows=(await db.scalars(select(ProfileDataRequest).where(ProfileDataRequest.foundation_id==principal.foundation_id,ProfileDataRequest.user_id==principal.user_id).order_by(ProfileDataRequest.created_at.desc()).limit(100))).all()
    return [data_requests.data_view(row) for row in rows]

@router.post('/me/profile/data-requests',response_model=dto.ProfileDataView)
async def data_request(body:dto.ProfileDataCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,'profile.data.request',idempotency_key,body,lambda:data_requests.create_request(db,principal,body))

@router.post('/me/profile/data-requests/{request_id}/cancel',response_model=dto.ProfileDataView)
async def data_cancel(request_id:UUID,body:dto.ProfileVersionCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'profile.data.cancel:{request_id}',idempotency_key,body,lambda:data_requests.cancel_request(db,principal,request_id,body))

@router.get('/coord/profile/data-requests',response_model=list[dto.ProfileDataView])
async def data_queue(principal:Principal=Depends(require_permission('profile.requests.review')),db:AsyncSession=Depends(get_db)):
    rows=(await db.scalars(select(ProfileDataRequest).where(ProfileDataRequest.foundation_id==principal.foundation_id).order_by(ProfileDataRequest.created_at.desc()).limit(200))).all()
    return [data_requests.data_view(row).model_copy(update={'display_name':(await db.get(User,row.user_id)).display_name}) for row in rows]

@router.post('/coord/profile/data-requests/{request_id}/review',response_model=dto.ProfileDataView)
async def data_review(request_id:UUID,body:dto.ProfileDataReviewCommand,principal:Principal=Depends(require_permission('profile.requests.review')),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'profile.data.review:{request_id}',idempotency_key,body,lambda:data_requests.review_request(db,principal,request_id,body),'profile.requests.review')

@router.get('/coord/profile/recognition-bases',response_model=list[dto.RecognitionBasisView])
async def recognition_bases(principal:Principal=Depends(require_permission('recognition.manage')),db:AsyncSession=Depends(get_db)):
    return await ledger.recognition_bases(db,principal)
