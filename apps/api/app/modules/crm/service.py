from datetime import date, datetime
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from sqlalchemy import select, func, text, or_
from app.core.auth import Principal
from app.core.errors import ApiError
from app.core.models import StaffMembership, User
from app.modules.applications.models import Application, ApplicationRevision
from .models import (CrmVolunteer,Agreement,ContactEvent,AvailabilityRule,AvailabilityWindow,AvailabilityVerification,
    ReserveReview,FollowUpTask,FollowUpTaskEvent,FollowUpSource,ImportBatch,ImportRow,ImportEffect,ImportExternalReference,MergeReview,utcnow)
from .schemas import (CrmVolunteerSummary,CrmVolunteerView,AgreementView,ContactEventView,AvailabilityView,
    AvailabilityWindowInput,FollowUpTaskView,ReserveReviewView,OwnAvailabilityView)


def today():
    return utcnow().astimezone(ZoneInfo('Europe/Moscow')).date()


def check_version(actual,expected):
    if actual!=expected:
        raise ApiError(409,'version_conflict','Данные изменились. Обновите карточку и повторите действие',current_version=actual)


def nonempty(value,label='Заполните поле'):
    if not value.strip():raise ApiError(422,'validation_error',label)
    return value.strip()


async def scoped_volunteer(db,foundation_id,volunteer_id,lock=False,allow_alias=False):
    query=select(CrmVolunteer).where(CrmVolunteer.foundation_id==foundation_id,CrmVolunteer.id==volunteer_id)
    if lock:query=query.with_for_update()
    value=await db.scalar(query)
    if not value:raise ApiError(404,'volunteer_not_found','Волонтёр не найден')
    if value.merged_into_id and not allow_alias:
        raise ApiError(409,'volunteer_merged','Карточка объединена. Откройте актуальную карточку',field_errors={'merged_into_id':str(value.merged_into_id)})
    return value


async def ensure_volunteer(db,foundation_id,application_id):
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'crm-application:{foundation_id}:{application_id}'})
    value=await db.scalar(select(CrmVolunteer).where(CrmVolunteer.foundation_id==foundation_id,CrmVolunteer.application_id==application_id))
    if value:return await scoped_volunteer(db,foundation_id,value.merged_into_id or value.id)
    application=await db.scalar(select(Application).where(Application.foundation_id==foundation_id,Application.id==application_id))
    if not application:raise ApiError(404,'application_not_found','Анкета не найдена')
    revision=await db.get(ApplicationRevision,application.submitted_revision_id)
    if not revision:raise ApiError(409,'application_incomplete','Анкета не завершена')
    if application.user_id:
        current=await db.scalar(select(CrmVolunteer).where(CrmVolunteer.foundation_id==foundation_id,CrmVolunteer.user_id==application.user_id,CrmVolunteer.merged_into_id.is_(None)))
        if current:
            if current.application_id is None:current.application_id=application.id
            return current
    answers=revision.answers
    value=CrmVolunteer(foundation_id=foundation_id,user_id=application.user_id,application_id=application.id,
        display_name=' '.join(str(answers.get(key,'')) for key in ('firstName','lastName')).strip(),
        contacts={key:str(answers[key]) for key in ('phone','email','telegram') if answers.get(key)},context='Анкета волонтёра',relationship_state='unverified')
    db.add(value);await db.flush();return value


async def alias_ids(db,volunteer):
    # Merge points directly at the canonical target; no user/assignment identity rewrites.
    return [volunteer.id,*list((await db.scalars(select(CrmVolunteer.id).where(CrmVolunteer.foundation_id==volunteer.foundation_id,CrmVolunteer.merged_into_id==volunteer.id))).all())]


async def availability_view(db,volunteer):
    rule=await db.scalar(select(AvailabilityRule).where(AvailabilityRule.volunteer_id==volunteer.id).order_by(AvailabilityRule.number.desc()).limit(1))
    if not rule:return None
    verification=await db.scalar(select(AvailabilityVerification).where(AvailabilityVerification.rule_id==rule.id).order_by(AvailabilityVerification.verified_at.desc()).limit(1))
    windows=(await db.scalars(select(AvailabilityWindow).where(AvailabilityWindow.rule_id==rule.id).order_by(AvailabilityWindow.weekday,AvailabilityWindow.start_minute))).all()
    return AvailabilityView(id=rule.id,number=rule.number,summary=rule.summary,timezone=rule.timezone,preferred_channel=rule.preferred_channel,
        windows=[AvailabilityWindowInput(weekday=w.weekday,start_minute=w.start_minute,end_minute=w.end_minute) for w in windows],
        verified_at=verification.verified_at if verification else None,valid_until=verification.valid_until if verification else None,
        verified=bool(verification and verification.valid_until>=today()))


def task_view(task):
    return FollowUpTaskView(id=task.id,volunteer_id=task.volunteer_id,application_id=task.application_id,assigned_user_id=task.assigned_user_id,
        due_on=task.due_on,title=task.title,state=task.state,version=task.version,source_type=task.source_type,source_id=task.source_id,
        source_revision=task.source_revision,completed_at=task.completed_at)


async def readiness(db,volunteer):
    availability=await availability_view(db,volunteer)
    agreement=await db.scalar(select(Agreement).where(Agreement.volunteer_id==volunteer.id).order_by(Agreement.created_at.desc(),Agreement.id).limit(1))
    reasons=[]
    if volunteer.no_contact:reasons.append('Человек попросил не связываться')
    if not availability or not availability.verified:reasons.append('Уточните актуальную доступность')
    if not agreement or (agreement.valid_until and agreement.valid_until<today()):reasons.append('Нужна актуальная договорённость')
    if volunteer.relationship_state not in ('ready','active'):reasons.append('Участие пока не согласовано')
    return availability,reasons


async def volunteer_view(db,volunteer,detail=False):
    availability,reasons=await readiness(db,volunteer)
    ids=await alias_ids(db,volunteer)
    tasks=(await db.scalars(select(FollowUpTask).where(FollowUpTask.foundation_id==volunteer.foundation_id,FollowUpTask.volunteer_id.in_(ids)).order_by(FollowUpTask.due_on,FollowUpTask.created_at))).all()
    next_task=next((task_view(task) for task in tasks if task.state=='open'),None)
    values=dict(id=volunteer.id,application_id=volunteer.application_id,display_name=volunteer.display_name,contacts=volunteer.contacts,context=volunteer.context,
        relationship_state=volunteer.relationship_state,no_contact=volunteer.no_contact,version=volunteer.version,merged_into_id=volunteer.merged_into_id,
        can_invite=not reasons,blocked_reasons=reasons,availability=availability,next_task=next_task)
    if not detail:return CrmVolunteerSummary(**values)
    agreements=(await db.scalars(select(Agreement).where(Agreement.volunteer_id.in_(ids)).order_by(Agreement.created_at.desc(),Agreement.id))).all()
    events=(await db.scalars(select(ContactEvent).where(ContactEvent.volunteer_id.in_(ids)).order_by(ContactEvent.occurred_at.desc(),ContactEvent.id))).all()
    reviews=(await db.scalars(select(ReserveReview).where(ReserveReview.volunteer_id.in_(ids)).order_by(ReserveReview.created_at.desc(),ReserveReview.id))).all()
    provenance=(await db.execute(select(ImportEffect,ImportRow,ImportBatch).join(ImportRow,ImportEffect.row_id==ImportRow.id).join(ImportBatch,ImportRow.batch_id==ImportBatch.id)
        .where(ImportEffect.volunteer_id.in_(ids),ImportBatch.foundation_id==volunteer.foundation_id).order_by(ImportEffect.created_at))).all()
    return CrmVolunteerView(**values,agreements=[AgreementView(id=a.id,text=a.text,role_context=a.role_context,valid_until=a.valid_until,created_at=a.created_at) for a in agreements],
        contact_events=[ContactEventView(id=e.id,kind=e.kind,direction=e.direction,text=e.text,occurred_at=e.occurred_at) for e in events],
        follow_up_tasks=[task_view(task) for task in tasks],reviews=[ReserveReviewView(id=r.id,outcome=r.outcome,note=r.note,no_contact=r.no_contact,created_at=r.created_at) for r in reviews],
        merged_record_ids=ids[1:],import_provenance=[dict(batch_id=str(batch.id),filename=batch.filename,checksum=batch.checksum,source_system=batch.source_system,line_number=row.line_number,snapshot=effect.snapshot,created_at=effect.created_at.isoformat()) for effect,row,batch in provenance])


async def valid_owner(db,foundation_id,user_id):
    membership=await db.scalar(select(StaffMembership).join(User,StaffMembership.user_id==User.id).where(StaffMembership.foundation_id==foundation_id,
        StaffMembership.user_id==user_id,StaffMembership.revoked_at.is_(None),User.account_state=='active'))
    if not membership:raise ApiError(422,'invalid_task_owner','Выберите сотрудника фонда, который отвечает за следующий шаг')


def touch(volunteer):
    volunteer.version+=1;volunteer.updated_at=utcnow()


async def add_agreement(db,principal,volunteer_id,command):
    volunteer=await scoped_volunteer(db,principal.foundation_id,volunteer_id,lock=True);check_version(volunteer.version,command.expected_version)
    if command.valid_until and command.valid_until<today():raise ApiError(422,'agreement_expired','Срок договорённости уже прошёл')
    previous=await db.scalar(select(Agreement).where(Agreement.volunteer_id==volunteer.id).order_by(Agreement.created_at.desc()).limit(1))
    db.add(Agreement(volunteer_id=volunteer.id,text=nonempty(command.text),role_context=command.role_context.strip(),valid_until=command.valid_until,
        supersedes_id=previous.id if previous else None,author_id=principal.actor_id));await db.flush()
    if command.relationship_state:
        if command.relationship_state in ('ready','active'):
            availability,_=await readiness(db,volunteer)
            if volunteer.no_contact or not availability or not availability.verified:
                raise ApiError(422,'availability_required','Перед приглашением подтвердите актуальную доступность и разрешение на связь')
        volunteer.relationship_state=command.relationship_state
    touch(volunteer);await db.flush();return await volunteer_view(db,volunteer,True)


async def add_contact(db,principal,volunteer_id,command):
    volunteer=await scoped_volunteer(db,principal.foundation_id,volunteer_id,lock=True);check_version(volunteer.version,command.expected_version)
    if volunteer.no_contact and command.direction=='outgoing':raise ApiError(409,'no_contact','Человек попросил не связываться')
    when=command.occurred_at or utcnow()
    if when.tzinfo is None:raise ApiError(422,'timezone_required','Укажите время связи с часовым поясом')
    if when>utcnow():raise ApiError(422,'future_contact','Будущую связь запишите следующим действием')
    db.add(ContactEvent(volunteer_id=volunteer.id,kind=command.kind,direction=command.direction,text=nonempty(command.text),author_id=principal.actor_id,occurred_at=when))
    touch(volunteer);await db.flush();return await volunteer_view(db,volunteer,True)


async def write_availability(db,volunteer,principal,command):
    try:ZoneInfo(command.timezone)
    except (ZoneInfoNotFoundError,ValueError):raise ApiError(422,'invalid_timezone','Выберите существующий часовой пояс')
    for window in command.windows:
        if window.start_minute>=window.end_minute:raise ApiError(422,'invalid_availability_window','Окончание должно быть позже начала')
    windows=sorted(command.windows,key=lambda w:(w.weekday,w.start_minute))
    for left,right in zip(windows,windows[1:]):
        if left.weekday==right.weekday and left.end_minute>right.start_minute:raise ApiError(422,'overlapping_availability','Периоды доступности пересекаются')
    number=(await db.scalar(select(func.coalesce(func.max(AvailabilityRule.number),0)).where(AvailabilityRule.volunteer_id==volunteer.id)))+1
    rule=AvailabilityRule(volunteer_id=volunteer.id,number=number,summary=nonempty(command.summary),timezone=command.timezone,
        preferred_channel=command.preferred_channel,author_id=principal.actor_id)
    db.add(rule);await db.flush()
    for window in windows:db.add(AvailabilityWindow(rule_id=rule.id,**window.model_dump()))
    await db.flush();return rule


async def save_availability(db,principal,volunteer_id,command):
    volunteer=await scoped_volunteer(db,principal.foundation_id,volunteer_id,lock=True);check_version(volunteer.version,command.expected_version)
    await write_availability(db,volunteer,principal,command);touch(volunteer);await db.flush();return await volunteer_view(db,volunteer,True)


async def verify_availability(db,principal,volunteer_id,command):
    volunteer=await scoped_volunteer(db,principal.foundation_id,volunteer_id,lock=True);check_version(volunteer.version,command.expected_version)
    if command.valid_until<today():raise ApiError(422,'verification_expired','Подтверждение должно действовать сейчас')
    rule=await db.scalar(select(AvailabilityRule).where(AvailabilityRule.volunteer_id==volunteer.id).order_by(AvailabilityRule.number.desc()).limit(1))
    if not rule:raise ApiError(422,'availability_required','Сначала уточните доступность')
    db.add(AvailabilityVerification(rule_id=rule.id,valid_until=command.valid_until,source=nonempty(command.source),author_id=principal.actor_id))
    touch(volunteer);await db.flush();return await volunteer_view(db,volunteer,True)


async def cancel_open_tasks(db,volunteer,principal,reason):
    ids=await alias_ids(db,volunteer)
    tasks=(await db.scalars(select(FollowUpTask).where(FollowUpTask.foundation_id==volunteer.foundation_id,FollowUpTask.volunteer_id.in_(ids),FollowUpTask.state=='open').with_for_update())).all()
    for task in tasks:
        before=task_view(task).model_dump(mode='json');task.state='cancelled';task.version+=1
        db.add(FollowUpTaskEvent(task_id=task.id,kind='cancelled',reason=reason,before=before,after=task_view(task).model_dump(mode='json'),author_id=principal.actor_id))


async def set_preference(db,principal,volunteer_id,command):
    volunteer=await scoped_volunteer(db,principal.foundation_id,volunteer_id,lock=True);check_version(volunteer.version,command.expected_version)
    if volunteer.no_contact and not command.no_contact and not command.renewed_consent_confirmed:
        raise ApiError(422,'renewed_consent_required','Подтвердите, что человек снова разрешил связываться')
    volunteer.no_contact=command.no_contact
    db.add(ContactEvent(volunteer_id=volunteer.id,kind='preference',direction='recorded',text=nonempty(command.reason),author_id=principal.actor_id))
    if volunteer.no_contact:await cancel_open_tasks(db,volunteer,principal,'Просьба не связываться')
    touch(volunteer);await db.flush();return await volunteer_view(db,volunteer,True)


async def record_review(db,principal,volunteer_id,command):
    volunteer=await scoped_volunteer(db,principal.foundation_id,volunteer_id,lock=True);check_version(volunteer.version,command.expected_version)
    if volunteer.no_contact and not command.no_contact:raise ApiError(409,'renewed_consent_required','Просьба не связываться действует. Измените её отдельно после согласия человека')
    if command.availability:
        rule=await write_availability(db,volunteer,principal,command.availability)
        if command.valid_until:
            if command.valid_until<today():raise ApiError(422,'verification_expired','Укажите актуальный срок подтверждения')
            db.add(AvailabilityVerification(rule_id=rule.id,valid_until=command.valid_until,source='contact_review',author_id=principal.actor_id))
    if command.agreement_text.strip():db.add(Agreement(volunteer_id=volunteer.id,text=command.agreement_text.strip(),role_context='',author_id=principal.actor_id))
    volunteer.no_contact=command.no_contact
    await db.flush()
    if command.outcome=='ready':
        availability,reasons=await readiness(db,volunteer)
        if volunteer.no_contact or not availability or not availability.verified or 'Нужна актуальная договорённость' in reasons:
            raise ApiError(422,'readiness_requirements','Готовность требует актуальной доступности, договорённости и разрешения на связь')
    volunteer.relationship_state=command.outcome
    note=nonempty(command.note)
    db.add(ReserveReview(volunteer_id=volunteer.id,outcome=command.outcome,note=note,no_contact=volunteer.no_contact,author_id=principal.actor_id))
    db.add(ContactEvent(volunteer_id=volunteer.id,kind='contact_review',direction='recorded',text=note,author_id=principal.actor_id))
    if volunteer.no_contact:await cancel_open_tasks(db,volunteer,principal,'Просьба не связываться')
    touch(volunteer);await db.flush();return await volunteer_view(db,volunteer,True)


async def create_task(db,principal,volunteer_id,command):
    volunteer=await scoped_volunteer(db,principal.foundation_id,volunteer_id,lock=True);check_version(volunteer.version,command.expected_version)
    if volunteer.no_contact:raise ApiError(409,'no_contact','Человек попросил не связываться')
    await valid_owner(db,principal.foundation_id,command.assigned_user_id)
    task=FollowUpTask(foundation_id=principal.foundation_id,volunteer_id=volunteer.id,application_id=volunteer.application_id,
        assigned_user_id=command.assigned_user_id,due_on=command.due_on,title=nonempty(command.title),source_type='manual',source_id=uuid4(),source_revision=1)
    db.add(task);touch(volunteer);await db.flush()
    db.add(FollowUpTaskEvent(task_id=task.id,kind='created',reason='',after=task_view(task).model_dump(mode='json'),author_id=principal.actor_id))
    await db.flush();return task_view(task)


async def update_task(db,principal,task_id,command):
    # Same volunteer->task lock order as no-contact cancellation and result scheduling.
    task=await db.scalar(select(FollowUpTask).where(FollowUpTask.foundation_id==principal.foundation_id,FollowUpTask.id==task_id))
    if not task:raise ApiError(404,'task_not_found','Следующее действие не найдено')
    volunteer=await scoped_volunteer(db,principal.foundation_id,task.volunteer_id,lock=True)
    task=await db.scalar(select(FollowUpTask).where(FollowUpTask.id==task_id).with_for_update());check_version(task.version,command.expected_version)
    if task.state!='open':raise ApiError(409,'task_closed','Действие уже завершено. Создайте следующий шаг отдельно')
    if volunteer.no_contact and command.state=='open':raise ApiError(409,'no_contact','Человек попросил не связываться')
    before=task_view(task).model_dump(mode='json')
    if command.assigned_user_id:await valid_owner(db,principal.foundation_id,command.assigned_user_id);task.assigned_user_id=command.assigned_user_id
    if command.title is not None:task.title=nonempty(command.title)
    if command.due_on is not None:task.due_on=command.due_on
    if command.state:task.state=command.state
    if task.state=='done':task.completed_at=utcnow()
    task.version+=1;touch(volunteer)
    db.add(FollowUpTaskEvent(task_id=task.id,kind=task.state,reason=nonempty(command.reason),before=before,after=task_view(task).model_dump(mode='json'),author_id=principal.actor_id))
    await db.flush();return task_view(task)


async def schedule_follow_up(db,foundation_id,application_id,assigned_user_id,due_on,source_type,source_id,source_revision,actor_id,title='Связаться с волонтёром'):
    """P06 integration boundary, in caller's transaction; never sends a message."""
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'follow-up:{foundation_id}:{source_type}:{source_id}'})
    from app.core.idempotency import payload_hash
    fingerprint=payload_hash(dict(application_id=application_id,assigned_user_id=assigned_user_id,due_on=due_on,title=title))
    source=await db.scalar(select(FollowUpSource).where(FollowUpSource.foundation_id==foundation_id,FollowUpSource.source_type==source_type,FollowUpSource.source_id==source_id).with_for_update())
    if source:
        if source.current_revision>source_revision:raise ApiError(409,'stale_follow_up_source','Итог встречи уже изменился')
        if source.current_revision==source_revision:
            if source.payload_hash!=fingerprint:raise ApiError(409,'follow_up_source_conflict','Версия итога уже использована с другими данными')
            old_task=await db.get(FollowUpTask,source.task_id) if source.task_id else None
            return task_view(old_task) if old_task else None
    else:
        source=FollowUpSource(foundation_id=foundation_id,source_type=source_type,source_id=source_id,current_revision=source_revision,payload_hash=fingerprint)
        db.add(source)
    source.current_revision=source_revision;source.payload_hash=fingerprint;source.task_id=None
    volunteer=await ensure_volunteer(db,foundation_id,application_id)
    volunteer=await scoped_volunteer(db,foundation_id,volunteer.id,lock=True)
    tasks=(await db.scalars(select(FollowUpTask).where(FollowUpTask.foundation_id==foundation_id,FollowUpTask.source_type==source_type,
        FollowUpTask.source_id==source_id).with_for_update())).all()
    if any(task.source_revision>source_revision for task in tasks):raise ApiError(409,'stale_follow_up_source','Итог встречи уже изменился')
    for task in tasks:
        if task.state=='open':
            before=task_view(task).model_dump(mode='json');task.state='cancelled';task.version+=1
            db.add(FollowUpTaskEvent(task_id=task.id,kind='superseded',reason='Итог встречи изменился',before=before,after=task_view(task).model_dump(mode='json'),author_id=actor_id))
    if due_on is None or volunteer.no_contact:
        await db.flush();return None
    await valid_owner(db,foundation_id,assigned_user_id)
    task=FollowUpTask(foundation_id=foundation_id,volunteer_id=volunteer.id,application_id=application_id,assigned_user_id=assigned_user_id,
        due_on=due_on,title=nonempty(title),source_type=source_type,source_id=source_id,source_revision=source_revision)
    db.add(task);touch(volunteer);await db.flush();source.task_id=task.id
    db.add(FollowUpTaskEvent(task_id=task.id,kind='created',reason='Следующий контакт после встречи',after=task_view(task).model_dump(mode='json'),author_id=actor_id))
    await db.flush();return task_view(task)


async def merge_volunteers(db,principal,source_id,command):
    if source_id==command.target_id:raise ApiError(422,'same_record','Выберите другую карточку')
    rows={}
    for record_id in sorted((source_id,command.target_id),key=str):rows[record_id]=await scoped_volunteer(db,principal.foundation_id,record_id,lock=True)
    source,target=rows[source_id],rows[command.target_id]
    check_version(source.version,command.expected_version);check_version(target.version,command.target_expected_version)
    if source.user_id and target.user_id and source.user_id!=target.user_id:raise ApiError(409,'identity_merge_forbidden','Это разные подтверждённые аккаунты. Объединение аккаунтов здесь недоступно')
    if source.application_id and target.application_id and source.application_id!=target.application_id:raise ApiError(409,'application_merge_forbidden','Две анкеты нельзя объединить через карточку контакта')
    target.no_contact=source.no_contact or target.no_contact
    move_user=source.user_id if target.user_id is None else None
    move_application=source.application_id if target.application_id is None else None
    if move_user:source.user_id=None
    if move_application:source.application_id=None
    await db.flush()
    if move_user:target.user_id=move_user
    if move_application:target.application_id=move_application
    target.contacts={**source.contacts,**target.contacts}
    source.merged_into_id=target.id
    aliases=(await db.scalars(select(CrmVolunteer).where(CrmVolunteer.foundation_id==principal.foundation_id,CrmVolunteer.merged_into_id==source.id))).all()
    for alias in aliases:alias.merged_into_id=target.id
    reason=nonempty(command.reason)
    db.add(MergeReview(foundation_id=principal.foundation_id,source_volunteer_id=source.id,target_volunteer_id=target.id,state='merged',reason=reason,author_id=principal.actor_id))
    db.add(ContactEvent(volunteer_id=target.id,kind='merged',direction='recorded',text=reason,author_id=principal.actor_id))
    touch(source);touch(target)
    await db.flush()
    if target.no_contact:await cancel_open_tasks(db,target,principal,'Объединена просьба не связываться')
    return await volunteer_view(db,target,True)


async def own_volunteer(db,principal):
    if principal.user_id:
        value=await db.scalar(select(CrmVolunteer).where(CrmVolunteer.foundation_id==principal.foundation_id,CrmVolunteer.user_id==principal.user_id,CrmVolunteer.merged_into_id.is_(None)))
        if value:return value
    from app.modules.applications.service import own_application
    application=await own_application(db,principal,required=False)
    if not application:return None
    return await db.scalar(select(CrmVolunteer).where(CrmVolunteer.foundation_id==principal.foundation_id,CrmVolunteer.application_id==application.id,CrmVolunteer.merged_into_id.is_(None)))


async def own_availability(db,principal):
    volunteer=await own_volunteer(db,principal)
    return OwnAvailabilityView(volunteer_id=volunteer.id if volunteer else None,version=volunteer.version if volunteer else 0,
        availability=await availability_view(db,volunteer) if volunteer else None,no_contact=volunteer.no_contact if volunteer else False)


async def claim_registration(db,registration_id,user_id):
    user=await db.get(User,user_id)
    if not user:return
    rows=(await db.scalars(select(CrmVolunteer).join(Application,CrmVolunteer.application_id==Application.id).where(
        CrmVolunteer.foundation_id==user.foundation_id,Application.user_id==user_id,CrmVolunteer.user_id.is_(None),CrmVolunteer.merged_into_id.is_(None)))).all()
    existing=await db.scalar(select(CrmVolunteer).where(CrmVolunteer.foundation_id==user.foundation_id,CrmVolunteer.user_id==user_id,CrmVolunteer.merged_into_id.is_(None)))
    if existing and rows:raise ApiError(409,'crm_claim_conflict','В аккаунте уже есть карточка. Координатор поможет сохранить историю')
    for volunteer in rows:volunteer.user_id=user_id
    await db.flush()


async def contact_preference(db,foundation_id,*,user_id=None,application_id=None,volunteer_id=None):
    """P17 must recheck this before invitations/reminders; authentication is separate."""
    conditions=[]
    if user_id:conditions.append(CrmVolunteer.user_id==user_id)
    if application_id:conditions.append(CrmVolunteer.application_id==application_id)
    if volunteer_id:conditions.append(CrmVolunteer.id==volunteer_id)
    if not conditions:raise ApiError(422,'contact_subject_required','Не указан получатель')
    records=(await db.scalars(select(CrmVolunteer).where(CrmVolunteer.foundation_id==foundation_id,or_(*conditions)))).all()
    no_contact=any(record.no_contact for record in records)
    for record in records:
        if record.merged_into_id:
            target=await scoped_volunteer(db,foundation_id,record.merged_into_id)
            no_contact=no_contact or target.no_contact
    return dict(no_contact=no_contact)


async def save_own_availability(db,principal,command):
    volunteer=await own_volunteer(db,principal)
    if volunteer:
        volunteer=await scoped_volunteer(db,principal.foundation_id,volunteer.id,lock=True)
    check_version(volunteer.version if volunteer else 0,command.expected_version)
    if not volunteer:
        from app.modules.applications.service import own_application
        application=await own_application(db,principal)
        volunteer=await ensure_volunteer(db,principal.foundation_id,application.id)
        volunteer=await scoped_volunteer(db,principal.foundation_id,volunteer.id,lock=True)
    await write_availability(db,volunteer,principal,command);touch(volunteer);await db.flush()
    return await own_availability(db,principal)
