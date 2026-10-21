from uuid import UUID
from fastapi import APIRouter,Depends,Header
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal,authz_guard
from app.core.db import get_db
from app.core.contact_policy import contact_guard
from app.core.idempotency import begin_command,finish_command
from .models import Webinar,WebinarEnrollment
from .summary_schemas import WebinarSummaryView,SummaryEditInput,SummaryVersionInput,SummaryAudiencePreviewView,SummarySendInput,SummarySendView,SummaryRevisionView
from . import summary_service as s
router=APIRouter()

async def command(db,p,id,operation,key,body,action,send=False):
    try:
        await authz_guard(db,p);s.require_manage(p,send)
        if send:await contact_guard(db,p.foundation_id)
        webinar=await s.scope(db,p,id,True,send)
        name='studio.summary.'+operation+':'+str(id)
        replay=await begin_command(db,p,name,key,body.model_dump(mode='json'))
        if replay is not None:await db.commit();return replay
        result=jsonable_encoder(await action(webinar))
        await finish_command(db,p,name,key,result);await db.commit();return result
    except BaseException:await db.rollback();raise

@router.get('/webinars/{id}/summary',response_model=WebinarSummaryView,operation_id='studio_summary')
async def get_summary(id:UUID,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    await authz_guard(db,p);webinar=await s.scope(db,p,id)
    return await s.view(db,p,webinar,await s.summary(db,id))

@router.patch('/webinars/{id}/summary',response_model=WebinarSummaryView,operation_id='studio_summary_edit')
async def edit_summary(id:UUID,body:SummaryEditInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    return await command(db,p,id,'edit',key,body,lambda webinar:s.edit(db,p,webinar,body))

@router.post('/webinars/{id}/summary/review',response_model=WebinarSummaryView,operation_id='studio_summary_review')
async def review_summary(id:UUID,body:SummaryVersionInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    return await command(db,p,id,'review',key,body,lambda webinar:s.decide(db,p,webinar,body,'review'))

@router.post('/webinars/{id}/summary/publish',response_model=WebinarSummaryView,operation_id='studio_summary_publish')
async def publish_summary(id:UUID,body:SummaryVersionInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    return await command(db,p,id,'publish',key,body,lambda webinar:s.decide(db,p,webinar,body,'publish'))

@router.post('/webinars/{id}/summary/audience-preview',response_model=SummaryAudiencePreviewView,operation_id='studio_summary_audience_preview')
async def preview_summary(id:UUID,body:SummaryVersionInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    return await command(db,p,id,'audience-preview',key,body,lambda webinar:s.preview(db,p,webinar,body),True)

@router.post('/webinars/{id}/summary/send',response_model=SummarySendView,operation_id='studio_summary_send')
async def send_summary(id:UUID,body:SummarySendInput,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal),key:str|None=Header(default=None,alias='Idempotency-Key')):
    return await command(db,p,id,'send',key,body,lambda webinar:s.send(db,p,webinar,body),True)

@router.get('/webinars/{id}/summary/published',response_model=SummaryRevisionView,operation_id='studio_summary_published')
async def published_summary(id:UUID,db:AsyncSession=Depends(get_db),p:Principal=Depends(get_principal)):
    await authz_guard(db,p)
    webinar=await db.scalar(select(Webinar).where(Webinar.id==id,Webinar.foundation_id==p.foundation_id,Webinar.state=='ended'))
    enrollment=await db.scalar(select(WebinarEnrollment.id).where(WebinarEnrollment.webinar_id==id,WebinarEnrollment.foundation_id==p.foundation_id,WebinarEnrollment.user_id==p.user_id,WebinarEnrollment.state=='enrolled'))
    if not webinar or not enrollment:s.denied()
    row=await s.summary(db,id)
    if not row or not row.published_revision:s.denied()
    return s.revision_view(await s.revision(db,row,row.published_revision))
