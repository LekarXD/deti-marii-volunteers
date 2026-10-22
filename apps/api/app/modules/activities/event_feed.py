"""Volunteer event feed: open places on scheduled occurrences, ordered by ranking.py.

The score orders the list and is never returned. A volunteer sees role counts,
never other volunteers, and only their own assignment and reserve rows.
"""
from datetime import datetime,timedelta,timezone
from sqlalchemy import func,select
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.models import ResourceReservation,User
from .assignment_models import Assignment,StaffingNeedReserve
from .assignment_service import readiness,require_user,reserve_view,sign_up_gate
from .calendar_models import EventOccurrence,EventSeries,StaffingNeed
from .calendar_service import materialize
from .event_feed_schemas import (EventContact,VolunteerEventAssignment,VolunteerEventCard,VolunteerEventDate,VolunteerEventDetail,VolunteerEventFeed,VolunteerEventNeed,
    VolunteerReadiness,VolunteerReserveItem,VolunteerReservePage)
from .models import VolunteerRoleVersion
from . import ranking

FEED_MAX_DAYS=92
OTHER_DATES=4


def plural(n,one,few,many):
    n=abs(n)%100
    if 10<n<20:return many
    n%=10
    return one if n==1 else few if 2<=n<=4 else many


def reason_text(reason):
    if reason.code=='skill':return f'Навык «{reason.value}» из твоей анкеты'
    if reason.code=='direction':return f'Направление «{reason.value}» из твоей анкеты'
    if reason.code=='unknown_direction':return 'В анкете отмечено «Пока не знаю» — можно попробовать'
    if reason.code=='familiar':return f'{reason.count} {plural(reason.count,"занятие","занятия","занятий")} с этой группой за полгода'
    if reason.code=='familiar_new':return 'Группа уже знакома тебе'
    if reason.code=='time_history':return f'Обычно ты приходишь в это время: {reason.value}'
    if reason.code=='time_window':return f'Удобно по твоему графику: {reason.value}'
    return ''


async def own_readiness(db,foundation_id,user_id,requirements,assignment=None):
    """The volunteer's own preparation: coordinator reviews on their assignment win, else version-bound learning evidence."""
    if assignment is not None:
        return [VolunteerReadiness(key=row.key,title=row.title,level=row.level,state='pending' if row.state=='pending' else 'fulfilled') for row in await readiness(db,assignment)]
    try:
        from app.modules.learning.service import requirement_status
    except ModuleNotFoundError as exc:
        if not exc.name.startswith('app.modules.learning'):raise
        requirement_status=None
    result=[]
    for row in requirements:
        status=await requirement_status(db,foundation_id,user_id,row['key']) if requirement_status else None
        result.append(VolunteerReadiness(key=row['key'],title=row['title'],level=row.get('level','recommended'),state='fulfilled' if status and status['status']=='fulfilled' else 'pending'))
    return result


async def event_contacts(db,foundation_id,group_id):
    """Same people the first-exit memo names: the group's active leader and coordinator."""
    if group_id is None:return []
    from app.modules.followups.service import owner_eligible
    from app.modules.participants.models import ParticipantGroup
    group=await db.get(ParticipantGroup,group_id)
    if group is None or group.foundation_id!=foundation_id:return []
    contacts=[]
    for user_id,label in ((group.leader_id,'Ведущий'),(group.coordinator_id,'Координатор')):
        user=await db.get(User,user_id) if user_id else None
        if user and await owner_eligible(db,foundation_id,user.id,group.id,False):contacts.append(EventContact(role=label,display_name=user.display_name))
    return contacts


async def materialize_window(db,foundation_id,lower,upper):
    # Series being edited right now are skipped; the next read projects them.
    entities=(await db.scalars(select(EventSeries).where(EventSeries.foundation_id==foundation_id,EventSeries.state=='active').order_by(EventSeries.id).with_for_update(skip_locked=True))).all()
    for entity in entities:await materialize(db,entity,lower-timedelta(days=1),upper+timedelta(days=1))


async def cards(db,principal,occurrences,*,feed):
    """Views for the volunteer; feed=True drops occurrences already in the volunteer's own schedule."""
    if not occurrences:return []
    fid=principal.foundation_id;uid=principal.user_id;now=utcnow()
    ids=[item.id for item in occurrences]
    needs=(await db.scalars(select(StaffingNeed).where(StaffingNeed.foundation_id==fid,StaffingNeed.occurrence_id.in_(ids),StaffingNeed.capacity_required>0).order_by(StaffingNeed.id))).all()
    by_occurrence={}
    for need in needs:by_occurrence.setdefault(need.occurrence_id,[]).append(need)
    need_ids=[need.id for need in needs]
    confirmed=dict((await db.execute(select(Assignment.staffing_need_id,func.count()).where(Assignment.foundation_id==fid,Assignment.staffing_need_id.in_(need_ids),Assignment.status=='confirmed')
        .group_by(Assignment.staffing_need_id))).all()) if need_ids else {}
    revisions={row.id:row for row in (await db.scalars(select(VolunteerRoleVersion).where(VolunteerRoleVersion.id.in_({need.role_version_id for need in needs})))).all()} if needs else {}
    roles=await ranking.load_roles(db,fid,list({need.role_id for need in needs}))
    mine={row.occurrence_id:row for row in (await db.scalars(select(Assignment).where(Assignment.foundation_id==fid,Assignment.user_id==uid,Assignment.occurrence_id.in_(ids)))).all()}
    reserves={row.staffing_need_id:row for row in (await db.scalars(select(StaffingNeedReserve).where(StaffingNeedReserve.foundation_id==fid,StaffingNeedReserve.user_id==uid,
        StaffingNeedReserve.occurrence_id.in_(ids),StaffingNeedReserve.state!='closed'))).all()}
    lower=min(item.starts_at for item in occurrences);upper=max(item.ends_at for item in occurrences)
    busy=(await db.execute(select(ResourceReservation.source_type,ResourceReservation.source_id,ResourceReservation.starts_at,ResourceReservation.busy_until).where(
        ResourceReservation.foundation_id==fid,ResourceReservation.owner_key==f'user:{uid}',ResourceReservation.active.is_(True),
        ResourceReservation.starts_at<upper,ResourceReservation.busy_until>lower))).all()
    facts=(await ranking.load_facts(db,fid,[uid],now)).get(uid)
    gate=await sign_up_gate(db,fid,uid)
    result=[]
    for item in occurrences:
        own=mine.get(item.id)
        active=own if own and own.status in ('invited','confirmed') else None
        if feed and active:continue
        rows=by_occurrence.get(item.id,[])
        if not rows and not active:continue
        own_ids={own.id} if own else set()
        conflict=any(start<item.ends_at and until>item.starts_at and not (kind=='activity' and source in own_ids) for kind,source,start,until in busy)
        views=[];scored=[]
        for need in rows:
            taken=confirmed.get(need.id,0);missing=max(0,need.capacity_required-taken)
            reserve=reserves.get(need.id)
            actions=[]
            if gate is None and active is None and not conflict and item.starts_at>now:
                if missing>0:actions.append('sign-up')
                elif reserve is None:actions.append('reserve')
            revision=revisions.get(need.role_version_id)
            snapshot=revision.snapshot if revision else {}
            mine_here=own if own and own.staffing_need_id==need.id and own.status in ('invited','confirmed') else None
            views.append(VolunteerEventNeed(id=need.id,version=need.version,role_id=need.role_id,role_title=snapshot.get('title',''),task=snapshot.get('task',''),
                required=need.capacity_required,confirmed=taken,missing=missing,approval_policy=need.approval_policy,points_multiplier=float(getattr(need,'points_multiplier',1) or 1),
                preparation_requirements=need.preparation_requirements,readiness=await own_readiness(db,fid,uid,need.preparation_requirements,mine_here),allowed_actions=actions))
            score=ranking.score_need(facts,item,roles.get(need.role_id),now) if facts else None
            scored.append((need,missing,score))
        open_needs=[row for row in scored if row[1]>0]
        full=bool(rows) and not open_needs
        pool=open_needs or scored
        best=max(pool,key=lambda row:(row[2].score if row[2] else 0,row[2].familiar_visits if row[2] else 0),default=None)
        if active:best_id=active.staffing_need_id
        elif reserves and any(need.id in reserves for need in rows):best_id=next(need.id for need in rows if need.id in reserves)
        else:best_id=best[0].id if best else None
        score=best[2] if best else None
        reasons=[text for text in (reason_text(reason) for reason in (score.reasons if score else [])) if text]
        reserve=next((reserves[need.id] for need in rows if need.id in reserves),None)
        card=VolunteerEventCard(occurrence_id=item.id,series_id=item.series_id,title=item.title,program=item.program,kind=item.kind,format=item.format,location=item.location,
            audience=item.audience,status=item.status,starts_at=item.starts_at,ends_at=item.ends_at,timezone=item.timezone,needs=views,best_need_id=best_id,reasons=reasons,full=full,conflict=conflict,
            my_assignment=VolunteerEventAssignment(id=own.id,version=own.version,staffing_need_id=own.staffing_need_id,status=own.status,origin=own.origin,approved_at=own.approved_at,
                awaiting_coordinator=own.status=='invited' and own.origin in ('self','reserve') and own.approved_at is None) if own else None,
            my_reserve=await reserve_view(db,reserve) if reserve else None)
        result.append((card,score.score if score else 0.0,score.familiar_visits if score else 0))
    return result


def ranked(rows):
    # Open places first by score; full or overlapping events stay visible at the end, by date.
    ordered=[card for card,_,_ in sorted(rows,key=lambda row:(row[0].full or row[0].conflict,-(row[1] if not (row[0].full or row[0].conflict) else 0),-row[2],row[0].starts_at,str(row[0].occurrence_id)))]
    # A recurring series appears once, at its best date; the event page lists the other dates.
    seen=set();result=[]
    for card in ordered:
        if card.series_id in seen:continue
        seen.add(card.series_id);result.append(card)
    return result


async def feed(db,principal,lower,upper,limit):
    require_user(principal)
    if upper<=lower or (upper-lower).days>FEED_MAX_DAYS:raise ApiError(422,'feed_range',f'Выберите период до {FEED_MAX_DAYS} дней.')
    await materialize_window(db,principal.foundation_id,lower.date(),upper.date())
    start=max(lower,utcnow())
    occurrences=(await db.scalars(select(EventOccurrence).where(EventOccurrence.foundation_id==principal.foundation_id,EventOccurrence.status=='scheduled',
        EventOccurrence.starts_at>=start,EventOccurrence.starts_at<upper).order_by(EventOccurrence.starts_at,EventOccurrence.id).limit(500))).all()
    rows=await cards(db,principal,list(occurrences),feed=True)
    gate=await sign_up_gate(db,principal.foundation_id,principal.user_id)
    return VolunteerEventFeed(algorithm_version=ranking.ALGORITHM_VERSION,can_sign_up=gate is None,locked_reason=gate[0] if gate else None,locked_message=gate[1] if gate else None,
        items=ranked(rows)[:limit])


async def detail(db,principal,occurrence_id):
    require_user(principal)
    item=await db.scalar(select(EventOccurrence).where(EventOccurrence.id==occurrence_id,EventOccurrence.foundation_id==principal.foundation_id))
    own=await db.scalar(select(Assignment.id).where(Assignment.occurrence_id==occurrence_id,Assignment.user_id==principal.user_id)) if item else None
    has_needs=await db.scalar(select(StaffingNeed.id).where(StaffingNeed.occurrence_id==occurrence_id,StaffingNeed.capacity_required>0).limit(1)) if item else None
    # Only events open for volunteers, or the volunteer's own history, are visible here.
    if item is None or (own is None and (item.status!='scheduled' or not has_needs)):raise ApiError(404,'occurrence_not_found','Занятие не найдено.')
    rows=await cards(db,principal,[item],feed=False)
    if not rows:raise ApiError(404,'occurrence_not_found','Занятие не найдено.')
    card=rows[0][0]
    now=utcnow()
    others=(await db.scalars(select(EventOccurrence).where(EventOccurrence.foundation_id==principal.foundation_id,EventOccurrence.series_id==item.series_id,EventOccurrence.id!=item.id,
        EventOccurrence.status=='scheduled',EventOccurrence.starts_at>now).order_by(EventOccurrence.starts_at,EventOccurrence.id).limit(OTHER_DATES))).all()
    dates=[]
    if others:
        other_ids=[row.id for row in others]
        needs=(await db.scalars(select(StaffingNeed).where(StaffingNeed.occurrence_id.in_(other_ids),StaffingNeed.capacity_required>0))).all()
        taken=dict((await db.execute(select(Assignment.staffing_need_id,func.count()).where(Assignment.staffing_need_id.in_([need.id for need in needs]),Assignment.status=='confirmed')
            .group_by(Assignment.staffing_need_id))).all()) if needs else {}
        mine={row for row in (await db.scalars(select(Assignment.occurrence_id).where(Assignment.user_id==principal.user_id,Assignment.occurrence_id.in_(other_ids),Assignment.status.in_(('invited','confirmed'))))).all()}
        for row in others:
            own_needs=[need for need in needs if need.occurrence_id==row.id]
            if not own_needs and row.id not in mine:continue
            dates.append(VolunteerEventDate(occurrence_id=row.id,starts_at=row.starts_at,ends_at=row.ends_at,mine=row.id in mine,
                full=not any(need.capacity_required>taken.get(need.id,0) for need in own_needs)))
    gate=await sign_up_gate(db,principal.foundation_id,principal.user_id)
    return VolunteerEventDetail(**card.model_dump(),algorithm_version=ranking.ALGORITHM_VERSION,can_sign_up=gate is None,
        locked_reason=gate[0] if gate else None,locked_message=gate[1] if gate else None,other_dates=dates,
        contacts=await event_contacts(db,principal.foundation_id,item.group_id))


async def own_reserves(db,principal):
    require_user(principal)
    rows=(await db.execute(select(StaffingNeedReserve,EventOccurrence,StaffingNeed).join(EventOccurrence,EventOccurrence.id==StaffingNeedReserve.occurrence_id)
        .join(StaffingNeed,StaffingNeed.id==StaffingNeedReserve.staffing_need_id).where(StaffingNeedReserve.foundation_id==principal.foundation_id,
        StaffingNeedReserve.user_id==principal.user_id,StaffingNeedReserve.state=='waiting',EventOccurrence.status=='scheduled',EventOccurrence.starts_at>utcnow())
        .order_by(EventOccurrence.starts_at,StaffingNeedReserve.id).limit(100))).all()
    revisions={row.id:row for row in (await db.scalars(select(VolunteerRoleVersion).where(VolunteerRoleVersion.id.in_({need.role_version_id for _,_,need in rows})))).all()} if rows else {}
    items=[]
    for reserve,event,need in rows:
        view=await reserve_view(db,reserve);revision=revisions.get(need.role_version_id)
        items.append(VolunteerReserveItem(reserve_id=reserve.id,version=reserve.version,position=view.position,state=reserve.state,occurrence_id=event.id,staffing_need_id=need.id,
            title=event.title,role_title=revision.snapshot.get('title','') if revision else '',starts_at=event.starts_at,ends_at=event.ends_at,location=event.location,timezone=event.timezone,
            allowed_actions=view.allowed_actions))
    return VolunteerReservePage(items=items)


def window(from_date,to_date,zone):
    lower=datetime.combine(from_date,datetime.min.time(),tzinfo=zone).astimezone(timezone.utc)
    upper=datetime.combine(to_date+timedelta(days=1),datetime.min.time(),tzinfo=zone).astimezone(timezone.utc)
    return lower,upper
