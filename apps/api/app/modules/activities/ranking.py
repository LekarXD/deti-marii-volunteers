"""Volunteer × staffing need ranking (rules-v3). The score only orders candidates; clients see reasons, never the number."""
from collections import defaultdict
from dataclasses import dataclass,field
from datetime import datetime,timedelta
from functools import lru_cache
from uuid import UUID
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
from sqlalchemy import or_,select
from app.core.clock import utcnow
from app.core.models import StaffMembership
from app.modules.applications.models import Application,ApplicationRevision
from app.modules.crm.models import AvailabilityRule,AvailabilityWindow,CrmVolunteer
from app.modules.interviews.models import InterviewBooking
from app.modules.notifications.models import NotificationPreference
from app.modules.profile.models import VolunteerProfile
from .assignment_models import Assignment,Attendance
from .calendar_models import EventOccurrence
from .directions import LEGACY_DIRECTIONS,UNKNOWN_DIRECTION,answer_directions,answer_skills
from .models import VolunteerRole

ALGORITHM_VERSION='rules-v3'
WEIGHTS={'role':0.4,'familiar':0.4,'time':0.2}
HALF_YEAR=timedelta(days=183)
ADVANCE_WINDOW=timedelta(weeks=6)
VISIT_SCORE=0.2
ADVANCE_SCORE=0.8
DEFAULT_TIMEZONE='Europe/Moscow'
OTHER_CITY='Другой город'
WEEKDAYS=('пн','вт','ср','чт','пт','сб','вс')
CHUNK=500


@dataclass(frozen=True)
class Reason:
    code:str      # 'skill' | 'direction' | 'unknown_direction' | 'familiar' | 'familiar_new' | 'time_history' | 'time_window'
    value:str=''  # skill or direction label; for time reasons a label like 'сб, днём'
    count:int=0   # attended visits for 'familiar'


@dataclass(frozen=True)
class Visit:
    """One assignment of the volunteer, reduced to what the ranking needs."""
    group:UUID                    # Assignment.group_id_snapshot, else the occurrence series
    starts_at:datetime
    weekday:int                   # Monday=0, local to the occurrence timezone
    part:str                      # 'утром' | 'днём' | 'вечером'
    confirmed_at:datetime|None=None
    outcome:str|None=None         # 'attended' | 'absent' | None


@dataclass
class VolunteerFacts:
    user_id:UUID
    directions:set[str]=field(default_factory=set)
    skills:set[str]=field(default_factory=set)
    area:str|None=None            # answers['area']
    meeting_completed:bool=False  # any InterviewBooking.status == 'completed'
    ever_confirmed:bool=False     # any Assignment with confirmed_at not null
    paused:bool=False             # profile pause or CRM relationship_state == 'paused'
    no_contact:bool=False         # CrmVolunteer.no_contact or NotificationPreference.no_contact
    staff_only:bool=False         # active StaffMembership without application or assignments
    invited_count:int=0
    confirmed_count:int=0
    attended_count:int=0
    has_application:bool=False
    visits:list[Visit]=field(default_factory=list)
    windows:list[tuple[int,int,int]]=field(default_factory=list)  # latest CRM rule: (weekday, start_minute, end_minute)
    windows_timezone:str=DEFAULT_TIMEZONE


@dataclass
class NeedScore:
    score:float
    role:float
    familiar:float
    time:float
    familiar_visits:int
    reasons:list[Reason]


@lru_cache(maxsize=64)
def _zone(name):
    try:return ZoneInfo(name or DEFAULT_TIMEZONE)
    except (ZoneInfoNotFoundError,ValueError):return ZoneInfo(DEFAULT_TIMEZONE)


def part_of_day(minute):
    return 'утром' if minute<12*60 else 'днём' if minute<17*60 else 'вечером'


def slot_label(weekday,part):
    return f'{WEEKDAYS[weekday]}, {part}'


def local_slot(moment,timezone_name):
    local=moment.astimezone(_zone(timezone_name))
    return local.weekday(),part_of_day(local.hour*60+local.minute)


def group_key(occurrence):
    return occurrence.group_id or occurrence.series_id


def exclusion(facts,occurrence):
    """Why the person never appears in suggestions for this occurrence, or None."""
    if facts.staff_only:return 'staff'
    # Same trust rule as assignment_service.sign_up_gate: a past confirmed shift stands in for the meeting.
    if not (facts.meeting_completed or facts.ever_confirmed):return 'no_meeting'
    if facts.paused:return 'paused'
    if facts.no_contact:return 'no_contact'
    if facts.area==OTHER_CITY and occurrence.format=='onsite':return 'other_city'
    return None


def missing_data(facts):
    missing=[]
    if not facts.directions and not facts.skills:missing.append('questionnaire')
    if not facts.windows and not any(visit.outcome=='attended' for visit in facts.visits):missing.append('availability')
    return missing


def _role_fit(facts,role,reasons):
    if role is not None:
        matched=[skill for skill in (role.skills or []) if skill in facts.skills]
        if matched:reasons.append(Reason('skill',matched[0]));return 1.0
        direction=LEGACY_DIRECTIONS.get(role.direction or '',role.direction or '')
        if direction and direction in facts.directions:reasons.append(Reason('direction',direction));return 0.6
    if UNKNOWN_DIRECTION in facts.directions:reasons.append(Reason('unknown_direction'));return 0.3
    return 0.0


def _familiar(facts,group,now,reasons):
    here=[visit for visit in facts.visits if visit.group==group]
    attended=sorted(visit.starts_at for visit in here if visit.outcome=='attended' and visit.starts_at<=now)
    recent=sum(1 for moment in attended if moment>=now-HALF_YEAR)
    earned=min(1.0,round(VISIT_SCORE*recent,6));advance=0.0
    if attended and now-attended[0]<ADVANCE_WINDOW:
        first=attended[0]
        no_show=any(visit.outcome=='absent' and first<=visit.starts_at<=now for visit in here)
        confirmed=any(visit.confirmed_at and now-ADVANCE_WINDOW<=visit.confirmed_at<=now for visit in here)
        if confirmed and not no_show:advance=ADVANCE_SCORE
    if advance>earned:reasons.append(Reason('familiar_new'));return advance,recent
    if recent:reasons.append(Reason('familiar',count=recent))
    return earned,recent


def _time_fit(facts,occurrence,reasons):
    history={(visit.weekday,visit.part) for visit in facts.visits if visit.outcome=='attended'}
    if history:
        weekday,part=local_slot(occurrence.starts_at,occurrence.timezone)
        if (weekday,part) in history:reasons.append(Reason('time_history',slot_label(weekday,part)));return 1.0
        return 0.6 if any(day==weekday for day,_ in history) else 0.2
    if facts.windows:
        zone=_zone(facts.windows_timezone)
        start=occurrence.starts_at.astimezone(zone);end=occurrence.ends_at.astimezone(zone)
        weekday=start.weekday();begin=start.hour*60+start.minute
        finish=end.hour*60+end.minute+(end.second>0)+1440*(end.date()-start.date()).days
        same_day=[(low,high) for day,low,high in facts.windows if day==weekday]
        if any(low<=begin and finish<=high for low,high in same_day):
            reasons.append(Reason('time_window',slot_label(weekday,part_of_day(begin))));return 1.0
        return 0.6 if same_day else 0.2
    return 0.5


def score_need(facts:VolunteerFacts,occurrence:EventOccurrence,role:VolunteerRole|None,now=None)->NeedScore:
    """Pure: no DB. Reasons are emitted only for components that contributed."""
    now=now or utcnow();reasons=[]
    role_fit=_role_fit(facts,role,reasons)
    familiar,visits=_familiar(facts,group_key(occurrence),now,reasons)
    time_fit=_time_fit(facts,occurrence,reasons)
    score=round(WEIGHTS['role']*role_fit+WEIGHTS['familiar']*familiar+WEIGHTS['time']*time_fit,6)
    return NeedScore(score=score,role=role_fit,familiar=familiar,time=time_fit,familiar_visits=visits,reasons=reasons)


async def load_roles(db,foundation_id,role_ids)->dict[UUID,VolunteerRole]:
    ids=list(dict.fromkeys(role_ids))
    if not ids:return {}
    rows=(await db.scalars(select(VolunteerRole).where(VolunteerRole.foundation_id==foundation_id,VolunteerRole.id.in_(ids)))).all()
    return {row.id:row for row in rows}


async def load_facts(db,foundation_id,user_ids,now=None)->dict[UUID,VolunteerFacts]:
    """A fixed number of queries per chunk of users; no per-user lookups."""
    now=now or utcnow();ids=list(dict.fromkeys(user_ids))
    facts={user_id:VolunteerFacts(user_id=user_id) for user_id in ids}
    for start in range(0,len(ids),CHUNK):await _load_chunk(db,foundation_id,ids[start:start+CHUNK],facts,now)
    return facts


async def _load_chunk(db,foundation_id,ids,facts,now):
    applications={}
    rows=(await db.execute(select(Application.id,Application.user_id,ApplicationRevision.answers)
        .outerjoin(ApplicationRevision,ApplicationRevision.id==Application.submitted_revision_id)
        .where(Application.foundation_id==foundation_id,Application.user_id.in_(ids)))).all()
    for application_id,user_id,answers in rows:
        item=facts[user_id];item.has_application=True;applications[application_id]=user_id
        if isinstance(answers,dict):
            item.directions=answer_directions(answers);item.skills=answer_skills(answers)
            item.area=answers['area'] if isinstance(answers.get('area'),str) else None
    # Bookings made before the account existed are linked through the application.
    owned=or_(InterviewBooking.user_id.in_(ids),InterviewBooking.application_id.in_(list(applications))) if applications else InterviewBooking.user_id.in_(ids)
    for user_id,application_id in (await db.execute(select(InterviewBooking.user_id,InterviewBooking.application_id).where(
            InterviewBooking.foundation_id==foundation_id,InterviewBooking.status=='completed',owned))).all():
        for owner in (user_id,applications.get(application_id)):
            if owner in facts:facts[owner].meeting_completed=True
    rows=(await db.execute(select(Assignment.user_id,Assignment.confirmed_at,Assignment.group_id_snapshot,EventOccurrence.series_id,EventOccurrence.starts_at,EventOccurrence.timezone,Attendance.outcome)
        .join(EventOccurrence,EventOccurrence.id==Assignment.occurrence_id).outerjoin(Attendance,Attendance.assignment_id==Assignment.id)
        .where(Assignment.foundation_id==foundation_id,Assignment.user_id.in_(ids)))).all()
    for user_id,confirmed_at,group_id,series_id,starts_at,zone,outcome in rows:
        item=facts[user_id];weekday,part=local_slot(starts_at,zone)
        item.visits.append(Visit(group_id or series_id,starts_at,weekday,part,confirmed_at,outcome))
        item.invited_count+=1;item.confirmed_count+=confirmed_at is not None;item.attended_count+=outcome=='attended'
        item.ever_confirmed=item.ever_confirmed or confirmed_at is not None
    today=now.astimezone(_zone(DEFAULT_TIMEZONE)).date()
    for user_id,until in (await db.execute(select(VolunteerProfile.user_id,VolunteerProfile.paused_until).where(
            VolunteerProfile.foundation_id==foundation_id,VolunteerProfile.user_id.in_(ids),VolunteerProfile.lifecycle=='paused'))).all():
        # Same rule as profile.service.active_for_invitations: an expired pause no longer counts.
        if not (until and until<today):facts[user_id].paused=True
    for user_id in (await db.scalars(select(NotificationPreference.user_id).where(
            NotificationPreference.foundation_id==foundation_id,NotificationPreference.user_id.in_(ids),NotificationPreference.no_contact.is_(True)))).all():
        facts[user_id].no_contact=True
    for user_id in (await db.scalars(select(StaffMembership.user_id).where(
            StaffMembership.foundation_id==foundation_id,StaffMembership.user_id.in_(ids),StaffMembership.revoked_at.is_(None)))).all():
        item=facts[user_id];item.staff_only=not item.has_application and not item.visits
    await _load_crm(db,foundation_id,ids,applications,facts)


async def _load_crm(db,foundation_id,ids,applications,facts):
    linked=or_(CrmVolunteer.user_id.in_(ids),CrmVolunteer.application_id.in_(list(applications))) if applications else CrmVolunteer.user_id.in_(ids)
    records=(await db.scalars(select(CrmVolunteer).where(CrmVolunteer.foundation_id==foundation_id,linked))).all()
    merged={record.merged_into_id for record in records if record.merged_into_id}
    # Aliases point directly at the canonical card (crm.service.alias_ids), so one hop is enough.
    targets={row.id:row for row in (await db.scalars(select(CrmVolunteer).where(CrmVolunteer.foundation_id==foundation_id,CrmVolunteer.id.in_(merged)))).all()} if merged else {}
    canonical={}
    for record in records:
        owner=record.user_id if record.user_id in facts else applications.get(record.application_id)
        if owner not in facts:continue
        target=targets.get(record.merged_into_id,record);item=facts[owner]
        item.no_contact=item.no_contact or record.no_contact or target.no_contact
        item.paused=item.paused or target.relationship_state=='paused'
        if owner not in canonical or (record.merged_into_id is None and record.user_id==owner):canonical[owner]=target.id
    if not canonical:return
    rules={rule.volunteer_id:rule for rule in (await db.scalars(select(AvailabilityRule).where(AvailabilityRule.volunteer_id.in_(set(canonical.values())))
        .order_by(AvailabilityRule.volunteer_id,AvailabilityRule.number.desc()).distinct(AvailabilityRule.volunteer_id))).all()}
    if not rules:return
    windows=defaultdict(list)
    for rule_id,weekday,low,high in (await db.execute(select(AvailabilityWindow.rule_id,AvailabilityWindow.weekday,AvailabilityWindow.start_minute,AvailabilityWindow.end_minute).where(
            AvailabilityWindow.rule_id.in_([rule.id for rule in rules.values()])))).all():
        windows[rule_id].append((weekday,low,high))
    for owner,volunteer_id in canonical.items():
        rule=rules.get(volunteer_id)
        if rule:facts[owner].windows=sorted(windows[rule.id]);facts[owner].windows_timezone=rule.timezone or DEFAULT_TIMEZONE
