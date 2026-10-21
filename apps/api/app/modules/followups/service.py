from datetime import timedelta
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy import and_,or_,select
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.models import User,StaffMembership,PermissionGrant
from app.modules.activities.assignment_service import assignment,locked_assignment
from app.modules.activities.calendar_models import EventOccurrence
from app.modules.activities.models import VolunteerRoleVersion
from app.modules.crm.service import schedule_user_follow_up
from app.modules.crm.models import FollowUpTask
from app.modules.participants.models import ParticipantGroup
from .models import AssignmentQuestion,FirstVisitChecklist,Reflection,ReflectionReview,ReflectionReviewNote,SupportSignal,SupportSignalEvent
from .schemas import AssignmentPreparationView,AssignmentQuestionView,ChecklistItem,OwnReflectionView,PublicReflectionReview,StaffReflectionView,SupportSignalView


def denied():raise ApiError(403,'permission_denied','Недостаточно прав для этого обращения.')
def today():return utcnow().astimezone(ZoneInfo('Europe/Moscow')).date()
def check_version(row,expected):
    version=row.version if row else 0
    if version!=expected:raise ApiError(409,'version_conflict','Данные уже изменились. Обновите страницу.',current_version=version)
def has(principal,permission,group_id=None):return principal.has_permission(permission,'group',group_id)
def scope(principal,permission,model):
    if principal.has_permission(permission):return model.foundation_id==principal.foundation_id
    ids=[i for p,t,i in principal.grants if p==permission and t=='group' and i is not None] if principal.is_staff else []
    return and_(model.foundation_id==principal.foundation_id,model.group_id.in_(ids))
def privacy(principal,model):
    if principal.has_permission('signals.restricted'):return model.foundation_id==principal.foundation_id
    ids=[i for p,t,i in principal.grants if p=='signals.restricted' and t=='group' and i is not None] if principal.is_staff else []
    return or_(model.restricted.is_(False),model.group_id.in_(ids))
def any_permission(principal,permission):
    if not principal.is_staff or not any(p==permission for p,_,_ in principal.grants):denied()

async def own_assignment(db,principal,id,lock=False):
    if principal.user_id is None:raise ApiError(403,'user_required','Войдите в свой кабинет.')
    if lock:
        item,event,_=await locked_assignment(db,principal,id,True)
        return item,event
    item=await assignment(db,principal,id,own=True)
    return item,await db.get(EventOccurrence,item.occurrence_id)

async def staff_reflection(db,principal,id,permission='followups.read',lock=False):
    any_permission(principal,permission)
    query=select(Reflection).where(Reflection.id==id,Reflection.submitted_at.is_not(None),scope(principal,permission,Reflection),privacy(principal,Reflection))
    row=await db.scalar(query.with_for_update() if lock else query)
    if not row:raise ApiError(404,'reflection_not_found','Рефлексия не найдена или недоступна.')
    return row

async def staff_signal(db,principal,id,permission='followups.read',lock=False):
    any_permission(principal,permission)
    query=select(SupportSignal).where(SupportSignal.id==id,scope(principal,permission,SupportSignal),privacy(principal,SupportSignal))
    row=await db.scalar(query.with_for_update() if lock else query)
    if not row:raise ApiError(404,'signal_not_found','Сигнал не найден или недоступен.')
    return row

async def staff_options(db,foundation_id):
    return (await db.scalars(select(User).join(StaffMembership,StaffMembership.user_id==User.id).where(User.foundation_id==foundation_id,User.account_state=='active',StaffMembership.foundation_id==foundation_id,StaffMembership.revoked_at.is_(None)).order_by(User.display_name,User.id))).all()

async def owner_eligible(db,foundation_id,user_id,group_id,restricted):
    users=await staff_options(db,foundation_id)
    if not any(user.id==user_id for user in users):return False
    if not restricted:return True
    grant=await db.scalar(select(PermissionGrant.id).join(StaffMembership,StaffMembership.id==PermissionGrant.membership_id).where(
        StaffMembership.user_id==user_id,StaffMembership.foundation_id==foundation_id,StaffMembership.revoked_at.is_(None),PermissionGrant.revoked_at.is_(None),PermissionGrant.permission=='signals.restricted',or_(PermissionGrant.scope_type=='foundation',and_(PermissionGrant.scope_type=='group',PermissionGrant.scope_id==group_id))))
    return grant is not None

async def choose_owner(db,foundation_id,group_id,restricted,preferred=None):
    group=await db.get(ParticipantGroup,group_id) if group_id else None
    users=await staff_options(db,foundation_id)
    ids=list(dict.fromkeys([preferred,*([group.coordinator_id,group.leader_id] if group else []),*[user.id for user in users]]))
    for user_id in ids:
        if user_id and await owner_eligible(db,foundation_id,user_id,group_id,restricted):return user_id
    raise ApiError(503,'support_team_unconfigured','Для закрытого обращения пока не назначен специалист. Черновик сохранён; обратитесь к координатору.' if restricted else 'Пока не назначен ответственный сотрудник. Черновик сохранён; обратитесь к координатору.',retryable=True)

async def question_view(row):
    return AssignmentQuestionView(id=row.id,kind=row.kind,text=row.text,restricted=row.restricted,public_answer=row.public_answer,created_at=row.created_at,answered_at=row.answered_at,version=row.version)

async def preparation(db,principal,id):
    item,event=await own_assignment(db,principal,id)
    role=await db.get(VolunteerRoleVersion,UUID(item.conditions_snapshot['role_version_id']))
    checklist=await db.get(FirstVisitChecklist,id)
    checked=set(checklist.checked_keys if checklist else [])
    contacts=[]
    available=item.status=='confirmed' and event.status!='cancelled'
    if available and item.group_id_snapshot:
        group=await db.get(ParticipantGroup,item.group_id_snapshot)
        if group:
            for user_id,label in ((group.leader_id,'Ведущий'),(group.coordinator_id,'Координатор')):
                user=await db.get(User,user_id) if user_id else None
                if user and await owner_eligible(db,principal.foundation_id,user.id,group.id,False):contacts.append({'display_name':user.display_name,'role':label})
    questions=(await db.scalars(select(AssignmentQuestion).where(AssignmentQuestion.assignment_id==id,AssignmentQuestion.user_id==principal.user_id,AssignmentQuestion.foundation_id==principal.foundation_id).order_by(AssignmentQuestion.created_at,AssignmentQuestion.id))).all()
    actions=['confirm','decline'] if item.status=='invited' and event.status=='scheduled' else ['cancel'] if available else []
    items=[('group','Познакомиться с участниками группы',f'/me/group?assignment_id={id}' if available else None),('contact','Уточнить, кто встретит',None),('clothes','Подготовить удобную одежду',None)]
    return AssignmentPreparationView(assignment_id=id,assignment_version=item.version,status=item.status,title=event.title,starts_at=event.starts_at,ends_at=event.ends_at,timezone=event.timezone,location=event.location,role_title=role.snapshot['title'],tasks=role.snapshot.get('task',''),contacts=contacts,checklist_version=1,version=checklist.version if checklist else 0,checklist=[ChecklistItem(key=key,title=title,checked=key in checked,href=href) for key,title,href in items],questions=[await question_view(row) for row in questions],group_briefing_available=available,allowed_actions=actions)

async def save_checklist(db,principal,id,body):
    item,event=await own_assignment(db,principal,id,True)
    if item.status!='confirmed' or event.status=='cancelled':raise ApiError(409,'assignment_inactive','Список доступен по подтверждённому назначению.')
    if body.checklist_version!=1:raise ApiError(409,'checklist_version_changed','Памятка обновилась. Откройте её заново.')
    row=await db.get(FirstVisitChecklist,id);check_version(row,body.expected_version)
    if row is None:row=FirstVisitChecklist(assignment_id=id,foundation_id=principal.foundation_id,version=1);db.add(row)
    else:row.version+=1
    row.checked_keys=body.checked_keys;row.updated_at=utcnow();await db.flush()
    return await preparation(db,principal,id)

async def new_signal(db,principal,*,reflection=None,question=None,owner,priority='normal',schedule=True):
    source=reflection or question
    signal=SupportSignal(foundation_id=source.foundation_id,reflection_id=reflection.id if reflection else None,question_id=question.id if question else None,subject_user_id=source.user_id,group_id=source.group_id,restricted=source.restricted,priority=priority,assigned_user_id=owner)
    db.add(signal);await db.flush()
    if schedule:
        task=await schedule_user_follow_up(db,source.foundation_id,source.user_id,owner,today(),'support_signal',signal.id,signal.version,principal.actor_id,title='Связаться с волонтёром')
        signal.follow_up_task_id=task.id if task else None
    db.add(SupportSignalEvent(signal_id=signal.id,revision=signal.version,action='created',reason='Обращение волонтёра',author_id=principal.actor_id));await db.flush()
    return signal

async def create_question(db,principal,id,body):
    item,event=await own_assignment(db,principal,id,True)
    if not body.text.strip():raise ApiError(422,'question_empty','Напишите вопрос для координатора.')
    if item.status not in ('invited','confirmed') and body.kind!='alternate_date':raise ApiError(409,'assignment_inactive','Для отменённого выхода можно запросить другую дату.')
    group_id=item.group_id_snapshot if item.status=='confirmed' else event.group_id
    owner=await choose_owner(db,principal.foundation_id,group_id,body.restricted)
    row=AssignmentQuestion(foundation_id=principal.foundation_id,assignment_id=id,user_id=principal.user_id,group_id=group_id,kind=body.kind,text=body.text.strip(),restricted=body.restricted)
    db.add(row);await db.flush();await new_signal(db,principal,question=row,owner=owner)
    return await question_view(row)

async def public_review(db,row):
    user=await db.get(User,row.assigned_user_id)
    return PublicReflectionReview(id=row.id,revision=row.revision,decision=row.decision,public_message=row.public_message,next_date=row.next_date,assigned_staff_name=user.display_name if user else 'Сотрудник фонда',created_at=row.created_at)

async def reflection_view(db,principal,id,staff_row=None):
    if staff_row is None:item,event=await own_assignment(db,principal,id)
    else:
        from app.modules.activities.assignment_models import Assignment
        item=await db.get(Assignment,id);event=await db.get(EventOccurrence,item.occurrence_id)
    row=staff_row or await db.scalar(select(Reflection).where(Reflection.assignment_id==id,Reflection.foundation_id==principal.foundation_id,Reflection.user_id==principal.user_id))
    review=await db.scalar(select(ReflectionReview).where(ReflectionReview.reflection_id==row.id).order_by(ReflectionReview.revision.desc()).limit(1)) if row else None
    signal=await db.scalar(select(SupportSignal).where(SupportSignal.reflection_id==row.id)) if row else None
    values=dict(id=row.id if row else None,assignment_id=id,title=event.title,version=row.version if row else 0,mood=row.mood if row else None,text=row.text if row else '',unexpected=row.unexpected if row else '',help=row.help if row else 'later',help_text=row.help_text if row else '',continuation=row.continuation if row else 'discuss',restricted=row.restricted if row else False,submitted_at=row.submitted_at if row else None,can_submit=item.status=='confirmed' and event.status!='cancelled' and event.ends_at<=utcnow() and not(row and row.submitted_at),follow_up_registered=bool(signal and signal.follow_up_task_id),review=await public_review(db,review) if review else None)
    if staff_row:
        user=await db.get(User,row.user_id)
        return StaffReflectionView(**values,group_id=row.group_id,user_id=row.user_id,display_name=user.display_name,signal_id=signal.id if signal else None,can_review=has(principal,'followups.manage',row.group_id),private_notes_available=has(principal,'followups.private_notes',row.group_id))
    from .audio import readiness
    voice=await readiness(db,principal.foundation_id)
    return OwnReflectionView(**values,voice_available=bool(values['can_submit'] and voice['available']),voice_unavailable_reason='' if voice['available'] else voice['reason'])

async def save_reflection(db,principal,id,body):
    item,event=await own_assignment(db,principal,id,True)
    if item.status!='confirmed' or event.status=='cancelled' or event.ends_at>utcnow():raise ApiError(409,'reflection_not_available','Рефлексию можно оставить после подтверждённого занятия.')
    row=await db.scalar(select(Reflection).where(Reflection.assignment_id==id).with_for_update());check_version(row,body.expected_version)
    if row and row.submitted_at:raise ApiError(409,'reflection_submitted','Рефлексия уже передана координатору.')
    if row is None:row=Reflection(foundation_id=principal.foundation_id,assignment_id=id,user_id=principal.user_id,group_id=item.group_id_snapshot,version=1);db.add(row)
    else:row.version+=1
    for key,value in body.model_dump(exclude={'expected_version'}).items():setattr(row,key,value.strip() if isinstance(value,str) else value)
    row.updated_at=utcnow();await db.flush()
    return await reflection_view(db,principal,id)

async def submit_reflection(db,principal,id,body):
    item,event=await own_assignment(db,principal,id,True)
    row=await db.scalar(select(Reflection).where(Reflection.assignment_id==id).with_for_update());check_version(row,body.expected_version)
    if row is None or row.submitted_at:raise ApiError(409,'reflection_not_draft','Сначала сохраните черновик рефлексии.')
    if item.status!='confirmed' or event.status=='cancelled' or event.ends_at>utcnow():raise ApiError(409,'reflection_not_available','Рефлексия недоступна для этого назначения.')
    if not(row.mood or row.text or row.unexpected or row.help=='yes' or row.continuation!='discuss'):raise ApiError(422,'reflection_empty','Добавьте настроение, текст или пожелание.')
    needs_help=row.help=='yes' or row.restricted or row.mood in ('hard','awful') or row.continuation in ('other','pause','finish')
    if needs_help:
        owner=await choose_owner(db,principal.foundation_id,row.group_id,row.restricted)
        await new_signal(db,principal,reflection=row,owner=owner,priority='urgent' if row.restricted else 'high' if row.mood in ('hard','awful') else 'normal')
    row.submitted_at=utcnow();row.version+=1;row.updated_at=utcnow();await db.flush()
    return await reflection_view(db,principal,id)

async def signal_view(db,row,principal=None):
    user=await db.get(User,row.subject_user_id);owner=await db.get(User,row.assigned_user_id) if row.assigned_user_id else None
    source=await db.get(Reflection,row.reflection_id) if row.reflection_id else await db.get(AssignmentQuestion,row.question_id)
    history=(await db.scalars(select(SupportSignalEvent).where(SupportSignalEvent.signal_id==row.id).order_by(SupportSignalEvent.revision))).all()
    details='\n\n'.join(part for part in ([source.text,source.unexpected,source.help_text] if row.reflection_id else [source.text]) if part)
    return SupportSignalView(id=row.id,version=row.version,reflection_id=row.reflection_id,question_id=row.question_id,question_version=source.version if row.question_id else None,can_manage=bool(principal and has(principal,'followups.manage',row.group_id)),subject_user_id=row.subject_user_id,display_name=user.display_name,group_id=row.group_id,restricted=row.restricted,priority=row.priority,state=row.state,assigned_user_id=row.assigned_user_id,assigned_staff_name=owner.display_name if owner else None,follow_up_task_id=row.follow_up_task_id,summary='Закрытое обращение' if row.restricted else 'Нужна поддержка после занятия' if row.reflection_id else 'Вопрос перед занятием',details=details,public_answer=source.public_answer if row.question_id else None,history=history)

async def latest_reflection_for_user(db,foundation_id,user_id,principal=None):
    """CRM read seam: current staff scope, submitted text only, no internal notes."""
    if not principal or principal.foundation_id!=foundation_id or not principal.is_staff:return None
    if not any(p=='followups.read' for p,_,_ in principal.grants):return None
    row=await db.scalar(select(Reflection).where(Reflection.foundation_id==foundation_id,Reflection.user_id==user_id,Reflection.submitted_at.is_not(None),scope(principal,'followups.read',Reflection),privacy(principal,Reflection)).order_by(Reflection.submitted_at.desc(),Reflection.id.desc()).limit(1))
    if row is None:return None
    review=await db.scalar(select(ReflectionReview).where(ReflectionReview.reflection_id==row.id).order_by(ReflectionReview.revision.desc()).limit(1))
    return {'id':row.id,'assignment_id':row.assignment_id,'text':row.text,'unexpected':row.unexpected,'help':row.help,'continuation':row.continuation,'submitted_at':row.submitted_at,'can_review':has(principal,'followups.manage',row.group_id),'review':(await public_review(db,review)).model_dump(mode='json') if review else None}

async def finish_task(db,principal,signal,state,reason):
    if not signal.follow_up_task_id:return
    from app.modules.crm.service import update_task
    from app.modules.crm.schemas import TaskUpdateCommand
    task=await db.get(FollowUpTask,signal.follow_up_task_id)
    if task and task.state=='open':await update_task(db,principal,task.id,TaskUpdateCommand(expected_version=task.version,state=state,reason=reason[:4000]))

async def review_reflection(db,principal,id,body):
    row=await staff_reflection(db,principal,id,'followups.manage',True);check_version(row,body.expected_version)
    if not await owner_eligible(db,principal.foundation_id,body.assigned_user_id,row.group_id,row.restricted):raise ApiError(422,'invalid_support_owner','Выберите действующего сотрудника с доступом к обращению.')
    if body.internal_note.strip() and not has(principal,'followups.private_notes',row.group_id):denied()
    from app.modules.crm.service import ensure_user_volunteer,first_visit_outcome
    from app.modules.crm.schemas import FirstVisitOutcomeCommand
    volunteer=await ensure_user_volunteer(db,principal.foundation_id,row.user_id)
    outcomes={'next_date':'next_activity','other_role':'different_role','discussion':'preparation','pause':'pause','finish':'finish'}
    # CRM's broadly visible agreement must not become a second copy of a restricted case.
    note='Согласован следующий шаг.' if row.restricted else body.public_message.strip()
    await first_visit_outcome(db,principal,volunteer.id,FirstVisitOutcomeCommand(expected_version=volunteer.version,outcome=outcomes[body.decision],note=note,due_on=None))
    signal=await db.scalar(select(SupportSignal).where(SupportSignal.reflection_id==row.id).with_for_update())
    if signal is None:signal=await new_signal(db,principal,reflection=row,owner=body.assigned_user_id,schedule=False)
    signal.version+=1;signal.assigned_user_id=body.assigned_user_id;signal.updated_at=utcnow()
    signal.state='resolved' if body.decision=='finish' or body.decision=='pause' and body.next_date is None else 'in_progress'
    task=await schedule_user_follow_up(db,principal.foundation_id,row.user_id,body.assigned_user_id,body.next_date,'support_signal',signal.id,signal.version,principal.actor_id,title='Связаться с волонтёром')
    signal.follow_up_task_id=task.id if task else None
    row.version+=1;row.updated_at=utcnow()
    review=ReflectionReview(foundation_id=row.foundation_id,reflection_id=row.id,revision=row.version,decision=body.decision,public_message=body.public_message.strip(),next_date=body.next_date,assigned_user_id=body.assigned_user_id,follow_up_task_id=task.id if task else None,author_id=principal.user_id)
    db.add(review);await db.flush()
    if body.internal_note.strip():db.add(ReflectionReviewNote(review_id=review.id,text=body.internal_note.strip(),author_id=principal.user_id))
    db.add(SupportSignalEvent(signal_id=signal.id,revision=signal.version,action='reviewed',reason='Согласован следующий шаг',author_id=principal.actor_id));await db.flush()
    return await reflection_view(db,principal,row.assignment_id,staff_row=row)

async def signal_action(db,principal,id,body,action):
    row=await staff_signal(db,principal,id,'followups.manage',True);check_version(row,body.expected_version)
    reason=body.reason.strip()
    if not reason:raise ApiError(422,'reason_required','Укажите причину действия.')
    if action in ('assign','resolve','dismiss') and row.state not in ('open','in_progress') or action=='reopen' and row.state not in ('resolved','dismissed'):raise ApiError(409,'signal_state_conflict','Состояние сигнала уже изменилось.')
    owner=body.assigned_user_id or row.assigned_user_id
    if action in ('assign','reopen'):
        if owner is None or not await owner_eligible(db,principal.foundation_id,owner,row.group_id,row.restricted):raise ApiError(422,'invalid_support_owner','Выберите действующего сотрудника с доступом к обращению.')
        row.assigned_user_id=owner
    row.version+=1;row.updated_at=utcnow()
    if body.priority is not None:row.priority=body.priority
    row.state={'assign':'in_progress','resolve':'resolved','dismiss':'dismissed','reopen':'open'}[action]
    if action in ('assign','reopen'):
        task=await schedule_user_follow_up(db,row.foundation_id,row.subject_user_id,owner,today(),'support_signal',row.id,row.version,principal.actor_id,title='Связаться с волонтёром')
        row.follow_up_task_id=task.id if task else None
    else:await finish_task(db,principal,row,'done' if action=='resolve' else 'cancelled','Обращение разобрано' if action=='resolve' else 'Обращение закрыто с причиной')
    db.add(SupportSignalEvent(signal_id=row.id,revision=row.version,action=action,reason=reason,author_id=principal.actor_id));await db.flush()
    return await signal_view(db,row,principal)

async def staff_question(db,principal,id,lock=False):
    any_permission(principal,'followups.manage')
    query=select(AssignmentQuestion).where(AssignmentQuestion.id==id,scope(principal,'followups.manage',AssignmentQuestion),privacy(principal,AssignmentQuestion))
    row=await db.scalar(query.with_for_update() if lock else query)
    if row is None:raise ApiError(404,'question_not_found','Вопрос не найден или недоступен.')
    return row

async def answer_question(db,principal,id,body):
    row=await staff_question(db,principal,id,True);check_version(row,body.expected_version)
    if not body.public_answer.strip():raise ApiError(422,'answer_empty','Напишите ответ для волонтёра.')
    row.public_answer=body.public_answer.strip();row.answered_at=utcnow();row.answered_by=principal.user_id;row.version+=1
    signal=await db.scalar(select(SupportSignal).where(SupportSignal.question_id==row.id).with_for_update())
    if signal:
        signal.state='resolved';signal.version+=1;signal.updated_at=utcnow()
        await finish_task(db,principal,signal,'done','Ответ сохранён для волонтёра')
        db.add(SupportSignalEvent(signal_id=signal.id,revision=signal.version,action='answered',reason='Ответ сохранён для волонтёра',author_id=principal.actor_id))
    await db.flush();return await question_view(row)
