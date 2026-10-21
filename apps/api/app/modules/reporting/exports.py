import asyncio
from sqlalchemy import select
from app.core.errors import ApiError
from app.modules.assets.registry import create_generated_asset
from .models import ReportRevision,ReportExport
from .schemas import ReportExportView,DobroPreviewView,DobroMappingColumn
from .service import scoped_report
from app.modules.applications.service import check_version
from .render import MIME,render
from . import assets
render_admission=asyncio.Semaphore(2)

def export_view(row):return ReportExportView(id=row.id,report_id=row.report_id,revision_id=row.revision_id,format=row.format,state=row.state,asset_id=row.asset_id,created_at=row.created_at)
async def create_export(db,principal,id,command):
    report=await scoped_report(db,principal,id,'reports.export',True);check_version(report.version,command.expected_version)
    if report.state!='confirmed':raise ApiError(409,'report_not_confirmed','Сначала подтвердите проверенный отчёт')
    revision=await db.scalar(select(ReportRevision).where(ReportRevision.report_id==report.id,ReportRevision.version==report.version))
    if revision is None:raise ApiError(409,'report_revision_missing','Не найдена подтверждённая версия')
    row=ReportExport(foundation_id=principal.foundation_id,report_id=report.id,revision_id=revision.id,format=command.format,created_by=principal.user_id,state='preparing');db.add(row);await db.flush()
    try:await asyncio.wait_for(render_admission.acquire(),timeout=1)
    except TimeoutError:raise ApiError(503,'report_renderer_busy','Подготовка файлов занята. Повторите попытку.',retryable=True)
    try:content=await asyncio.to_thread(render,revision.snapshot,command.format)
    finally:render_admission.release()
    asset=await create_generated_asset(db,principal,content_type=MIME[command.format],data=content,purpose='report_export',resource_type='report_export',resource_id=row.id)
    row.asset_id=asset.id;row.state='ready';await db.flush();return export_view(row)

async def dobro_preview(db,principal,id):
    report=await scoped_report(db,principal,id,'reports.export')
    from .schemas import ReportMetricsView
    facts=ReportMetricsView.model_validate(report.metrics_snapshot)
    return DobroPreviewView(reason='Формат и API Добро.рф для фонда пока не согласованы. Предпросмотр содержит внутренние подтверждённые факты; внешняя отправка недоступна.',mapping=[DobroMappingColumn(internal_key=key,label=label) for key,label in [('user_id','Волонтёр в Опоре'),('service_date','Дата помощи'),('delta_minutes','Подписанная разница минут'),('title','Вид помощи'),('id','Факт учёта')]],rows=facts.rows,total_minutes=sum(row.delta_minutes for row in facts.rows))
