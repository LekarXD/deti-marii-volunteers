from sqlalchemy import select
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.modules.applications.service import check_version
from .models import ReportDraft,ReportRevision
from .schemas import ReportView,ReportSummaryView,ReportRevisionView,ReportMetricsView,ReportSectionView
from .scopes import authorize_scope,report_filter
from .metrics import metrics,DEFINITIONS_VERSION
SECTION_LABELS={'done':'Что сделано','results':'Результаты','stories':'Истории участников','hard':'Трудности и что изменили'}
STORIES_NOTICE='Истории участников не включены в этот отчёт: подтверждённых источников для публикации нет.'

async def scoped_report(db,principal,report_id,permission='reports.read',lock=False):
    query=select(ReportDraft).where(ReportDraft.id==report_id,ReportDraft.foundation_id==principal.foundation_id)
    if lock:query=query.with_for_update()
    row=await db.scalar(query)
    if row is None:raise ApiError(404,'report_not_found','Отчёт не найден')
    await authorize_scope(db,principal,row.foundation_id,row.scope_type,row.scope_id)
    if permission!='reports.read':await authorize_scope(db,principal,row.foundation_id,row.scope_type,row.scope_id,permission)
    return row

async def summary_view(db,principal,row):
    scope=await authorize_scope(db,principal,row.foundation_id,row.scope_type,row.scope_id)
    return ReportSummaryView(id=row.id,title=row.title,kind=row.kind,state=row.state,version=row.version,scope=scope,period_from=row.period_from,period_to=row.period_to,updated_at=row.updated_at)

async def report_view(db,principal,row):
    scope=await authorize_scope(db,principal,row.foundation_id,row.scope_type,row.scope_id)
    revisions=(await db.scalars(select(ReportRevision).where(ReportRevision.report_id==row.id).order_by(ReportRevision.version.desc()).limit(100))).all()
    data=ReportMetricsView.model_validate(row.metrics_snapshot).model_copy(update={'scope':scope})
    return ReportView(id=row.id,title=row.title,kind=row.kind,state=row.state,version=row.version,scope=scope,period_from=row.period_from,period_to=row.period_to,metrics=data,sections=[ReportSectionView.model_validate(section) for section in row.sections],revisions=[ReportRevisionView(id=r.id,version=r.version,state=r.snapshot['state'],reason=r.reason,created_at=r.created_at) for r in revisions],created_at=row.created_at,updated_at=row.updated_at)

def snapshot(row):
    return dict(id=str(row.id),title=row.title,kind=row.kind,state=row.state,version=row.version,scope_type=row.scope_type,scope_id=str(row.scope_id) if row.scope_id else None,period_from=row.period_from.isoformat(),period_to=row.period_to.isoformat(),definitions_version=row.definitions_version,metrics=row.metrics_snapshot,sections=row.sections)

async def record_revision(db,principal,row,reason,*,increment=True):
    if increment:row.version+=1
    row.updated_at=utcnow();await db.flush()
    db.add(ReportRevision(report_id=row.id,version=row.version,snapshot=snapshot(row),reason=reason,actor_id=principal.actor_id));await db.flush()
    return await report_view(db,principal,row)

async def create_report(db,principal,command):
    await authorize_scope(db,principal,principal.foundation_id,command.scope_type,command.scope_id)
    await authorize_scope(db,principal,principal.foundation_id,command.scope_type,command.scope_id,'reports.write')
    data=await metrics(db,principal,principal.foundation_id,command.period_from,command.period_to,command.scope_type,command.scope_id)
    title=command.title.strip()
    if not title:raise ApiError(422,'report_title_required','Назовите отчёт')
    sections=[dict(key=key,title=label,text=STORIES_NOTICE if key=='stories' else '',confirmed=False,source='system' if key=='stories' else 'manual') for key,label in SECTION_LABELS.items()]
    row=ReportDraft(foundation_id=principal.foundation_id,scope_type=command.scope_type,scope_id=command.scope_id,kind=command.kind,title=title,period_from=command.period_from,period_to=command.period_to,definitions_version=DEFINITIONS_VERSION,metrics_snapshot=data.model_dump(mode='json'),source_hash=data.source_hash,sections=sections,state='draft',version=1,created_by=principal.user_id)
    db.add(row);await db.flush();return await record_revision(db,principal,row,'created',increment=False)

async def editable(db,principal,id,expected_version):
    row=await scoped_report(db,principal,id,'reports.write',True);check_version(row.version,expected_version)
    if row.state!='draft':raise ApiError(409,'report_not_draft','Сначала верните отчёт в черновик')
    return row

async def edit_section(db,principal,id,key,command):
    row=await editable(db,principal,id,command.expected_version)
    if key not in SECTION_LABELS:raise ApiError(404,'report_section_not_found','Раздел не найден')
    if command.text.count('\n')>200:raise ApiError(422,'report_section_too_many_lines','В разделе должно быть не больше 200 строк')
    if key=='stories':raise ApiError(409,'report_story_sources_unavailable','Для историй нужны подтверждённые источники публикации. Они пока не подключены.')
    sections=[dict(section) for section in row.sections]
    for section in sections:
        if section['key']==key:section.update(text=command.text.strip(),confirmed=False,source='manual')
    row.sections=sections;return await record_revision(db,principal,row,'section_edited')

async def decide_section(db,principal,id,key,command):
    row=await editable(db,principal,id,command.expected_version)
    if key not in SECTION_LABELS:raise ApiError(404,'report_section_not_found','Раздел не найден')
    sections=[dict(section) for section in row.sections]
    for section in sections:
        if section['key']==key:
            if command.decision=='confirm' and not section['text'].strip():raise ApiError(422,'report_section_empty','Сначала добавьте текст раздела')
            section['confirmed']=command.decision=='confirm'
    row.sections=sections;return await record_revision(db,principal,row,'section_'+command.decision)

async def refresh_metrics(db,principal,id,command):
    row=await editable(db,principal,id,command.expected_version)
    data=await metrics(db,principal,row.foundation_id,row.period_from,row.period_to,row.scope_type,row.scope_id)
    row.metrics_snapshot=data.model_dump(mode='json');row.source_hash=data.source_hash
    row.sections=[dict(section,confirmed=False) for section in row.sections]
    return await record_revision(db,principal,row,'metrics_refreshed')

async def confirm_report(db,principal,id,command):
    row=await editable(db,principal,id,command.expected_version)
    if not all(section['confirmed'] for section in row.sections):raise ApiError(409,'report_sections_unconfirmed','Проверьте и подтвердите все разделы')
    current=await metrics(db,principal,row.foundation_id,row.period_from,row.period_to,row.scope_type,row.scope_id)
    if current.source_hash!=row.source_hash:raise ApiError(409,'report_facts_changed','Подтверждённые факты изменились. Обновите показатели и проверьте текст заново.')
    row.state='confirmed';return await record_revision(db,principal,row,'confirmed')

async def reopen_report(db,principal,id,command):
    row=await scoped_report(db,principal,id,'reports.write',True);check_version(row.version,command.expected_version)
    if row.state!='confirmed':raise ApiError(409,'report_not_confirmed','Отчёт не находится в подтверждённом состоянии')
    row.state='draft';row.sections=[dict(section,confirmed=False) for section in row.sections]
    return await record_revision(db,principal,row,'reopened')
