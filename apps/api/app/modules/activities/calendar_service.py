from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from app.core.db import Base
from app.core.errors import ApiError
from app.core.idempotency import payload_hash
from app.modules.participants.models import ParticipantGroup
from .calendar_models import EventOccurrence, EventRevision, EventSeries, EventSeriesNeedTemplate, OccurrenceOverride, StaffingNeed
from .calendar_schemas import EventOccurrenceView, EventSeriesCreate, EventSeriesView, RecurrenceRule, SeriesChangePreview, StaffingNeedView
from .models import VolunteerRoleVersion
from .recurrence import dates_in_range, local_interval, occurrence_id
from .service import check_version, role_snapshots

CONTENT=('title','program','kind','format','location','audience','group_id')
SERIES_FIELDS=(*CONTENT,'start_date','start_time','timezone','duration_minutes','recurrence')


async def lock_group(db,foundation_id,group_id):
    if group_id is not None:
        lock=int(payload_hash(['calendar-group',str(foundation_id),str(group_id)])[:15],16)
        await db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':lock})


async def validate_group(db,principal,group_id):
    if group_id is not None:
        group=await db.scalar(select(ParticipantGroup).where(ParticipantGroup.id==group_id,ParticipantGroup.foundation_id==principal.foundation_id,ParticipantGroup.lifecycle=='active'))
        if group is None:raise ApiError(422,'invalid_group','Выберите действующую группу своего фонда.')


async def series(db,principal,id,lock=False):
    query=select(EventSeries).where(EventSeries.id==id,EventSeries.foundation_id==principal.foundation_id)
    entity=await db.scalar(query.with_for_update() if lock else query)
    if entity is None:raise ApiError(404,'series_not_found','Серия не найдена.')
    return entity


async def occurrence(db,principal,id,lock=False):
    query=select(EventOccurrence).where(EventOccurrence.id==id,EventOccurrence.foundation_id==principal.foundation_id)
    entity=await db.scalar(query.with_for_update() if lock else query)
    if entity is None:raise ApiError(404,'occurrence_not_found','Занятие не найдено.')
    return entity


async def count_assignments(db,need_id):
    table=Base.metadata.tables.get('assignments')
    if table is None:return 0,0
    rows=(await db.execute(select(table.c.status,func.count()).where(table.c.staffing_need_id==need_id).group_by(table.c.status))).all()
    counts=dict(rows)
    return counts.get('invited',0),counts.get('confirmed',0)


async def needs_view(db,entity):
    needs=(await db.scalars(select(StaffingNeed).where(StaffingNeed.occurrence_id==entity.id).order_by(StaffingNeed.id))).all()
    result=[]
    for need in needs:
        revision=await db.get(VolunteerRoleVersion,need.role_version_id)
        invited,confirmed=await count_assignments(db,need.id)
        result.append(StaffingNeedView(id=need.id,role_id=need.role_id,role_version_id=need.role_version_id,
            role_title=revision.snapshot['title'],version=need.version,required=need.capacity_required,invited=invited,
            confirmed=confirmed,missing=max(0,need.capacity_required-confirmed),preparation_requirements=need.preparation_requirements,approval_policy=need.approval_policy))
    return result


async def occurrence_view(db,entity):
    overridden=await db.get(OccurrenceOverride,entity.id)
    fields={field:getattr(entity,field) for field in EventOccurrenceView.model_fields if field not in ('has_override','staffing_needs','allowed_actions')}
    return EventOccurrenceView(**fields,has_override=overridden is not None,staffing_needs=await needs_view(db,entity),
        allowed_actions=['edit','copy','cancel' if entity.status=='scheduled' else 'restore'] if entity.status!='completed' else ['copy'])


async def series_view(db,entity):
    templates=(await db.scalars(select(EventSeriesNeedTemplate).where(EventSeriesNeedTemplate.series_id==entity.id,EventSeriesNeedTemplate.active.is_(True)).order_by(EventSeriesNeedTemplate.id))).all()
    fields={field:getattr(entity,field) for field in SERIES_FIELDS}
    return EventSeriesView(**fields,id=entity.id,state=entity.state,version=entity.version,
        staffing_needs=[{'role_id':t.role_id,'capacity_required':t.capacity_required,'preparation_requirements':t.preparation_requirements,'approval_policy':t.approval_policy} for t in templates],allowed_actions=['preview-change','cancel' if entity.state=='active' else 'restore'])


async def record(db,principal,entity,kind):
    await db.flush()
    snapshot=(await series_view(db,entity) if kind=='series' else await occurrence_view(db,entity)).model_dump(mode='json')
    db.add(EventRevision(foundation_id=principal.foundation_id,entity_type=kind,entity_id=entity.id,version=entity.version,snapshot=snapshot,actor_id=principal.actor_id))


def projected(entity,lower,upper):
    rule=RecurrenceRule.model_validate(entity.recurrence)
    offset=entity.start_date-entity.anchor_date
    for day in dates_in_range(entity.start_date,rule,lower,upper):
        interval=local_interval(day,entity.start_time,entity.timezone,entity.duration_minutes)
        if interval is None:continue
        origin=day-offset
        yield dict(id=occurrence_id(entity.id,origin,entity.origin_time),foundation_id=entity.foundation_id,series_id=entity.id,
            origin_local_date=origin,origin_local_time=entity.origin_time,starts_at=interval[0],ends_at=interval[1],timezone=entity.timezone,
            **{field:getattr(entity,field) for field in CONTENT},status='scheduled' if entity.state=='active' else 'cancelled',series_version=entity.version,version=1,updated_by=entity.updated_by)


async def add_need_from_template(db,entity,template):
    db.add(StaffingNeed(occurrence_id=entity.id,foundation_id=entity.foundation_id,template_id=template.id,role_id=template.role_id,role_version_id=template.role_version_id,
        capacity_required=template.capacity_required,preparation_requirements=template.preparation_requirements,approval_policy=template.approval_policy))


async def materialize(db,entity,lower,upper):
    # Derivative projection; serializing the source avoids racing a series edit.
    templates=(await db.scalars(select(EventSeriesNeedTemplate).where(EventSeriesNeedTemplate.series_id==entity.id,EventSeriesNeedTemplate.active.is_(True)))).all()
    for values in projected(entity,lower,upper):
        created=await db.scalar(insert(EventOccurrence).values(**values).on_conflict_do_nothing(index_elements=['id']).returning(EventOccurrence.id))
        if created:
            item=await db.get(EventOccurrence,created)
            for template in templates:await add_need_from_template(db,item,template)
    await db.flush()


async def update_templates(db,principal,entity,inputs):
    existing={r.role_id:r for r in (await db.scalars(select(EventSeriesNeedTemplate).where(EventSeriesNeedTemplate.series_id==entity.id))).all()}
    new_ids={row.role_id for row in inputs}
    # Only new role references must be active; retaining historical archived roles is safe.
    new_roles=await role_snapshots(db,principal,list(new_ids-set(existing))) if new_ids-set(existing) else []
    by_id={r.id:r for r in new_roles}
    for row in inputs:
        template=existing.get(row.role_id)
        if template is None:
            role=by_id[row.role_id]
            revision=await db.scalar(select(VolunteerRoleVersion).where(VolunteerRoleVersion.role_id==role.id,VolunteerRoleVersion.version==role.version))
            template=EventSeriesNeedTemplate(series_id=entity.id,foundation_id=entity.foundation_id,role_id=role.id,role_version_id=revision.id,capacity_required=row.capacity_required,
                preparation_requirements=row.model_dump(mode='json')['preparation_requirements'] if row.preparation_requirements is not None else role.preparation_defaults,
                approval_policy=row.approval_policy or role.approval_policy)
            db.add(template)
        else:
            template.capacity_required=row.capacity_required
            if row.preparation_requirements is not None:template.preparation_requirements=row.model_dump(mode='json')['preparation_requirements']
            if row.approval_policy is not None:template.approval_policy=row.approval_policy
            template.active=True
    for role_id,template in existing.items():
        if role_id not in new_ids:template.active=False
    await db.flush()


async def create_series(db,principal,body):
    await validate_group(db,principal,body.group_id)
    await lock_group(db,principal.foundation_id,body.group_id)
    if local_interval(body.start_date,body.start_time,body.timezone,body.duration_minutes) is None:
        raise ApiError(422,'nonexistent_local_time','Такого локального времени нет при переходе на летнее время.')
    fields={name:getattr(body,name) for name in SERIES_FIELDS}
    fields['recurrence']=body.recurrence.model_dump(mode='json')
    entity=EventSeries(**fields,foundation_id=principal.foundation_id,anchor_date=body.start_date,origin_time=body.start_time,updated_by=principal.actor_id)
    db.add(entity);await db.flush()
    await update_templates(db,principal,entity,body.staffing_needs)
    for values in projected(entity,body.start_date,body.start_date+timedelta(days=183)):
        if await group_conflicts(db,principal,values):raise ApiError(409,'calendar_conflict','У группы уже есть занятие в это время.')
    await materialize(db,entity,body.start_date,body.start_date+timedelta(days=183))
    await record(db,principal,entity,'series')
    return await series_view(db,entity)


async def group_conflicts(db,principal,values,exclude_ids=()):
    if values['group_id'] is None:return []
    query=select(EventOccurrence.id).where(EventOccurrence.foundation_id==principal.foundation_id,EventOccurrence.group_id==values['group_id'],EventOccurrence.status=='scheduled',
        EventOccurrence.starts_at<values['ends_at'],EventOccurrence.ends_at>values['starts_at'])
    if exclude_ids:query=query.where(EventOccurrence.id.not_in(exclude_ids))
    return [{'kind':'group_overlap','occurrence_id':str(id)} for id in (await db.scalars(query)).all()]


async def patch_occurrence(db,principal,id,body):
    before=await occurrence(db,principal,id)
    for group_id in sorted({g for g in (before.group_id,body.group_id) if g},key=str):await lock_group(db,principal.foundation_id,group_id)
    item=await occurrence(db,principal,id,True);check_version(item,body.expected_version)
    if item.status!='scheduled':raise ApiError(409,'occurrence_not_scheduled','Сначала восстановите занятие.')
    await validate_group(db,principal,body.group_id)
    await lock_group(db,principal.foundation_id,body.group_id)
    values=body.model_dump(exclude={'expected_version'})
    conflicts=await group_conflicts(db,principal,values,[id])
    if conflicts:raise ApiError(409,'calendar_conflict','У группы уже есть занятие в это время.',field_errors={'starts_at':'Занятия пересекаются.'})
    for name,value in values.items():setattr(item,name,value)
    override=await db.get(OccurrenceOverride,id)
    fields={name:value.isoformat() if hasattr(value,'isoformat') else str(value) if isinstance(value,UUID) else value for name,value in values.items()}
    if override is None:db.add(OccurrenceOverride(occurrence_id=id,fields=fields,updated_by=principal.actor_id))
    else:override.fields={**override.fields,**fields};override.version+=1;override.updated_at=datetime.now(timezone.utc);override.updated_by=principal.actor_id
    item.version+=1;item.updated_at=datetime.now(timezone.utc);item.updated_by=principal.actor_id
    await record(db,principal,item,'occurrence')
    return await occurrence_view(db,item)


async def change_occurrence_state(db,principal,id,body,state):
    before=await occurrence(db,principal,id)
    await lock_group(db,principal.foundation_id,before.group_id)
    item=await occurrence(db,principal,id,True);check_version(item,body.expected_version)
    if item.status=='completed' or item.status==state:raise ApiError(409,'occurrence_state_conflict','Состояние занятия изменилось.')
    await lock_group(db,principal.foundation_id,item.group_id)
    if state=='scheduled' and await group_conflicts(db,principal,{'group_id':item.group_id,'starts_at':item.starts_at,'ends_at':item.ends_at},[id]):
        raise ApiError(409,'calendar_conflict','У группы уже есть занятие в это время.')
    override=await db.get(OccurrenceOverride,id)
    if override is None:db.add(OccurrenceOverride(occurrence_id=id,fields={'status':state},updated_by=principal.actor_id))
    else:override.fields={**override.fields,'status':state};override.version+=1;override.updated_at=datetime.now(timezone.utc);override.updated_by=principal.actor_id
    item.status=state;item.cancellation_source='manual' if state=='cancelled' else None;item.version+=1;item.updated_at=datetime.now(timezone.utc);item.updated_by=principal.actor_id
    await record(db,principal,item,'occurrence')
    return await occurrence_view(db,item)


async def patch_staffing(db,principal,id,body):
    item=await occurrence(db,principal,id,True);check_version(item,body.expected_version)
    existing={n.role_id:n for n in (await db.scalars(select(StaffingNeed).where(StaffingNeed.occurrence_id==id).order_by(StaffingNeed.id).with_for_update())).all()}
    if len({n.role_id for n in body.staffing_needs})!=len(body.staffing_needs):raise ApiError(422,'duplicate_role','Для одной роли создайте одну потребность.')
    incoming={row.role_id:row for row in body.staffing_needs}
    for role_id,need in existing.items():
        invited,confirmed=await count_assignments(db,need.id)
        capacity=incoming[role_id].capacity_required if role_id in incoming else 0
        if capacity<confirmed:raise ApiError(409,'capacity_below_confirmed','Сначала пересогласуйте подтверждённую команду.')
        if role_id not in incoming:
            # A zero-capacity retained row preserves the assignment/history FK.
            need.capacity_required=0;need.version+=1
    new_roles=await role_snapshots(db,principal,list(set(incoming)-set(existing))) if set(incoming)-set(existing) else []
    by_id={r.id:r for r in new_roles}
    for row in body.staffing_needs:
        need=existing.get(row.role_id)
        if need is None:
            role=by_id[row.role_id]
            revision=await db.scalar(select(VolunteerRoleVersion).where(VolunteerRoleVersion.role_id==role.id,VolunteerRoleVersion.version==role.version))
            need=StaffingNeed(occurrence_id=id,foundation_id=principal.foundation_id,role_id=role.id,role_version_id=revision.id,capacity_required=row.capacity_required,
                preparation_requirements=row.model_dump(mode='json')['preparation_requirements'] if row.preparation_requirements is not None else role.preparation_defaults,approval_policy=row.approval_policy or role.approval_policy)
            db.add(need)
        else:
            need.capacity_required=row.capacity_required;need.version+=1
            if row.preparation_requirements is not None:need.preparation_requirements=row.model_dump(mode='json')['preparation_requirements']
            if row.approval_policy is not None:need.approval_policy=row.approval_policy
    override=await db.get(OccurrenceOverride,id)
    if override is None:db.add(OccurrenceOverride(occurrence_id=id,fields={'staffing_needs':True},updated_by=principal.actor_id))
    else:override.fields={**override.fields,'staffing_needs':True};override.version+=1
    item.version+=1;item.updated_at=datetime.now(timezone.utc);item.updated_by=principal.actor_id
    await record(db,principal,item,'occurrence')
    return await occurrence_view(db,item)


def proposed_series(entity,body):
    from types import SimpleNamespace
    values={column.name:getattr(entity,column.name) for column in EventSeries.__table__.columns}
    values.update({name:getattr(body,name) for name in SERIES_FIELDS})
    values['recurrence']=body.recurrence.model_dump(mode='json')
    return SimpleNamespace(**values)


async def preview_change(db,principal,id,body,lock=False):
    entity=await series(db,principal,id,lock);check_version(entity,body.expected_version)
    await validate_group(db,principal,body.group_id)
    future_query=select(EventOccurrence).where(EventOccurrence.series_id==id,EventOccurrence.ends_at>=datetime.now(timezone.utc)).order_by(EventOccurrence.id)
    future=list((await db.scalars(future_query.with_for_update() if lock else future_query)).all())
    lower=datetime.now(timezone.utc).date()
    upper=max([lower+timedelta(days=183),*(r.starts_at.date()+timedelta(days=2) for r in future)])
    prospective=proposed_series(entity,body)
    desired={row['id']:row for row in projected(prospective,lower,upper)}
    overridden=set((await db.scalars(select(OccurrenceOverride.occurrence_id).where(OccurrenceOverride.occurrence_id.in_([r.id for r in future])))).all()) if future else set()
    affected=[r for r in future if r.id not in overridden and r.status!='completed']
    conflicts=[];reconfirm=[]
    all_ids=[r.id for r in affected]
    for values in desired.values():
        if values['id'] not in overridden:
            conflicts.extend(await group_conflicts(db,principal,values,all_ids))
    incoming={n.role_id:n for n in body.staffing_needs}
    for item in affected:
        needs=(await db.scalars(select(StaffingNeed).where(StaffingNeed.occurrence_id==item.id))).all()
        for need in needs:
            invited,confirmed=await count_assignments(db,need.id)
            target=incoming.get(need.role_id)
            if confirmed and (target is None or target.capacity_required<confirmed):conflicts.append({'kind':'capacity_below_confirmed','occurrence_id':str(item.id),'staffing_need_id':str(need.id)})
            values=desired.get(item.id)
            if confirmed and (values is None or any(getattr(item,key)!=values[key] for key in ('starts_at','ends_at','location','group_id'))):reconfirm.append(item.id)
    signature={'series_version':entity.version,'body':body.model_dump(mode='json',exclude={'preview_hash'}),'occurrences':[(str(r.id),r.version) for r in future], 'conflicts':conflicts,'reconfirm':sorted(str(i) for i in set(reconfirm))}
    preview=SeriesChangePreview(series_id=id,expected_version=entity.version,preview_hash=payload_hash(signature),affected_occurrence_ids=[r.id for r in affected],retained_override_ids=sorted(overridden),conflicts=conflicts,needs_reconfirmation_ids=sorted(set(reconfirm)),can_apply=not conflicts and not reconfirm)
    return preview,entity,future,desired,overridden


async def sync_needs(db,entity,templates):
    existing={n.role_id:n for n in (await db.scalars(select(StaffingNeed).where(StaffingNeed.occurrence_id==entity.id))).all()}
    active={t.role_id:t for t in templates if t.active}
    for role_id,need in existing.items():
        if role_id not in active:
            if need.capacity_required:need.capacity_required=0;need.version+=1
        else:
            t=active[role_id]
            if (need.capacity_required,need.preparation_requirements,need.approval_policy)!=(t.capacity_required,t.preparation_requirements,t.approval_policy):
                need.capacity_required=t.capacity_required;need.preparation_requirements=t.preparation_requirements;need.approval_policy=t.approval_policy;need.version+=1
    for role_id,template in active.items():
        if role_id not in existing:await add_need_from_template(db,entity,template)


async def apply_change(db,principal,id,body):
    before=await series(db,principal,id)
    for group_id in sorted({g for g in (before.group_id,body.group_id) if g},key=str):await lock_group(db,principal.foundation_id,group_id)
    preview,entity,future,desired,overridden=await preview_change(db,principal,id,body,True)
    if preview.preview_hash!=body.preview_hash:raise ApiError(409,'preview_changed','Состав или расписание изменились. Проверьте изменения ещё раз.',current_version=entity.version)
    if not preview.can_apply:raise ApiError(409,'calendar_conflict','Сначала устраните пересечения и пересогласуйте подтверждённые назначения.')
    for field in SERIES_FIELDS:setattr(entity,field,getattr(body,field) if field!='recurrence' else body.recurrence.model_dump(mode='json'))
    entity.version+=1;entity.updated_by=principal.actor_id;entity.updated_at=datetime.now(timezone.utc)
    await update_templates(db,principal,entity,body.staffing_needs)
    templates=(await db.scalars(select(EventSeriesNeedTemplate).where(EventSeriesNeedTemplate.series_id==id))).all()
    existing_ids={item.id for item in future}
    for item in future:
        if item.id in overridden or item.status=='completed':continue
        values=desired.get(item.id)
        if values:
            for field in (*CONTENT,'starts_at','ends_at','timezone','status'):setattr(item,field,values[field])
            item.cancellation_source=None
            await sync_needs(db,item,templates)
        else:item.status='cancelled';item.cancellation_source='series_change'
        item.series_version=entity.version;item.version+=1;item.updated_at=datetime.now(timezone.utc);item.updated_by=principal.actor_id
        await record(db,principal,item,'occurrence')
    for id,values in desired.items():
        if id not in existing_ids:
            values['series_version']=entity.version
            item=EventOccurrence(**values);db.add(item);await db.flush()
            for template in templates:
                if template.active:await add_need_from_template(db,item,template)
    await record(db,principal,entity,'series')
    return await series_view(db,entity)


async def change_series_state(db,principal,id,body,state):
    before=await series(db,principal,id)
    await lock_group(db,principal.foundation_id,before.group_id)
    entity=await series(db,principal,id,True);check_version(entity,body.expected_version)
    if entity.state==state:raise ApiError(409,'series_state_conflict','Состояние серии уже изменилось.')
    await lock_group(db,principal.foundation_id,entity.group_id)
    future=list((await db.scalars(select(EventOccurrence).where(EventOccurrence.series_id==id,EventOccurrence.ends_at>=datetime.now(timezone.utc)).order_by(EventOccurrence.id).with_for_update())).all())
    for item in future:
        if item.status=='completed':continue
        if state=='active' and item.cancellation_source=='series':
            if await group_conflicts(db,principal,{'group_id':item.group_id,'starts_at':item.starts_at,'ends_at':item.ends_at},[r.id for r in future]):raise ApiError(409,'calendar_conflict','При восстановлении найдено пересечение занятий группы.')
            item.status='scheduled';item.cancellation_source=None
        elif state=='cancelled' and item.status=='scheduled':item.status='cancelled';item.cancellation_source='series'
        else:continue
        item.version+=1;item.updated_by=principal.actor_id;item.updated_at=datetime.now(timezone.utc)
        await record(db,principal,item,'occurrence')
    entity.state=state;entity.version+=1;entity.updated_by=principal.actor_id;entity.updated_at=datetime.now(timezone.utc)
    await record(db,principal,entity,'series')
    return await series_view(db,entity)
