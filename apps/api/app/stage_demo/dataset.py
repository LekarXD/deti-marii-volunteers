"""Explicit fictional facts for walkthroughs, not production imports or examples
silently loaded at runtime. Stable source seeders remain authoritative for content.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, time
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo
import pyotp
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.crypto import seal
from app.core.models import Foundation, User, ContactChannel, StaffMembership, PermissionGrant, MfaFactor, ResourceReservation
from app.modules.staff.catalog import LABELS, scopes
from .operator import FOUNDATION_NAME

ZONE=ZoneInfo('Europe/Moscow')

@dataclass(frozen=True)
class BootstrapActor:
    """Private seed transaction context. It cannot authenticate an HTTP request."""
    user_id:UUID
    foundation_id:UUID
    permissions:frozenset
    is_staff:bool=True
    registration_id:None=None
    @property
    def actor_id(self): return str(self.user_id)
    def has_permission(self,name,scope_type='foundation',scope_id=None): return name in self.permissions

async def populate(db, foundation_id):
    from app.modules.learning.seed import seed_introduction
    from app.modules.learning.models import LearningAssignment, LearningTrack
    from app.modules.applications.service import current_form
    from app.modules.applications.form import validate_answers, FORM_VERSION
    from app.modules.applications.models import Application, ApplicationRevision, ApplicationReviewEvent, ConsentEvent
    from app.modules.crm.models import CrmVolunteer, Agreement, FollowUpTask
    from app.modules.participants.models import ParticipantGroup, Participant, ParticipantBriefing, GroupMembership
    from app.modules.activities import service as activities, calendar_service
    from app.modules.activities.schemas import RoleCreate, OpportunityCreate, VersionCommand
    from app.modules.activities.calendar_schemas import EventSeriesCreate, StaffingNeedInput
    from app.modules.activities.calendar_models import EventOccurrence, StaffingNeed
    from app.modules.activities.assignment_models import Assignment, AssignmentEvent, Attendance, AttendanceEvent, AssignmentParticipantSnapshot
    from app.modules.activities.models import VolunteerRoleVersion
    from app.modules.profile.models import VolunteerProfile
    from app.modules.profile.ledger import append_service_time
    from app.modules.dobro import service as dobro, schemas as ds
    from app.modules.dobro.models import DobroSeriesOpportunity, DobroEnrollment, DobroEnrollmentEvent
    from app.modules.messaging.models import Conversation, ConversationMember, Message
    from app.modules.interviews.models import AvailabilitySeries, InterviewSlot, InterviewBooking, BookingEvent
    from app.modules.followups.models import Reflection, AssignmentQuestion
    from app.modules.knowledge.models import KnowledgeQuestion, KnowledgeSource
    from app.modules.studio.models import Webinar, WebinarEnrollment
    from app.modules.simulator.models import SimulatorScenario
    from app.modules.simulator.schemas import SimulatorScenarioDraft
    from app.modules.reporting.service import create_report
    from app.modules.reporting.schemas import ReportCreateCommand

    foundation=await db.get(Foundation,foundation_id)
    if foundation is None:
        foundation=Foundation(id=foundation_id,name=FOUNDATION_NAME)
        db.add(foundation)
        await db.flush()
    now=utcnow(); today=now.astimezone(ZONE).date()
    month=today.replace(day=1); previous=(month-timedelta(days=1)).replace(day=1)
    identities={}; people={}; private={}
    personas=[('coordinator','Координатор Демонстрационный'),('volunteer','Анна Демонстрационная'),('candidate','Новый Кандидат'),('polina','Полина Демонстрационная'),('igor','Игорь Демонстрационный'),('maria','Мария Демонстрационная')]
    for key,name in personas:
        person=User(foundation_id=foundation_id,display_name='[ДЕМО] '+name)
        db.add(person);await db.flush()
        email=f'{key}@example.test'
        db.add(ContactChannel(user_id=person.id,normalized_value=email,type='email',verified_at=now))
        people[key]=person
        identities[key]={'user_id':str(person.id),'email':email,'persona':name}
        if key=='coordinator':
            membership=StaffMembership(user_id=person.id,foundation_id=foundation_id)
            db.add(membership);await db.flush()
            grants=[name for name in LABELS if 'foundation' in scopes(name)]
            db.add_all([PermissionGrant(membership_id=membership.id,permission=name,scope_type='foundation') for name in grants])
            secret=pyotp.random_base32()
            # Ordinary /auth/mfa/verify confirms this fresh factor and rotates the
            # session. The seed never creates Session or sets mfa_at.
            db.add(MfaFactor(user_id=person.id,secret_cipher=seal(secret)))
            private[key]={'totp_secret':secret}
    coordinator=people['coordinator']
    actor=BootstrapActor(coordinator.id,foundation_id,frozenset(grants))
    await db.flush()
    track_id=await seed_introduction(db,foundation_id)
    track=await db.get(LearningTrack,track_id)
    form=await current_form(db,foundation_id,create=True)
    applications={}
    for key in ('volunteer','candidate','polina','igor','maria'):
        person=people[key]
        answers=validate_answers({'firstName':identities[key]['persona'].split()[0],'lastName':'Демонстрационная' if key not in ('candidate','igor') else 'Демонстрационный','birthdate':'1996-01-01','phone':'+7 (999) 000-00-'+str(10+len(applications)),'email':identities[key]['email'],'area':'Другой город','directions':['Творчество'],'participation':'Каждую неделю','volExp':'Нет','specialExp':'Нет','record':'Хочу обсудить','source':'Сайт фонда'},complete=True,form=form.content)
        application=Application(foundation_id=foundation_id,user_id=person.id,review_state='new' if key=='candidate' else 'discussed')
        db.add(application);await db.flush()
        revision=ApplicationRevision(application_id=application.id,form_version_id=form.id,number=1,answers=answers,author_id=str(person.id))
        db.add(revision);await db.flush()
        application.submitted_revision_id=revision.id
        db.add(ApplicationReviewEvent(application_id=application.id,kind='submitted',state=application.review_state,public_message='Полностью вымышленная демонстрационная анкета',author_id=actor.actor_id))
        db.add(ConsentEvent(application_id=application.id,document='privacy',document_version='4',purpose='personal_data',granted=True,author_id=str(person.id)))
        db.add(LearningAssignment(foundation_id=foundation_id,release_id=track.current_release_id,user_id=person.id))
        db.add(VolunteerProfile(user_id=person.id,foundation_id=foundation_id,about='Вымышленный профиль для демонстрации. Реальные персональные данные не используются.'))
        crm=CrmVolunteer(foundation_id=foundation_id,user_id=person.id,application_id=application.id,display_name=person.display_name,contacts={'email':identities[key]['email']},context='Вымышленный демонстрационный контакт',relationship_state='contacted' if key=='candidate' else 'active')
        db.add(crm);await db.flush()
        applications[key]=application
        if key=='volunteer':
            db.add(Agreement(volunteer_id=crm.id,role_context='Творческая мастерская',text='[ДЕМО] Обсудили знакомство с группой перед первым занятием.',author_id=coordinator.id))
            db.add(FollowUpTask(foundation_id=foundation_id,volunteer_id=crm.id,title='[ДЕМО] Уточнить удобный день',due_on=today+timedelta(days=2),assigned_user_id=coordinator.id,source_type='stage_demo',source_id=uuid4(),source_revision=1))
    historical=CrmVolunteer(foundation_id=foundation_id,display_name='[ДЕМО] Исторический контакт',contacts={},context='Связь с аккаунтом не установлена; готовность помогать не подтверждена.',relationship_state='unverified')
    db.add(historical)
    group=ParticipantGroup(foundation_id=foundation_id,title='[ДЕМО] Творческая группа',schedule='Пример расписания; не реальное занятие фонда',location='Демонстрационная мастерская',leader_id=coordinator.id,coordinator_id=coordinator.id)
    db.add(group);await db.flush()
    participant_ids=[]
    for index in range(1,4):
        participant=Participant(foundation_id=foundation_id,display_name=f'[ДЕМО] Участник {index}',birth_year=None,about='Полностью вымышленный персонаж. Фотографий и характеристик реальных подопечных здесь нет.')
        db.add(participant);await db.flush()
        participant_ids.append(participant.id)
        db.add(ParticipantBriefing(participant_id=participant.id,communication='[ДЕМО] Дайте время ответить и задавайте по одному вопросу.',support='[ДЕМО] Предлагайте помощь, не делайте за участника.',interests='[ДЕМО] Рисование, музыка, общение.'))
        db.add(GroupMembership(foundation_id=foundation_id,group_id=group.id,participant_id=participant.id,valid_from=previous))
    roles=[]
    for title,task in [('Ассистент педагога','Помогать участникам с материалами и быть рядом на занятии.'),('Волонтёр ярмарки','Подготовить продукцию, оформить стол и помочь гостям.'),('Предметный фотограф','Сделать фотографии изделий в спокойной обстановке.')]:
        roles.append(await activities.create_role(db,actor,RoleCreate(title=title+' [ДЕМО]',task=task)))
    opportunities=[]; links=[]
    for index,title in enumerate(['Творческая мастерская','Ярмарка и упаковка']):
        item=await activities.create_opportunity(db,actor,OpportunityCreate(title=title+' [ДЕМО]',role_ids=[roles[index].id],program='opora-stage-synthetic-v1',audience='Вымышленные участники демонстрационного контура',conditions='Это демонстрация, а не объявление реального фонда.',regularity='regular',location='Демонстрационная мастерская',schedule='Даты примера выбирает координатор'))
        item=await activities.change_opportunity_state(db,actor,item.id,VersionCommand(expected_version=item.version),'published')
        opportunities.append(item)
        links.append(await dobro.create_link(db,actor,item.id,ds.DobroActivityCommand(title=title+' — демонстрационный сезон',url='https://dobro.ru/',kind='long_term',valid_from=previous,valid_until=(today+timedelta(days=180)))))
    events=[]; assignments={}
    async def event(day,title,minutes=120,hour=14,capacity=3,opportunity_index=0,with_group=False):
        series=await calendar_service.create_series(db,actor,EventSeriesCreate(title=title+' [ДЕМО]',program='opora-stage-synthetic-v1',start_date=day,start_time=time(hour),timezone='Europe/Moscow',duration_minutes=minutes,location='Демонстрационная мастерская',group_id=group.id if with_group else None,staffing_needs=[StaffingNeedInput(role_id=roles[opportunity_index].id,capacity_required=capacity)]))
        db.add(DobroSeriesOpportunity(series_id=series.id,foundation_id=foundation_id,opportunity_id=opportunities[opportunity_index].id,actor_id=actor.actor_id))
        await db.flush()
        occurrence=await db.scalar(select(EventOccurrence).where(EventOccurrence.series_id==series.id))
        events.append(occurrence)
        return occurrence
    async def assign(person_key,occurrence,status='confirmed',minutes=None):
        person=people[person_key]
        need=await db.scalar(select(StaffingNeed).where(StaffingNeed.occurrence_id==occurrence.id))
        row=Assignment(foundation_id=foundation_id,user_id=person.id,occurrence_id=occurrence.id,staffing_need_id=need.id,group_id_snapshot=occurrence.group_id,status=status,approved_at=now-timedelta(days=1),confirmed_at=now-timedelta(days=1) if status=='confirmed' else None,conditions_version=1,conditions_snapshot={'role_version_id':str(need.role_version_id),'preparation_requirements':need.preparation_requirements,'approval_policy':'coordinator'})
        db.add(row);await db.flush()
        if status=='confirmed': db.add(ResourceReservation(foundation_id=foundation_id,user_id=person.id,owner_key=f'user:{person.id}',source_type='activity',source_id=row.id,starts_at=occurrence.starts_at,busy_until=occurrence.ends_at,active=True))
        db.add(AssignmentEvent(assignment_id=row.id,version=1,command='seed_synthetic',status=status,reason='Вымышленное начальное состояние демонстрации',actor_id=actor.actor_id))
        if occurrence.group_id:
            for participant_id in participant_ids: db.add(AssignmentParticipantSnapshot(assignment_id=row.id,participant_id=participant_id,foundation_id=foundation_id))
        if minutes is not None:
            attendance=Attendance(foundation_id=foundation_id,assignment_id=row.id,outcome='attended' if minutes else 'absent',minutes=minutes)
            db.add(attendance);await db.flush()
            entry=AttendanceEvent(foundation_id=foundation_id,attendance_id=attendance.id,assignment_id=row.id,user_id=person.id,version=1,old_minutes=0,new_minutes=minutes,reason='Вымышленное посещение для демонстрации',actor_id=actor.actor_id)
            db.add(entry);await db.flush()
            await append_service_time(db,actor,person.id,row.id,entry.id)
        assignments.setdefault(person_key,[]).append(row)
        return row
    future=await event(today+timedelta(days=1),'Ближайшая творческая встреча',with_group=True)
    await assign('volunteer',future)
    await assign('polina',future,'invited')
    await event(today+timedelta(days=3),'Подготовка ярмарки',opportunity_index=1,capacity=2)
    await event(today+timedelta(days=5),'Творческая мастерская',with_group=True,capacity=2)
    past=await event(today-timedelta(days=2),'Завершённая творческая встреча',minutes=180,capacity=4)
    for key,minutes in [('volunteer',120),('polina',90),('maria',120)]: await assign(key,past,minutes=minutes)
    first=await event(today-timedelta(days=3),'Утренняя мастерская',minutes=360,hour=8,capacity=1)
    second=await event(today-timedelta(days=3),'Подготовка ярмарки вечером',minutes=240,hour=14,capacity=1,opportunity_index=1)
    await assign('igor',first,minutes=360);await assign('igor',second,minutes=240)
    older=await event(previous+timedelta(days=2),'Прошлый месяц',minutes=100,capacity=1)
    await assign('volunteer',older,minutes=100)
    for person_key,link_index,state in [('volunteer',0,'approved'),('polina',0,'applied'),('igor',0,'approved'),('igor',1,'approved'),('maria',0,'not_needed')]:
        enrollment=DobroEnrollment(foundation_id=foundation_id,user_id=people[person_key].id,activity_id=links[link_index].id,state=state)
        db.add(enrollment);await db.flush()
        db.add(DobroEnrollmentEvent(enrollment_id=enrollment.id,version=1,state=state,actor_id=actor.actor_id,reason='Вымышленный пример статуса'))
    await db.flush()
    historic=await dobro.transfer_period(db,actor,previous.strftime('%Y-%m'))
    for item in historic.groups:
        if item.activity.id==links[0].id:
            row=next((row for row in item.rows if row.user_id==people['volunteer'].id and row.hours_due>0),None)
            if row: await dobro.mark_entered(db,actor,ds.DobroMarkCommand(confirmed=True,note='Вымышленный перенос: CRM Добро.рф не использовалась',rows=[ds.DobroMarkRow(id=row.id,user_id=row.user_id,activity_id=item.activity.id,period=historic.period,snapshot_hash=row.snapshot_hash,hours_delta=row.hours_due)]))
    completed=assignments['volunteer'][1]
    db.add(Reflection(foundation_id=foundation_id,assignment_id=completed.id,user_id=people['volunteer'].id,group_id=completed.group_id_snapshot,mood='good',text='[ДЕМО] Понравилось помогать с материалами.',unexpected='[ДЕМО] Было больше общения, чем ожидалось.',help='yes',help_text='[ДЕМО] Хочу обсудить следующую встречу.',continuation='yes',submitted_at=now))
    db.add(AssignmentQuestion(foundation_id=foundation_id,assignment_id=assignments['volunteer'][0].id,user_id=people['volunteer'].id,group_id=group.id,text='[ДЕМО] Какие материалы подготовить к встрече?'))
    window=AvailabilitySeries(foundation_id=foundation_id,coordinator_id=coordinator.id,local_start_date=today+timedelta(days=1),start_minute=10*60,end_minute=12*60,duration_minutes=30,buffer_after_minutes=10,venue='[ДЕМО] Онлайн-знакомство, без реальной ссылки')
    db.add(window);await db.flush()
    for index in range(3):
        starts=datetime.combine(today+timedelta(days=1),time(10),ZONE)+timedelta(minutes=40*index)
        slot=InterviewSlot(foundation_id=foundation_id,series_id=window.id,coordinator_id=coordinator.id,origin_date=starts.date(),origin_minute=starts.hour*60+starts.minute,starts_at=starts,ends_at=starts+timedelta(minutes=30),busy_until=starts+timedelta(minutes=40))
        db.add(slot);await db.flush()
        if index==0:
            booking=InterviewBooking(foundation_id=foundation_id,application_id=applications['candidate'].id,user_id=people['candidate'].id,candidate_key=f'user:{people["candidate"].id}',slot_id=slot.id,coordinator_id=coordinator.id,starts_at=slot.starts_at,ends_at=slot.ends_at,busy_until=slot.busy_until,venue=window.venue)
            db.add(booking);await db.flush()
            from app.modules.interviews.service import reserve
            await reserve(db,booking)
            db.add(BookingEvent(booking_id=booking.id,kind='booked',actor_id=actor.actor_id,after={'status':'booked','fixture':True}))
    conversation=Conversation(foundation_id=foundation_id,title='[ДЕМО] Команда мастерской',kind='group',direct_key='stage-demo-team',created_by_user_id=coordinator.id,last_seq=1)
    db.add(conversation);await db.flush()
    db.add_all([ConversationMember(conversation_id=conversation.id,user_id=person.id) for person in people.values()])
    db.add(Message(conversation_id=conversation.id,author_user_id=coordinator.id,seq=1,text='Это демонстрационный чат. Все люди, события и договорённости здесь вымышлены. Сообщения за пределы платформы не отправляются.'))
    db.add(KnowledgeQuestion(foundation_id=foundation_id,user_id=people['volunteer'].id,text='[ДЕМО] Как подготовиться к первому занятию?'))
    db.add(KnowledgeSource(foundation_id=foundation_id,owner_user_id=coordinator.id,title='[ДЕМО] Памятка перед встречей',draft_body='Это вымышленный черновик. Проверьте адрес, время и договорённости с координатором.',draft_visibility='all'))
    draft=SimulatorScenarioDraft(title='[ДЕМО] Спокойный разговор',character_name='Вымышленный участник',character_profile='Полностью вымышленный персонаж для авторского черновика.',situation='Участник хочет отложить задание.',first_turn='Можно я немного отдохну?',warning='Демонстрационный черновик; не опубликован и не оценён ИИ.')
    db.add(SimulatorScenario(foundation_id=foundation_id,title=draft.title,draft=draft.model_dump(mode='json'),updated_by=actor.actor_id))
    webinar=Webinar(foundation_id=foundation_id,host_user_id=coordinator.id,title='[ДЕМО] Встреча волонтёров онлайн',description='Демонстрационное событие. Провайдер эфира и записи отдельно настраивается оператором.',starts_at=datetime.combine(today+timedelta(days=2),time(18),ZONE),duration_minutes=60,state='published')
    db.add(webinar);await db.flush()
    db.add(WebinarEnrollment(foundation_id=foundation_id,webinar_id=webinar.id,user_id=people['volunteer'].id))
    await db.flush()
    report=await create_report(db,actor,ReportCreateCommand(title='[ДЕМО] Отчёт о волонтёрской помощи',period_from=previous,period_to=today,scope_type='foundation'))
    manifest={'seed_version':1,'synthetic_only':True,'anchor_date':str(today),'form_version':FORM_VERSION,'introduction_release_id':str(track.current_release_id),'identities':identities,'opportunities':[str(item.id) for item in opportunities],'group_id':str(group.id),'event_ids':[str(item.id) for item in events],'report_id':str(report.id),'webinar_id':str(webinar.id),'no_real_photos':True,'no_external_messages':True}
    return {'identities':{key:{**value,**private.get(key,{})} for key,value in identities.items()}},manifest
