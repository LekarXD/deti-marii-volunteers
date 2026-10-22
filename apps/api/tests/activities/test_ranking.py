"""rules-v3 volunteer × staffing need ranking: pure scoring, batch facts and the coordinator suggestions."""
from datetime import date,datetime,time,timedelta,timezone
from uuid import UUID,uuid4
from zoneinfo import ZoneInfo
import pytest
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.models import RegistrationSession,StaffMembership,User
from app.modules.activities.assignment_models import Assignment,Attendance
from app.modules.activities.calendar_models import EventOccurrence,StaffingNeed
from app.modules.activities.directions import answer_directions,answer_skills
from app.modules.activities.models import VolunteerRole
from app.modules.activities.ranking import ALGORITHM_VERSION,WEIGHTS,Reason,Visit,VolunteerFacts,exclusion,load_facts,load_roles,local_slot,missing_data,score_need
from app.modules.applications.models import Application,ApplicationRevision,FormVersion
from app.modules.crm.models import AvailabilityRule,AvailabilityWindow,CrmVolunteer
from app.modules.interviews.models import AvailabilitySeries,InterviewBooking,InterviewSlot
from app.modules.notifications.models import NotificationPreference
from app.modules.profile.models import VolunteerProfile
from .test_p07 import context,headers
from .test_p09 import setup,user_headers

MSK=ZoneInfo('Europe/Moscow')
NOW=datetime(2028,3,1,12,0,tzinfo=timezone.utc) # Wednesday
GROUP=uuid4();SERIES=uuid4();OTHER=uuid4()
SATURDAY=datetime(2028,3,4,14,0,tzinfo=MSK) # сб, днём


def occurrence(start=SATURDAY,minutes=120,group=GROUP,series=SERIES,format='onsite'):
    return EventOccurrence(id=uuid4(),series_id=series,group_id=group,starts_at=start,ends_at=start+timedelta(minutes=minutes),timezone='Europe/Moscow',format=format,title='Занятие')


def visit(start,outcome='attended',group=GROUP,confirmed=None):
    weekday,part=local_slot(start,'Europe/Moscow')
    return Visit(group,start,weekday,part,confirmed or start-timedelta(days=3),outcome)


def weeks_ago(weeks,hour=14,weekday=5):
    day=(NOW-timedelta(weeks=weeks)).astimezone(MSK).date();day-=timedelta(days=(day.weekday()-weekday)%7)
    return datetime.combine(day,time(hour),tzinfo=MSK)


def role(direction='Творчество',skills=('Керамика',)):
    return VolunteerRole(title='Ассистент',direction=direction,skills=list(skills))


def facts(**values):
    return VolunteerFacts(user_id=uuid4(),**values)


def test_contract_constants():
    assert ALGORITHM_VERSION=='rules-v3' and WEIGHTS=={'role':0.4,'familiar':0.4,'time':0.2}


def test_role_fit_levels_and_questionnaire_vocabulary():
    event=occurrence()
    skill=score_need(facts(skills={'Керамика'},directions={'Творчество'}),event,role(),NOW)
    assert skill.role==1.0 and skill.reasons==[Reason('skill','Керамика')]
    # Nothing else contributes: 0.4·1 + 0.4·0 + 0.2·0.5 (no time data).
    assert skill.score==0.5 and skill.familiar==0 and skill.time==0.5
    direction=score_need(facts(skills={'Валяние'},directions={'Творчество'}),event,role(),NOW)
    assert direction.role==0.6 and direction.reasons==[Reason('direction','Творчество')] and direction.score==round(0.24+0.1,6)
    unknown=score_need(facts(directions={'Пока не знаю'}),event,role(),NOW)
    assert unknown.role==0.3 and unknown.reasons==[Reason('unknown_direction')]
    none=score_need(facts(directions={'Ярмарки'},skills={'Валяние'}),event,role(),NOW)
    assert none.role==0 and none.reasons==[] and none.score==0.1
    # Version 4 «Как специалист» is the current specialist direction; free-text skills are never compared.
    legacy=facts(directions=answer_directions({'directions':['Как специалист']}),skills=answer_skills({'skills':['Лепка из теста','IT']}))
    assert legacy.skills=={'IT'}
    assert score_need(legacy,event,role('Юрист, IT, маркетинг',()),NOW).reasons==[Reason('direction','Юрист, IT, маркетинг')]
    assert score_need(facts(skills=answer_skills({'skills':['Своя керамика']})),event,role(),NOW).role==0
    # A role without authored vocabulary still lets «Пока не знаю» through, nothing else.
    assert score_need(facts(directions={'Пока не знаю'}),event,None,NOW).role==0.3
    assert score_need(facts(directions={'Творчество'},skills={'Керамика'}),event,role('',()),NOW).role==0


def test_familiar_visits_cap_scope_and_series_fallback():
    event=occurrence()
    three=facts(visits=[visit(weeks_ago(w)) for w in (8,9,10)])
    result=score_need(three,event,None,NOW)
    assert result.familiar==0.6 and result.familiar_visits==3 and Reason('familiar',count=3) in result.reasons
    seven=score_need(facts(visits=[visit(weeks_ago(w)) for w in range(7,14)]),event,None,NOW)
    assert seven.familiar==1.0 and seven.familiar_visits==7 and Reason('familiar',count=7) in seven.reasons
    # Older than half a year, other groups and no-shows do not count as visits.
    stale=facts(visits=[visit(weeks_ago(30)),visit(weeks_ago(8),group=OTHER),visit(weeks_ago(9),group=OTHER),visit(weeks_ago(10),outcome='absent')])
    result=score_need(stale,event,None,NOW)
    assert result.familiar==0 and result.familiar_visits==0 and not [r for r in result.reasons if r.code.startswith('familiar')]
    # Without a group the series is the familiar unit.
    series=facts(visits=[visit(weeks_ago(w),group=SERIES) for w in (8,9)])
    assert score_need(series,occurrence(group=None),None,NOW).familiar==0.4
    assert score_need(series,event,None,NOW).familiar==0


def test_advance_for_a_newcomer_and_how_it_burns():
    event=occurrence()
    newcomer=facts(visits=[visit(weeks_ago(2),confirmed=NOW-timedelta(weeks=3))])
    result=score_need(newcomer,event,None,NOW)
    assert result.familiar==0.8 and result.familiar_visits==1 and Reason('familiar_new') in result.reasons
    assert not [r for r in result.reasons if r.code=='familiar']
    # A no-show on this group after the first visit burns the advance; one elsewhere does not.
    no_show=facts(visits=[visit(weeks_ago(2),confirmed=NOW-timedelta(weeks=3)),visit(weeks_ago(1),outcome='absent')])
    result=score_need(no_show,event,None,NOW)
    assert result.familiar==0.2 and Reason('familiar',count=1) in result.reasons and Reason('familiar_new') not in result.reasons
    elsewhere=facts(visits=[visit(weeks_ago(2),confirmed=NOW-timedelta(weeks=3)),visit(weeks_ago(1),outcome='absent',group=OTHER)])
    assert score_need(elsewhere,event,None,NOW).familiar==0.8
    # No confirmation on this group within the last six weeks burns it too…
    stale=facts(visits=[visit(weeks_ago(5),confirmed=NOW-timedelta(weeks=7))])
    assert score_need(stale,event,None,NOW).familiar==0.2
    # …unless a later shift on the same group was confirmed recently.
    upcoming=Visit(GROUP,NOW+timedelta(days=3),5,'днём',NOW-timedelta(days=1),None)
    assert score_need(facts(visits=[visit(weeks_ago(5),confirmed=NOW-timedelta(weeks=7)),upcoming]),event,None,NOW).familiar==0.8
    # The advance lasts six weeks from the FIRST visit.
    expired=facts(visits=[visit(weeks_ago(7)),visit(weeks_ago(1))])
    result=score_need(expired,event,None,NOW)
    assert result.familiar==0.4 and Reason('familiar',count=2) in result.reasons
    # When earned visits already reach the advance, the visit count is the reason.
    regular=facts(visits=[visit(weeks_ago(w)) for w in (1,2,3,5)])
    result=score_need(regular,event,None,NOW)
    assert result.familiar==0.8 and Reason('familiar',count=4) in result.reasons and Reason('familiar_new') not in result.reasons


def test_time_from_history_then_windows_then_default():
    event=occurrence()
    def time_of(item,target=event):
        result=score_need(item,target,None,NOW);return result.time,[r for r in result.reasons if r.code.startswith('time')]
    other=[visit(weeks_ago(30,weekday=w)) for w in (5,)] # history outside the familiar window still tells the time
    assert time_of(facts(visits=other))==(1.0,[Reason('time_history','сб, днём')])
    assert time_of(facts(visits=[visit(weeks_ago(30,hour=10))]))==(0.6,[])
    assert time_of(facts(visits=[visit(weeks_ago(30,weekday=1))]))==(0.2,[])
    # History wins over windows; absences are not history.
    covering=[(5,13*60,18*60)]
    assert time_of(facts(visits=[visit(weeks_ago(30,weekday=1))],windows=covering))==(0.2,[])
    assert time_of(facts(visits=[visit(weeks_ago(30,weekday=1),outcome='absent')],windows=covering))==(1.0,[Reason('time_window','сб, днём')])
    assert time_of(facts(windows=[(5,15*60,18*60)]))==(0.6,[])
    assert time_of(facts(windows=[(1,600,1200),(6,600,1200)]))==(0.2,[])
    assert time_of(facts())==(0.5,[])
    # Windows are read in the rule's timezone: 14:00–16:00 MSK is 16:00–18:00 in Yekaterinburg.
    assert time_of(facts(windows=[(5,15*60,18*60)],windows_timezone='Asia/Yekaterinburg'))==(1.0,[Reason('time_window','сб, днём')])
    # Weekday and part of day are local to the occurrence: 22:30 UTC Saturday is Sunday morning in Moscow.
    late=occurrence(start=datetime(2028,3,4,22,30,tzinfo=timezone.utc))
    assert time_of(facts(visits=[visit(weeks_ago(30,hour=9,weekday=6))]),late)==(1.0,[Reason('time_history','вс, утром')])
    evening=occurrence(start=datetime(2028,3,4,17,0,tzinfo=MSK))
    assert time_of(facts(visits=[visit(weeks_ago(30,hour=18))]),evening)==(1.0,[Reason('time_history','сб, вечером')])
    assert missing_data(facts())==['questionnaire','availability']
    assert missing_data(facts(directions={'Творчество'},windows=covering))==[]


def test_tie_data_and_exclusions():
    event=occurrence()
    five=score_need(facts(directions={'Творчество'},visits=[visit(weeks_ago(w)) for w in range(7,12)]),event,role(),NOW)
    seven=score_need(facts(directions={'Творчество'},visits=[visit(weeks_ago(w)) for w in range(7,14)]),event,role(),NOW)
    assert five.score==seven.score==round(0.24+0.4+0.2,6)
    assert (five.familiar_visits,seven.familiar_visits)==(5,7)
    ready=dict(meeting_completed=True)
    assert exclusion(facts(**ready),event) is None
    assert exclusion(facts(ever_confirmed=True),event) is None
    assert exclusion(facts(),event)=='no_meeting'
    assert exclusion(facts(staff_only=True,**ready),event)=='staff'
    assert exclusion(facts(paused=True,**ready),event)=='paused'
    assert exclusion(facts(no_contact=True,**ready),event)=='no_contact'
    assert exclusion(facts(area='Другой город',**ready),event)=='other_city'
    assert exclusion(facts(area='Другой город',**ready),occurrence(format='online')) is None
    assert exclusion(facts(area='Другой город',**ready),occurrence(format='hybrid')) is None


# --- database ---------------------------------------------------------------

async def volunteer(db,context,name,answers=None,meeting='completed',state='active'):
    user=User(foundation_id=context.foundation.id,display_name=name,account_state=state);db.add(user);await db.flush()
    application=None
    if answers is not None:
        form=await db.scalar(select(FormVersion).where(FormVersion.foundation_id==context.foundation.id))
        if form is None:form=FormVersion(foundation_id=context.foundation.id,version=5,content={});db.add(form);await db.flush()
        application=Application(foundation_id=context.foundation.id,user_id=user.id);db.add(application);await db.flush()
        revision=ApplicationRevision(application_id=application.id,form_version_id=form.id,number=1,answers=answers,author_id='test');db.add(revision);await db.flush()
        application.submitted_revision_id=revision.id;await db.flush()
    if meeting and application:
        slot=await interview_slot(db,context)
        db.add(InterviewBooking(foundation_id=context.foundation.id,application_id=application.id,user_id=user.id,candidate_key=f'user:{user.id}',slot_id=slot.id,coordinator_id=context.principal.user_id,
            starts_at=slot.starts_at,ends_at=slot.ends_at,busy_until=slot.busy_until,venue='Офис',status=meeting))
        await db.flush()
    return user


async def interview_slot(db,context):
    slot=await db.scalar(select(InterviewSlot).where(InterviewSlot.foundation_id==context.foundation.id))
    if slot:return slot
    start=datetime(2025,9,1,10,0,tzinfo=timezone.utc)
    series=AvailabilitySeries(foundation_id=context.foundation.id,coordinator_id=context.principal.user_id,local_start_date=start.date(),start_minute=600,end_minute=660,venue='Офис');db.add(series);await db.flush()
    slot=InterviewSlot(foundation_id=context.foundation.id,series_id=series.id,coordinator_id=context.principal.user_id,origin_date=start.date(),origin_minute=600,starts_at=start,ends_at=start+timedelta(minutes=30),busy_until=start+timedelta(minutes=40))
    db.add(slot);await db.flush();return slot


async def availability(db,context,user_id,windows,number=1,timezone_name='Europe/Moscow',**crm):
    record=await db.scalar(select(CrmVolunteer).where(CrmVolunteer.user_id==user_id))
    if record is None:record=CrmVolunteer(foundation_id=context.foundation.id,user_id=user_id,display_name='CRM',**crm);db.add(record);await db.flush()
    rule=AvailabilityRule(volunteer_id=record.id,number=number,summary='График',timezone=timezone_name,preferred_channel='email',author_id='test');db.add(rule);await db.flush()
    db.add_all([AvailabilityWindow(rule_id=rule.id,weekday=day,start_minute=low,end_minute=high) for day,low,high in windows]);await db.flush()
    return record


def past_mondays(count,first=1):
    """Recent Mondays at 14:00 Moscow — the same slot as the setup occurrence (2028-01-03 14:00)."""
    today=utcnow().astimezone(MSK).date();monday=today-timedelta(days=today.weekday())
    return [datetime.combine(monday-timedelta(weeks=first+i),time(14),tzinfo=MSK) for i in range(count)]


async def history(db,event_id,need_id,starts,attendees):
    """Past occurrences of the same series and group; attendees are (user_id, outcome) pairs."""
    base=await db.get(EventOccurrence,event_id);need=await db.get(StaffingNeed,need_id)
    for start in starts:
        local=start.astimezone(MSK)
        row=EventOccurrence(id=uuid4(),foundation_id=base.foundation_id,series_id=base.series_id,origin_local_date=local.date(),origin_local_time=local.time(),starts_at=start,ends_at=start+timedelta(hours=2),
            timezone='Europe/Moscow',group_id=base.group_id,title=base.title,series_version=base.series_version,updated_by='test')
        db.add(row);await db.flush()
        past=StaffingNeed(occurrence_id=row.id,foundation_id=row.foundation_id,role_id=need.role_id,role_version_id=need.role_version_id,capacity_required=20);db.add(past);await db.flush()
        for user_id,outcome in attendees:
            item=Assignment(foundation_id=row.foundation_id,user_id=user_id,occurrence_id=row.id,staffing_need_id=past.id,group_id_snapshot=row.group_id,status='confirmed',
                confirmed_at=start-timedelta(days=2),conditions_version=1,conditions_snapshot={});db.add(item);await db.flush()
            if outcome:db.add(Attendance(foundation_id=row.foundation_id,assignment_id=item.id,outcome=outcome,minutes=120 if outcome=='attended' else 0))
    await db.flush()


@pytest.mark.asyncio
async def test_load_facts_batches_questionnaire_meetings_pauses_contacts_and_history(context):
    event,need,first,second,_=await setup(context,group=True)
    async with context.db() as db:
        legacy=await volunteer(db,context,'Анкета v4',{'directions':['Как специалист'],'skills':['IT','Своё умение'],'area':'Юг'})
        # A meeting booked before the account existed is linked through the application.
        claimed=await volunteer(db,context,'Встреча до аккаунта',{'directions':['Творчество']},meeting=None)
        registration=RegistrationSession(foundation_id=context.foundation.id,expires_at=utcnow()+timedelta(hours=1));db.add(registration);await db.flush()
        application=await db.scalar(select(Application).where(Application.user_id==claimed.id));slot=await interview_slot(db,context)
        db.add(InterviewBooking(foundation_id=context.foundation.id,application_id=application.id,registration_id=registration.id,candidate_key=f'registration:{registration.id}',slot_id=slot.id,
            coordinator_id=context.principal.user_id,starts_at=slot.starts_at,ends_at=slot.ends_at,busy_until=slot.busy_until,venue='Офис',status='completed'))
        missed=await volunteer(db,context,'Не пришёл на встречу',{'directions':['Творчество']},meeting='missed')
        paused=await volunteer(db,context,'Пауза',{'directions':['Творчество']})
        db.add(VolunteerProfile(user_id=paused.id,foundation_id=context.foundation.id,lifecycle='paused'))
        resumed=await volunteer(db,context,'Пауза закончилась',{'directions':['Творчество']})
        db.add(VolunteerProfile(user_id=resumed.id,foundation_id=context.foundation.id,lifecycle='paused',paused_until=date(2020,1,1)))
        crm_paused=await volunteer(db,context,'CRM пауза',{'directions':['Творчество']})
        await availability(db,context,crm_paused.id,[(0,600,1200)],relationship_state='paused')
        quiet=await volunteer(db,context,'Не беспокоить',{'directions':['Творчество']})
        db.add(NotificationPreference(foundation_id=context.foundation.id,user_id=quiet.id,no_contact=True))
        # An old alias carries the opt-out of the canonical card it was merged into.
        aliased=await volunteer(db,context,'Объединённая карточка',{'directions':['Творчество']})
        canonical=CrmVolunteer(foundation_id=context.foundation.id,display_name='Канон',no_contact=True);db.add(canonical);await db.flush()
        db.add(CrmVolunteer(foundation_id=context.foundation.id,user_id=aliased.id,display_name='Алиас',merged_into_id=canonical.id))
        windows=await volunteer(db,context,'Окна',{'directions':['Творчество']})
        await availability(db,context,windows.id,[(1,600,700)],number=1)
        await availability(db,context,windows.id,[(0,780,1020),(5,600,900)],number=2,timezone_name='Asia/Yekaterinburg')
        staff=await volunteer(db,context,'Сотрудник')
        db.add(StaffMembership(foundation_id=context.foundation.id,user_id=staff.id))
        staff_volunteer=await volunteer(db,context,'Сотрудник и волонтёр',{'directions':['Творчество']})
        db.add(StaffMembership(foundation_id=context.foundation.id,user_id=staff_volunteer.id))
        await history(db,UUID(event['id']),UUID(need['id']),past_mondays(3),[(first,'attended'),(second,'absent')])
        await db.commit()
        ids=[first,second,legacy.id,claimed.id,missed.id,paused.id,resumed.id,crm_paused.id,quiet.id,aliased.id,windows.id,staff.id,staff_volunteer.id,context.principal.user_id,uuid4()]
        loaded=await load_facts(db,context.foundation.id,ids)
        assert set(loaded)==set(ids)
        assert loaded[legacy.id].directions=={'Юрист, IT, маркетинг'} and loaded[legacy.id].skills=={'IT'} and loaded[legacy.id].area=='Юг' and loaded[legacy.id].meeting_completed
        assert loaded[claimed.id].meeting_completed and not loaded[missed.id].meeting_completed
        assert loaded[paused.id].paused and not loaded[resumed.id].paused and loaded[crm_paused.id].paused
        assert loaded[quiet.id].no_contact and loaded[aliased.id].no_contact and not loaded[legacy.id].no_contact
        assert loaded[windows.id].windows==[(0,780,1020),(5,600,900)] and loaded[windows.id].windows_timezone=='Asia/Yekaterinburg'
        assert loaded[crm_paused.id].windows==[(0,600,1200)]
        assert loaded[staff.id].staff_only and loaded[context.principal.user_id].staff_only and not loaded[staff_volunteer.id].staff_only
        one,two=loaded[first],loaded[second]
        assert (one.invited_count,one.confirmed_count,one.attended_count,one.ever_confirmed)==(3,3,3,True)
        assert (two.invited_count,two.confirmed_count,two.attended_count)==(3,3,0) and not two.staff_only
        assert {visit.group for visit in one.visits}=={UUID(event['group_id'])} and {(visit.weekday,visit.part) for visit in one.visits}=={(0,'днём')}
        roles=await load_roles(db,context.foundation.id,[UUID(need['role_id']),uuid4()])
        assert list(roles)==[UUID(need['role_id'])]
        assert await load_facts(db,context.foundation.id,[])=={}


@pytest.mark.asyncio
async def test_suggestions_filter_order_reasons_facts_and_invitation_status(context):
    event,need,first,second,_=await setup(context,group=True,capacity=5)
    url=f"/api/v1/coord/staffing-needs/{need['id']}/suggestions"
    async with context.db() as db:
        saved=await db.get(VolunteerRole,UUID(need['role_id']));saved.direction='Творчество';saved.skills=['Керамика','Валяние']
        for user_id,answers in ((first,{'directions':['Творчество'],'skills':['Валяние']}),(second,{'directions':['Творчество','Ярмарки']})):
            form=await db.scalar(select(FormVersion).where(FormVersion.foundation_id==context.foundation.id))
            if form is None:form=FormVersion(foundation_id=context.foundation.id,version=5,content={});db.add(form);await db.flush()
            application=Application(foundation_id=context.foundation.id,user_id=user_id);db.add(application);await db.flush()
            revision=ApplicationRevision(application_id=application.id,form_version_id=form.id,number=1,answers=answers,author_id='test');db.add(revision);await db.flush()
            application.submitted_revision_id=revision.id
            slot=await interview_slot(db,context)
            db.add(InterviewBooking(foundation_id=context.foundation.id,application_id=application.id,user_id=user_id,candidate_key=f'user:{user_id}',slot_id=slot.id,coordinator_id=context.principal.user_id,
                starts_at=slot.starts_at,ends_at=slot.ends_at,busy_until=slot.busy_until,venue='Офис',status='completed'))
        await availability(db,context,second,[(0,13*60,17*60)])
        unsure=await volunteer(db,context,'Вера',{'directions':['Пока не знаю']})
        nothing=await volunteer(db,context,'Глеб',{'directions':['Ярмарки']})
        anya=await volunteer(db,context,'Аня',{'directions':['Творчество']})
        # Яна never had a meeting in the system, but her confirmed shifts make her a known volunteer.
        yana=await volunteer(db,context,'Яна',{'directions':['Творчество']},meeting=None)
        far=await volunteer(db,context,'Из другого города',{'directions':['Творчество'],'skills':['Керамика'],'area':'Другой город'})
        excluded=[await volunteer(db,context,'Без встречи',{'directions':['Творчество'],'skills':['Керамика']},meeting='missed'),
            await volunteer(db,context,'Неактивный',{'directions':['Творчество'],'skills':['Керамика']},state='paused')]
        paused=await volunteer(db,context,'Пауза',{'directions':['Творчество'],'skills':['Керамика']})
        db.add(VolunteerProfile(user_id=paused.id,foundation_id=context.foundation.id,lifecycle='paused'))
        crm_paused=await volunteer(db,context,'CRM пауза',{'directions':['Творчество'],'skills':['Керамика']})
        db.add(CrmVolunteer(foundation_id=context.foundation.id,user_id=crm_paused.id,display_name='CRM',relationship_state='paused'))
        crm_quiet=await volunteer(db,context,'CRM не беспокоить',{'directions':['Творчество'],'skills':['Керамика']})
        db.add(CrmVolunteer(foundation_id=context.foundation.id,user_id=crm_quiet.id,display_name='CRM',no_contact=True))
        quiet=await volunteer(db,context,'Не беспокоить',{'directions':['Творчество'],'skills':['Керамика']})
        db.add(NotificationPreference(foundation_id=context.foundation.id,user_id=quiet.id,no_contact=True))
        foreign=User(foundation_id=context.other.id,display_name='Чужой фонд');db.add(foreign)
        excluded+=[paused,crm_paused,crm_quiet,quiet,foreign]
        await history(db,UUID(event['id']),UUID(need['id']),past_mondays(7),[(first,'attended'),(anya.id,'absent')])
        await history(db,UUID(event['id']),UUID(need['id']),past_mondays(5,first=8),[(anya.id,'attended'),(yana.id,'attended')])
        # Аня (5 visits) and Яна (7) earn the same capped score; more visits put Яна first despite the name order.
        await history(db,UUID(event['id']),UUID(need['id']),past_mondays(2,first=13),[(yana.id,'attended')])
        await db.commit()
        ids=dict(unsure=unsure.id,nothing=nothing.id,anya=anya.id,yana=yana.id,far=far.id)
        excluded_ids={str(user.id) for user in excluded}
    invited=await context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/invitations",headers=headers(),json={'expected_version':need['version'],'user_id':str(first)})
    assert invited.status_code==200,invited.text
    declined_row=await context.client.post(f"/api/v1/coord/staffing-needs/{need['id']}/invitations",headers=headers(),json={'expected_version':need['version'],'user_id':str(second)})
    assert declined_row.status_code==200,declined_row.text
    declined=await context.client.post(f"/api/v1/assignments/{declined_row.json()['id']}/decline",headers=user_headers('second','second-csrf'),json={'expected_version':declined_row.json()['version']})
    assert declined.status_code==200,declined.text
    response=await context.client.get(url)
    assert response.status_code==200,response.text
    rows=response.json()
    assert all(set(row)=={'user_id','display_name','reasons','missing_data','facts','invitation_status'} for row in rows) # never a score
    order=[row['user_id'] for row in rows]
    assert order==[str(first),str(ids['yana']),str(ids['anya']),str(second),str(ids['unsure']),str(ids['nothing'])],[row['display_name'] for row in rows]
    assert not excluded_ids & set(order) and str(context.principal.user_id) not in order and str(ids['far']) not in order
    by_id={row['user_id']:row for row in rows}
    top=by_id[str(first)]
    assert top['reasons']==['Подходит по навыку «Валяние»','7 посещений этой группы за полгода','Обычно приходит: пн, днём']
    assert top['facts']=={'invited':8,'confirmed':7,'attended':7} and top['invitation_status']=='invited' and top['missing_data']==[]
    assert by_id[str(ids['yana'])]['reasons']==['Подходит по направлению «Творчество»','7 посещений этой группы за полгода','Обычно приходит: пн, днём']
    assert by_id[str(ids['anya'])]['reasons'][1]=='5 посещений этой группы за полгода'
    assert by_id[str(ids['anya'])]['facts']=={'invited':12,'confirmed':12,'attended':5}
    other=by_id[str(second)]
    assert other['reasons']==['Подходит по направлению «Творчество»','Удобно по графику: пн, днём'] and other['invitation_status']=='declined'
    assert other['facts']=={'invited':1,'confirmed':0,'attended':0}
    assert by_id[str(ids['unsure'])]['reasons']==['В анкете: «Пока не знаю»'] and by_id[str(ids['unsure'])]['missing_data']==['availability']
    assert by_id[str(ids['nothing'])]['reasons']==[] and by_id[str(ids['nothing'])]['invitation_status'] is None
    # Name search narrows the candidates; another city is fine once the occurrence is not onsite.
    assert [row['display_name'] for row in (await context.client.get(url+'?q=second')).json()]==['Invented second volunteer']
    async with context.db() as db:
        row=await db.get(EventOccurrence,UUID(event['id']));row.format='hybrid';await db.commit()
    hybrid=[row['user_id'] for row in (await context.client.get(url)).json()]
    assert hybrid.index(str(ids['far']))==3 # skill match, no history, no windows: 0.4 + 0.1, between 0.84 and 0.44
    assert (await context.client.get(url,headers={'Cookie':'opora_session=self'})).status_code==403
    assert (await context.client.get(f'/api/v1/coord/staffing-needs/{uuid4()}/suggestions')).status_code==404
