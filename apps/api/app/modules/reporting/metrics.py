"""One canonical rowset builds screen totals, definitions and export evidence."""
from collections import defaultdict
from datetime import timedelta
from sqlalchemy import select,func
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.idempotency import payload_hash
from app.core.models import User
from app.modules.profile.models import ServiceTimeEntry
from app.modules.activities.assignment_models import Assignment
from app.modules.participants.models import ParticipantGroup
from app.modules.profile.dates import local_today
from .scopes import authorize_scope
from .schemas import ReportMetricsView,ReportMetricView,ReportFactView
DEFINITIONS_VERSION='reports-v1'
MAX_FACTS=50000

async def metrics(db,authority,foundation_id,period_from,period_to,scope_type='foundation',scope_id=None):
    scope=await authorize_scope(db,authority,foundation_id,scope_type,scope_id)
    if period_to<period_from or (period_to-period_from).days>1826:raise ApiError(422,'invalid_report_period','Выберите период до пяти лет')
    if period_to>local_today():raise ApiError(422,'future_report_period','Фактический отчёт не включает будущие даты')
    cohort_start=period_from-timedelta(days=90)
    query=select(ServiceTimeEntry,User.display_name,Assignment.occurrence_id,Assignment.group_id_snapshot,ParticipantGroup.title).join(User,User.id==ServiceTimeEntry.user_id).outerjoin(Assignment,Assignment.id==ServiceTimeEntry.assignment_id).outerjoin(ParticipantGroup,ParticipantGroup.id==Assignment.group_id_snapshot).where(ServiceTimeEntry.foundation_id==foundation_id,User.foundation_id==foundation_id,ServiceTimeEntry.service_date>=cohort_start,ServiceTimeEntry.service_date<=period_to)
    # Older history only decides who already had a first visit, so it is aggregated instead of loaded.
    prior=select(ServiceTimeEntry.user_id).join(User,User.id==ServiceTimeEntry.user_id).join(Assignment,Assignment.id==ServiceTimeEntry.assignment_id).where(ServiceTimeEntry.foundation_id==foundation_id,User.foundation_id==foundation_id,ServiceTimeEntry.service_date<cohort_start).group_by(ServiceTimeEntry.assignment_id,ServiceTimeEntry.user_id).having(func.sum(ServiceTimeEntry.delta_minutes)>0)
    if scope_type=='group':
        query=query.where(Assignment.foundation_id==foundation_id,Assignment.group_id_snapshot==scope_id)
        prior=prior.where(Assignment.foundation_id==foundation_id,Assignment.group_id_snapshot==scope_id)
    records=(await db.execute(query.order_by(ServiceTimeEntry.service_date,ServiceTimeEntry.created_at,ServiceTimeEntry.id).limit(MAX_FACTS+1))).all()
    if len(records)>MAX_FACTS:raise ApiError(413,'report_fact_budget_exceeded','Объём данных превышает лимит этого отчёта. Подготовьте отчёт по отдельной группе.')
    facts=[ReportFactView(id=row.id,user_id=row.user_id,display_name=name,service_date=row.service_date,title=row.title,delta_minutes=row.delta_minutes,assignment_id=row.assignment_id,occurrence_id=occurrence,group_id=group,group_title=group_title,source_kind=row.source_kind,source_id=row.source_id,source_revision=row.source_revision) for row,name,occurrence,group,group_title in records]
    rows=[fact for fact in facts if period_from<=fact.service_date<=period_to]
    people=defaultdict(int);assignments=defaultdict(int);occurrences={};source_net=defaultdict(int);source_meta={}
    for fact in rows:
        people[fact.user_id]+=fact.delta_minutes
        if fact.assignment_id:
            assignments[fact.assignment_id]+=fact.delta_minutes;occurrences[fact.assignment_id]=fact.occurrence_id
    # Corrections retain the original service date, so each source has one net fact.
    for fact in facts:
        if fact.assignment_id:
            source_net[fact.assignment_id]+=fact.delta_minutes;source_meta[fact.assignment_id]=(fact.user_id,fact.service_date)
    visits=defaultdict(list)
    for assignment_id,net in source_net.items():
        if net>0:
            user_id,day=source_meta[assignment_id];visits[user_id].append(day)
    earlier=set((await db.scalars(select(prior.subquery().c.user_id).distinct())).all())&visits.keys()
    cohort={user_id:min(days) for user_id,days in visits.items() if user_id not in earlier and cohort_start<=min(days)<period_from and min(days)+timedelta(days=90)<=period_to}
    retained=sum(any(max(period_from,first+timedelta(days=90))<=day<=period_to for day in visits[user_id]) for user_id,first in cohort.items())
    retention=round(retained*100/len(cohort),1) if cohort else None
    values=[
        ReportMetricView(key='children_attended',label='Детей на занятиях',value=None,unit='человек',definition='Уникальные участники по индивидуальным подтверждённым отметкам присутствия за период.',status='unavailable',reason='Индивидуальные отметки присутствия участников пока не ведутся. Состав группы не подтверждает посещение.'),
        ReportMetricView(key='held_occurrences',label='Занятий с подтверждённой помощью',value=len({occurrences[id] for id,net in assignments.items() if net>0}),unit='занятий',definition='Разные занятия, у которых есть хотя бы одно назначение с положительным итогом подтверждённых минут в выбранном периоде и области.',status='available'),
        ReportMetricView(key='volunteer_minutes',label='Минут волонтёрской помощи',value=sum(f.delta_minutes for f in rows),unit='минут',definition='Сумма всех подписанных разниц минут канонического журнала по дате помощи. Коррекции вычитаются. Ожидающие подтверждения запросы не включены; в группе учтены только назначения этой группы.',status='available'),
        ReportMetricView(key='retention_90',label='Продолжают спустя 90 дней',value=retention,unit='%',definition='По наблюдаемой истории системы: первое подтверждённое занятие в этой области за 90 дней до начала периода и повторное занятие в периоде не раньше чем через 90 дней после первого. Только созревшая когорта; ручные часы не считаются занятиями.',status='available' if cohort else 'empty',reason='' if cohort else 'В наблюдаемой истории нет созревшей когорты.',numerator=retained,denominator=len(cohort)),
        ReportMetricView(key='active_volunteers',label='Волонтёров с подтверждённой помощью',value=sum(net>0 for net in people.values()),unit='человек',definition='Разные пользователи с положительным итогом подтверждённых минут в выбранном периоде и области.',status='available'),
    ]
    refs=[dict(id=str(f.id),source_kind=f.source_kind,source_id=str(f.source_id),source_revision=f.source_revision,delta_minutes=f.delta_minutes,service_date=f.service_date.isoformat()) for f in facts]
    source_hash=payload_hash(dict(definitions_version=DEFINITIONS_VERSION,period_from=period_from,period_to=period_to,scope_type=scope_type,scope_id=scope_id,metrics=[v.model_dump(mode='json') for v in values],facts=[fact.model_dump(mode='json') for fact in facts],earlier_visitors=sorted(map(str,earlier))))
    return ReportMetricsView(definitions_version=DEFINITIONS_VERSION,period_from=period_from,period_to=period_to,scope=scope,metrics=values,rows=rows,source_refs=refs,source_hash=source_hash,generated_at=utcnow())
