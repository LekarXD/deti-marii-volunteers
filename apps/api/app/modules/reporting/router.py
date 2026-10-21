from datetime import date
from uuid import UUID
from fastapi import APIRouter,Depends,Header,Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal,authz_guard
from app.core.db import get_db
from app.core.audit import audit
from app.core.errors import ApiError
from app.core.idempotency import begin_command,finish_command
from . import schemas as dto,service,exports
from .metrics import metrics
from .models import ReportDraft,ReportExport
from .scopes import scope_options,authorize_scope,report_filter
router=APIRouter(prefix='/api/v1',tags=['reporting'])

async def command(db,principal,operation,key,body,action,*,id=None,permission='reports.write'):
    await authz_guard(db,principal)
    if id is not None:await service.scoped_report(db,principal,id,permission)
    else:
        await authorize_scope(db,principal,principal.foundation_id,body.scope_type,body.scope_id)
        await authorize_scope(db,principal,principal.foundation_id,body.scope_type,body.scope_id,permission)
    prior=await begin_command(db,principal,operation,key,body.model_dump(mode='json'))
    if prior is not None:await db.commit();return prior
    result=await action();result=result.model_dump(mode='json') if hasattr(result,'model_dump') else result
    audit(db,principal,operation,'report',result.get('id',id or ''),body.model_dump().keys())
    await finish_command(db,principal,operation,key,result);await db.commit();return result

@router.get('/coord/reports/scopes',response_model=list[dto.ReportScopeView])
async def scopes(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await scope_options(db,principal)
@router.get('/coord/reports/metrics',response_model=dto.ReportMetricsView)
async def current_metrics(period_from:date,period_to:date,scope_type:str='foundation',scope_id:UUID|None=None,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await metrics(db,principal,principal.foundation_id,period_from,period_to,scope_type,scope_id)
@router.get('/coord/reports',response_model=list[dto.ReportSummaryView])
async def reports(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    rows=(await db.scalars(select(ReportDraft).where(report_filter(ReportDraft,principal)).order_by(ReportDraft.updated_at.desc(),ReportDraft.id).limit(100))).all()
    return [await service.summary_view(db,principal,row) for row in rows]
@router.post('/coord/reports',response_model=dto.ReportView)
async def create_report(body:dto.ReportCreateCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,'report.create',idempotency_key,body,lambda:service.create_report(db,principal,body))
@router.get('/coord/reports/{id}',response_model=dto.ReportView)
async def report(id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.report_view(db,principal,await service.scoped_report(db,principal,id))
@router.put('/coord/reports/{id}/sections/{key}',response_model=dto.ReportView)
async def edit_section(id:UUID,key:str,body:dto.ReportSectionCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'report.section.edit:{id}:{key}',idempotency_key,body,lambda:service.edit_section(db,principal,id,key,body),id=id)
@router.post('/coord/reports/{id}/sections/{key}/decision',response_model=dto.ReportView)
async def section_decision(id:UUID,key:str,body:dto.ReportSectionDecisionCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'report.section.decision:{id}:{key}',idempotency_key,body,lambda:service.decide_section(db,principal,id,key,body),id=id)
@router.post('/coord/reports/{id}/refresh',response_model=dto.ReportView)
async def refresh(id:UUID,body:dto.ReportVersionCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'report.refresh:{id}',idempotency_key,body,lambda:service.refresh_metrics(db,principal,id,body),id=id)
@router.post('/coord/reports/{id}/confirm',response_model=dto.ReportView)
async def confirm(id:UUID,body:dto.ReportVersionCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'report.confirm:{id}',idempotency_key,body,lambda:service.confirm_report(db,principal,id,body),id=id)
@router.post('/coord/reports/{id}/reopen',response_model=dto.ReportView)
async def reopen(id:UUID,body:dto.ReportVersionCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'report.reopen:{id}',idempotency_key,body,lambda:service.reopen_report(db,principal,id,body),id=id)
@router.post('/coord/reports/{id}/exports',response_model=dto.ReportExportView)
async def create_export(id:UUID,body:dto.ReportExportCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,f'report.export:{id}',idempotency_key,body,lambda:exports.create_export(db,principal,id,body),id=id,permission='reports.export')
@router.get('/coord/reports/{id}/exports',response_model=list[dto.ReportExportView])
async def export_list(id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    await service.scoped_report(db,principal,id,'reports.export')
    rows=(await db.scalars(select(ReportExport).where(ReportExport.report_id==id,ReportExport.foundation_id==principal.foundation_id).order_by(ReportExport.created_at.desc()).limit(100))).all()
    return [exports.export_view(row) for row in rows]
@router.get('/coord/reports/{id}/dobro-preview',response_model=dto.DobroPreviewView)
async def dobro_preview(id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await exports.dobro_preview(db,principal,id)

from . import digests
@router.get('/coord/report-digests/recipient-options',response_model=list[dto.ReportDigestRecipientView])
async def digest_recipients(scope_type:str='foundation',scope_id:UUID|None=None,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await digests.recipient_options(db,principal,scope_type,scope_id)
@router.get('/coord/report-digests',response_model=dto.ReportDigestView)
async def digest(scope_type:str='foundation',scope_id:UUID|None=None,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await digests.digest_view(db,principal,scope_type,scope_id)
@router.put('/coord/report-digests',response_model=dto.ReportDigestView)
async def save_digest(body:dto.ReportDigestCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await command(db,principal,'report.digest.save',idempotency_key,body,lambda:digests.save_schedule(db,principal,body))
