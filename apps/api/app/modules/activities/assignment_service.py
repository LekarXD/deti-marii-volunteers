from datetime import datetime,timezone
from uuid import UUID
from zoneinfo import ZoneInfo
from sqlalchemy import delete,func,or_,select,update
from app.core.auth import Principal
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.models import ResourceReservation,User
from app.worker.queue import enqueue_outbox
from app.modules.profile.ledger import append_service_time,post_pending_attendance,subject_lock
from app.modules.profile.service import active_for_invitations
from app.modules.participants.access import AssignmentParticipantAccess
from app.modules.participants.models import GroupMembership
from .assignment_models import Assignment,AssignmentEvent,AssignmentParticipantSnapshot,AssignmentRequirementReview,Attendance,AttendanceEvent,OpportunityResponse,OpportunityResponseEvent,StaffingNeedReserve
from .assignment_schemas import AssignmentParticipationView,AssignmentReadinessItem,ParticipationResponseView
from .event_feed_schemas import ReserveView
from .calendar_models import EventOccurrence,StaffingNeed
from .calendar_service import occurrence
from .models import Opportunity,VolunteerRoleVersion
from .service import check_version,find_opportunity


def require_user(principal):
    if principal.user_id is None:raise ApiError(403,'user_required','Подтвердите контакт и войдите в свой кабинет.')


def staff(principal):return principal.has_permission('assignments.manage')


async def assignment(db,principal,id,lock=False,own=False):
    query=select(Assignment).where(Assignment.id==id,Assignment.foundation_id==principal.foundation_id)
    if own or not staff(principal):query=query.where(Assignment.user_id==principal.user_id)
    # Recheck committed state/version after waiting for the parent or row lock.
    item=await db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
    if item is None:raise ApiError(404,'assignment_not_found','Назначение не найдено.')
    return item


async def locked_assignment(db,principal,id,own=False):
    before=await assignment(db,principal,id,own=own)
    event=await occurrence(db,principal,before.occurrence_id,True)
    need=await db.scalar(select(StaffingNeed).where(StaffingNeed.id==before.staffing_need_id).with_for_update())
    item=await assignment(db,principal,id,True,own)
    return item,event,need


async def readiness(db,item):
    result=[]
    for req in item.conditions_snapshot.get('preparation_requirements',[]):
        review=await db.scalar(select(AssignmentRequirementReview).where(AssignmentRequirementReview.assignment_id==item.id,
            AssignmentRequirementReview.conditions_version==item.conditions_version,AssignmentRequirementReview.requirement_key==req['key']).order_by(AssignmentRequirementReview.created_at.desc(),AssignmentRequirementReview.id.desc()).limit(1))
        state='pending';evidence=None
        if review:state=review.state;evidence={'review_id':str(review.id),'reason':review.reason}
        else:
            try:
                from app.modules.learning.service import requirement_status
            except ModuleNotFoundError as exc:
                if not exc.name.startswith('app.modules.learning'):raise
            else:
                status=await requirement_status(db,item.foundation_id,item.user_id,req['key'])
                if status:state=status['status'];evidence=status['evidence']
        result.append(AssignmentReadinessItem(**req,state=state,evidence=evidence))
    return result


async def assignment_view(db,item,principal):
    event=await db.get(EventOccurrence,item.occurrence_id);user=await db.get(User,item.user_id)
    revision=await db.get(VolunteerRoleVersion,item.conditions_snapshot['role_version_id'])
    history=(await db.scalars(select(AssignmentEvent).where(AssignmentEvent.assignment_id==item.id).order_by(AssignmentEvent.version))).all()
    attendance=await db.scalar(select(Attendance).where(Attendance.assignment_id==item.id))
    latest_attendance_event=await db.scalar(select(AttendanceEvent).where(AttendanceEvent.attendance_id==attendance.id).order_by(AttendanceEvent.version.desc()).limit(1)) if attendance else None
    # Until confirmation the volunteer sees the need's current multiplier; after it, the copy fixed at confirm.
    multiplier=item.points_multiplier if item.confirmed_at else await db.scalar(select(StaffingNeed.points_multiplier).where(StaffingNeed.id==item.staffing_need_id))
    actions=[]
    if item.status=='invited' and event.status=='scheduled':
        if staff(principal):actions=['approve','review-requirement','cancel']
        if principal.user_id==item.user_id:actions+=['confirm','decline']
    if item.status=='confirmed':
        if attendance is None and principal.user_id==item.user_id:actions.append('cancel')
        if staff(principal):
            if attendance is None:actions+=['cancel']
            if event.ends_at<=utcnow():actions.append('correct-attendance' if attendance else 'attendance')
    return AssignmentParticipationView(id=item.id,version=item.version,user_id=item.user_id,display_name=user.display_name,
        occurrence_id=item.occurrence_id,staffing_need_id=item.staffing_need_id,title=event.title,role_title=revision.snapshot['title'],
        starts_at=event.starts_at,ends_at=event.ends_at,timezone=event.timezone,location=event.location,status=item.status,origin=item.origin or 'invitation',occurrence_status=event.status,approved_at=item.approved_at,
        confirmed_at=item.confirmed_at,conditions_version=item.conditions_version,points_multiplier=multiplier,approval_required=item.origin in ('self','reserve'),readiness=await readiness(db,item),allowed_actions=list(dict.fromkeys(actions)),
        history=[{'command':h.command,'status':h.status,'reason':h.reason,'at':h.created_at.isoformat()} for h in history],
        attendance={'id':str(attendance.id),'version':attendance.version,'outcome':attendance.outcome,'minutes':attendance.minutes,'ledger_state':latest_attendance_event.ledger_state if latest_attendance_event else 'pending'} if attendance else None)


async def assignment_event(db,principal,item,command,reason=''):
    await db.flush()
    db.add(AssignmentEvent(assignment_id=item.id,version=item.version,command=command,status=item.status,reason=reason,actor_id=principal.actor_id))
    event_name={'invite':'invited','approve':'approved','confirm':'confirmed','declined':'declined','cancelled':'cancelled','reserve_offer':'offered'}.get(command)
    if event_name:enqueue_outbox(db,principal.foundation_id,'internal',{'event':f'assignment.{event_name}','assignment_id':str(item.id),'assignment_version':item.version})


def conditions_snapshot(need):
    return {'role_version_id':str(need.role_version_id),'preparation_requirements':need.preparation_requirements,'approval_policy':need.approval_policy}


async def confirmed_count(db,need_id):
    return await db.scalar(select(func.count()).select_from(Assignment).where(Assignment.staffing_need_id==need_id,Assignment.status=='confirmed'))


async def sign_up_gate(db,foundation_id,user_id):
    """None when the volunteer may sign up alone; otherwise (code, message) for the locked state."""
    if not await active_for_invitations(db,foundation_id,user_id):
        return 'volunteer_paused','Участие сейчас на паузе. Возобновите его в профиле, чтобы записаться.'
    # Volunteers who already took part are trusted; newcomers sign up after the coordinator meeting.
    if await db.scalar(select(Assignment.id).where(Assignment.foundation_id==foundation_id,Assignment.user_id==user_id,Assignment.confirmed_at.is_not(None)).limit(1)):return None
    from app.modules.interviews.models import InterviewBooking
    if await db.scalar(select(InterviewBooking.id).where(InterviewBooking.foundation_id==foundation_id,InterviewBooking.user_id==user_id,InterviewBooking.status=='completed').limit(1)):return None
    return 'meeting_required','Записаться можно после встречи с координатором.'


async def require_sign_up(db,principal):
    require_user(principal)
    gate=await sign_up_gate(db,principal.foundation_id,principal.user_id)
    if gate:raise ApiError(409,gate[0],gate[1])


async def invite(db,principal,need_id,body):
    before=await db.get(StaffingNeed,need_id)
    if before is None or before.foundation_id!=principal.foundation_id:raise ApiError(404,'need_not_found','Потребность не найдена.')
    event=await occurrence(db,principal,before.occurrence_id,True)
    need=await db.scalar(select(StaffingNeed).where(StaffingNeed.id==need_id).with_for_update().execution_options(populate_existing=True))
    check_version(need,body.expected_version)
    if event.status!='scheduled' or event.ends_at<=utcnow() or need.capacity_required==0:raise ApiError(409,'event_not_open','Набор на занятие закрыт.')
    user=await db.get(User,body.user_id)
    if user is None or user.foundation_id!=principal.foundation_id or user.account_state!='active':raise ApiError(422,'invalid_volunteer','Волонтёр недоступен.')
    if not await active_for_invitations(db,principal.foundation_id,user.id):raise ApiError(409,'volunteer_paused','Волонтёр сейчас на паузе. Сначала согласуйте возобновление участия.')
    item=await db.scalar(select(Assignment).where(Assignment.occurrence_id==event.id,Assignment.user_id==user.id).with_for_update())
    if item:
        if body.expected_assignment_version is None:raise ApiError(409,'already_invited','Назначение уже существует.',current_version=item.version)
        check_version(item,body.expected_assignment_version)
        if item.status=='confirmed':raise ApiError(409,'already_confirmed','Сначала отмените подтверждённое назначение.')
        item.status='invited';item.version+=1;item.approved_at=None;item.confirmed_at=None
    else:
        item=Assignment(foundation_id=principal.foundation_id,user_id=user.id,occurrence_id=event.id,staffing_need_id=need.id)
        db.add(item)
    item.staffing_need_id=need.id;item.conditions_version=need.version;item.updated_at=utcnow();item.origin='invitation'
    item.conditions_snapshot=conditions_snapshot(need)
    await assignment_event(db,principal,item,'invite')
    return await assignment_view(db,item,principal)


async def approve(db,principal,id,body):
    item,event,need=await locked_assignment(db,principal,id);check_version(item,body.expected_version)
    if item.status!='invited' or event.status!='scheduled':raise ApiError(409,'assignment_state_conflict','Назначение уже изменилось.')
    if item.conditions_version!=need.version:raise ApiError(409,'conditions_changed','Условия изменились. Пригласите волонтёра с обновлёнными условиями.')
    item.approved_at=utcnow();item.version+=1;item.updated_at=utcnow()
    await assignment_event(db,principal,item,'approve',body.reason)
    if item.origin in ('self','reserve') and event.starts_at>utcnow():
        # The volunteer already asked for the place; approval completes it unless a check fails.
        reason='Волонтёр записался сам, координатор согласовал участие.' if item.origin=='self' else 'Место из резерва, координатор согласовал участие.'
        try:await confirm_locked(db,principal,item,event,need,reason)
        except ApiError:pass
    return await assignment_view(db,item,principal)


async def overlapping_commitment(db,item,event):
    return await db.scalar(select(ResourceReservation.id).where(ResourceReservation.foundation_id==item.foundation_id,ResourceReservation.owner_key==f'user:{item.user_id}',
        ResourceReservation.active.is_(True),ResourceReservation.starts_at<event.ends_at,ResourceReservation.busy_until>event.starts_at,
        or_(ResourceReservation.source_type!='activity',ResourceReservation.source_id!=item.id)).limit(1))


async def confirm_locked(db,principal,item,event,need,reason=''):
    """Every check runs before the first write, so a caller may keep the transaction after an ApiError."""
    if not await active_for_invitations(db,item.foundation_id,item.user_id):raise ApiError(409,'volunteer_paused','Участие сейчас на паузе. Сначала возобновите его в профиле.')
    if item.conditions_version!=need.version:raise ApiError(409,'conditions_changed','Условия изменились. Координатор должен обновить приглашение.')
    # A volunteer's own sign-up and a reserve place wait for the coordinator; an invitation is the coordinator's offer already.
    if item.origin in ('self','reserve') and item.approved_at is None:raise ApiError(409,'approval_required','Сначала участие должен согласовать координатор.')
    pending=[r for r in await readiness(db,item) if r.level=='mandatory' and r.state=='pending']
    if pending:raise ApiError(409,'preparation_pending','Сначала выполните обязательную подготовку.',field_errors={r.key:r.title for r in pending})
    if await confirmed_count(db,need.id)>=need.capacity_required:raise ApiError(409,'capacity_full','Все места уже подтверждены.')
    if await overlapping_commitment(db,item,event):raise ApiError(409,'participation_overlap','В это время уже есть подтверждённое занятие или встреча.')
    reservation=await db.scalar(select(ResourceReservation).where(ResourceReservation.source_type=='activity',ResourceReservation.source_id==item.id).with_for_update())
    if reservation is None:
        reservation=ResourceReservation(foundation_id=principal.foundation_id,user_id=item.user_id,owner_key=f'user:{item.user_id}',source_type='activity',source_id=item.id,starts_at=event.starts_at,busy_until=event.ends_at,active=True);db.add(reservation)
    else:reservation.starts_at=event.starts_at;reservation.busy_until=event.ends_at;reservation.active=True
    item.status='confirmed';item.confirmed_at=utcnow();item.version+=1;item.updated_at=utcnow();item.group_id_snapshot=event.group_id;item.points_multiplier=need.points_multiplier
    await db.execute(delete(AssignmentParticipantSnapshot).where(AssignmentParticipantSnapshot.assignment_id==item.id))
    if event.group_id:
        event_date=event.starts_at.astimezone(ZoneInfo(event.timezone)).date()
        ids=(await db.scalars(select(GroupMembership.participant_id).where(GroupMembership.foundation_id==principal.foundation_id,GroupMembership.group_id==event.group_id,
            GroupMembership.valid_from<=event_date,or_(GroupMembership.valid_until.is_(None),GroupMembership.valid_until>event_date)))).all()
        for participant_id in ids:db.add(AssignmentParticipantSnapshot(assignment_id=item.id,participant_id=participant_id,foundation_id=principal.foundation_id))
    await close_reserve(db,need.id,item.user_id)
    await assignment_event(db,principal,item,'confirm',reason)


async def confirm(db,principal,id,body):
    require_user(principal)
    item,event,need=await locked_assignment(db,principal,id,True);check_version(item,body.expected_version)
    if item.status!='invited' or event.status!='scheduled' or event.ends_at<=utcnow():raise ApiError(409,'assignment_state_conflict','Подтверждение больше недоступно.')
    await confirm_locked(db,principal,item,event,need)
    return await assignment_view(db,item,principal)


async def open_need(db,principal,need_id,expected_version):
    before=await db.get(StaffingNeed,need_id)
    if before is None or before.foundation_id!=principal.foundation_id:raise ApiError(404,'need_not_found','Роль на занятии не найдена.')
    event=await occurrence(db,principal,before.occurrence_id,True)
    need=await db.scalar(select(StaffingNeed).where(StaffingNeed.id==need_id).with_for_update().execution_options(populate_existing=True))
    check_version(need,expected_version)
    if event.status!='scheduled' or event.starts_at<=utcnow() or need.capacity_required==0:raise ApiError(409,'event_not_open','Запись на это занятие закрыта.')
    return event,need


async def sign_up(db,principal,need_id,body):
    """Volunteer's own sign-up is a request: the coordinator's approval confirms it (approve)."""
    await require_sign_up(db,principal)
    event,need=await open_need(db,principal,need_id,body.expected_version)
    item=await db.scalar(select(Assignment).where(Assignment.occurrence_id==event.id,Assignment.user_id==principal.user_id).with_for_update())
    if item and item.status in ('invited','confirmed'):raise ApiError(409,'already_signed_up','Вы уже записаны на это занятие или ждёте ответа.',current_version=item.version)
    if await confirmed_count(db,need.id)>=need.capacity_required:raise ApiError(409,'capacity_full','Все места уже заняты. Можно встать в резерв.')
    if item is None:
        item=Assignment(foundation_id=principal.foundation_id,user_id=principal.user_id,occurrence_id=event.id,staffing_need_id=need.id);db.add(item)
    else:item.version+=1;item.approved_at=None;item.confirmed_at=None
    item.status='invited';item.origin='self';item.staffing_need_id=need.id;item.conditions_version=need.version;item.updated_at=utcnow()
    item.conditions_snapshot=conditions_snapshot(need)
    await assignment_event(db,principal,item,'sign_up',body.message)
    await close_reserve(db,need.id,item.user_id)
    return await assignment_view(db,item,principal)


async def close_reserve(db,need_id,user_id):
    await db.execute(update(StaffingNeedReserve).where(StaffingNeedReserve.staffing_need_id==need_id,StaffingNeedReserve.user_id==user_id,StaffingNeedReserve.state!='closed').values(
        state='closed',version=StaffingNeedReserve.version+1,updated_at=utcnow()))


async def reserve_view(db,row):
    ahead=0
    if row.state=='waiting':
        ahead=await db.scalar(select(func.count()).select_from(StaffingNeedReserve).where(StaffingNeedReserve.staffing_need_id==row.staffing_need_id,StaffingNeedReserve.state=='waiting',
            or_(StaffingNeedReserve.queued_at<row.queued_at,(StaffingNeedReserve.queued_at==row.queued_at)&(StaffingNeedReserve.id<row.id))))
    return ReserveView(id=row.id,version=row.version,occurrence_id=row.occurrence_id,staffing_need_id=row.staffing_need_id,state=row.state,
        position=ahead+1 if row.state=='waiting' else None,offered_assignment_id=row.offered_assignment_id,queued_at=row.queued_at,
        allowed_actions=['leave'] if row.state in ('waiting','offered') else [])


async def join_reserve(db,principal,need_id,body):
    await require_sign_up(db,principal)
    event,need=await open_need(db,principal,need_id,body.expected_version)
    item=await db.scalar(select(Assignment).where(Assignment.occurrence_id==event.id,Assignment.user_id==principal.user_id))
    if item and item.status in ('invited','confirmed'):raise ApiError(409,'already_signed_up','Вы уже записаны на это занятие или ждёте ответа.')
    if await confirmed_count(db,need.id)<need.capacity_required:raise ApiError(409,'places_available','Места ещё есть — можно записаться.')
    row=await db.scalar(select(StaffingNeedReserve).where(StaffingNeedReserve.staffing_need_id==need.id,StaffingNeedReserve.user_id==principal.user_id).with_for_update())
    if row and row.state!='closed':raise ApiError(409,'already_in_reserve','Вы уже в резерве на эту роль.',current_version=row.version)
    if row is None:
        row=StaffingNeedReserve(foundation_id=principal.foundation_id,occurrence_id=event.id,staffing_need_id=need.id,user_id=principal.user_id,state='waiting');db.add(row)
    else:row.state='waiting';row.version+=1;row.queued_at=utcnow();row.updated_at=utcnow();row.offered_assignment_id=None
    await db.flush()
    return await reserve_view(db,row)


async def leave_reserve(db,principal,reserve_id,body):
    require_user(principal)
    row=await db.scalar(select(StaffingNeedReserve).where(StaffingNeedReserve.id==reserve_id,StaffingNeedReserve.foundation_id==principal.foundation_id,StaffingNeedReserve.user_id==principal.user_id).with_for_update())
    if row is None:raise ApiError(404,'reserve_not_found','Запись в резерве не найдена.')
    check_version(row,body.expected_version)
    if row.state=='closed':raise ApiError(409,'reserve_state_conflict','Вы уже не в резерве.')
    row.state='closed';row.version+=1;row.updated_at=utcnow()
    await db.flush()
    return await reserve_view(db,row)


async def offer_reserved_places(db,principal,event,need):
    """A freed place becomes an invitation for the next volunteer in the reserve queue, in queue order."""
    if event.status!='scheduled' or event.starts_at<=utcnow():return
    outstanding=await db.scalar(select(func.count()).select_from(Assignment).where(Assignment.staffing_need_id==need.id,Assignment.status=='invited',Assignment.origin=='reserve'))
    free=need.capacity_required-await confirmed_count(db,need.id)-outstanding
    if free<=0:return
    rows=(await db.scalars(select(StaffingNeedReserve).where(StaffingNeedReserve.staffing_need_id==need.id,StaffingNeedReserve.state=='waiting')
        .order_by(StaffingNeedReserve.queued_at,StaffingNeedReserve.id).with_for_update())).all()
    for row in rows:
        if free<=0:break
        if not await active_for_invitations(db,row.foundation_id,row.user_id):continue
        item=await db.scalar(select(Assignment).where(Assignment.occurrence_id==event.id,Assignment.user_id==row.user_id).with_for_update())
        if item and item.status in ('invited','confirmed'):
            row.state='closed';row.version+=1;row.updated_at=utcnow();continue
        if item is None:
            item=Assignment(foundation_id=row.foundation_id,user_id=row.user_id,occurrence_id=event.id,staffing_need_id=need.id);db.add(item)
        else:item.version+=1;item.approved_at=None;item.confirmed_at=None
        item.status='invited';item.origin='reserve';item.staffing_need_id=need.id;item.conditions_version=need.version;item.updated_at=utcnow()
        item.conditions_snapshot=conditions_snapshot(need)
        await assignment_event(db,principal,item,'reserve_offer','Освободилось место из резерва. Участие подтвердит координатор.')
        row.state='offered';row.offered_assignment_id=item.id;row.version+=1;row.updated_at=utcnow()
        free-=1


async def cancel(db,principal,id,body,status='cancelled',own=False):
    item,event,need=await locked_assignment(db,principal,id,own);check_version(item,body.expected_version)
    if await db.scalar(select(Attendance.id).where(Attendance.assignment_id==item.id)):
        raise ApiError(409,'attendance_already_recorded','Факт уже отмечен. При необходимости исправьте отметку участия.')
    if item.status not in ('invited','confirmed'):raise ApiError(409,'assignment_state_conflict','Назначение уже изменилось.')
    if status=='declined' and item.status!='invited':raise ApiError(409,'already_confirmed','Для подтверждённого участия используйте отмену.')
    item.status=status;item.version+=1;item.updated_at=utcnow()
    await db.execute(update(ResourceReservation).where(ResourceReservation.source_type=='activity',ResourceReservation.source_id==item.id).values(active=False))
    if item.origin=='reserve':await close_reserve(db,need.id,item.user_id)
    await assignment_event(db,principal,item,status,getattr(body,'reason',''))
    await offer_reserved_places(db,principal,event,need)
    return await assignment_view(db,item,principal)


async def review_requirement(db,principal,id,body):
    item,event,need=await locked_assignment(db,principal,id);check_version(item,body.expected_version)
    if item.status!='invited':raise ApiError(409,'assignment_state_conflict','Подготовка проверяется до подтверждения участия.')
    if not any(r['key']==body.requirement_key for r in item.conditions_snapshot['preparation_requirements']):raise ApiError(422,'unknown_requirement','Такого условия нет в приглашении.')
    db.add(AssignmentRequirementReview(assignment_id=id,requirement_key=body.requirement_key,conditions_version=item.conditions_version,state=body.state,reason=body.reason,author_id=principal.actor_id))
    item.version+=1;item.updated_at=utcnow()
    await assignment_event(db,principal,item,'review_requirement',body.reason)
    return await assignment_view(db,item,principal)


async def record_attendance(db,principal,id,body,correction=False):
    identity=await assignment(db,principal,id)
    await subject_lock(db,principal.foundation_id,identity.user_id)
    await post_pending_attendance(db,principal,identity.user_id)
    item,event,need=await locked_assignment(db,principal,id);check_version(item,body.expected_version)
    if item.status!='confirmed' or event.status=='cancelled':raise ApiError(409,'attendance_not_available','Факт можно отметить только по подтверждённому участию.')
    if event.ends_at>utcnow():raise ApiError(409,'attendance_not_finished','Нельзя отмечать факт участия до окончания занятия.')
    attendance=await db.scalar(select(Attendance).where(Attendance.assignment_id==id).with_for_update())
    if attendance is not None and not correction:raise ApiError(409,'attendance_already_recorded','Факт уже отмечен. Используйте коррекцию.')
    if attendance is None and correction:raise ApiError(409,'attendance_not_recorded','Сначала отметьте факт участия.')
    old=attendance.minutes if attendance else 0
    if attendance is None:attendance=Attendance(foundation_id=principal.foundation_id,assignment_id=id,outcome=body.outcome,minutes=body.minutes);db.add(attendance)
    else:attendance.outcome=body.outcome;attendance.minutes=body.minutes;attendance.version+=1;attendance.updated_at=utcnow()
    item.version+=1;item.updated_at=utcnow();await db.flush()
    event_row=AttendanceEvent(foundation_id=principal.foundation_id,attendance_id=attendance.id,assignment_id=id,user_id=item.user_id,version=attendance.version,
        old_minutes=old,new_minutes=body.minutes,reason=body.reason,actor_id=principal.actor_id)
    db.add(event_row)
    await db.flush()
    await append_service_time(db,principal,item.user_id,item.id,event_row.id)
    await assignment_event(db,principal,item,'correct_attendance' if correction else 'record_attendance',body.reason)
    return await assignment_view(db,item,principal)


async def response_view(db,row,principal):
    opportunity=await db.get(Opportunity,row.opportunity_id);user=await db.get(User,row.user_id)
    history=(await db.scalars(select(OpportunityResponseEvent).where(OpportunityResponseEvent.response_id==row.id).order_by(OpportunityResponseEvent.version))).all()
    return ParticipationResponseView(id=row.id,opportunity_id=row.opportunity_id,opportunity_title=opportunity.title,user_id=row.user_id,display_name=user.display_name,
        state=row.state,decision_reason=row.decision_reason,version=row.version,
        allowed_actions=(['approve','decline','request-preparation'] if staff(principal) and row.state in ('submitted','under_review','preparation_requested') else [])+(['withdraw'] if principal.user_id==row.user_id and row.state not in ('withdrawn','declined') else ['resubmit'] if principal.user_id==row.user_id else []),
        history=[{'state':h.state,'reason':h.reason,'at':h.created_at.isoformat()} for h in history])


async def respond(db,principal,opportunity_id,body):
    require_user(principal);await find_opportunity(db,principal,opportunity_id)
    row=await db.scalar(select(OpportunityResponse).where(OpportunityResponse.opportunity_id==opportunity_id,OpportunityResponse.user_id==principal.user_id).with_for_update())
    if row:raise ApiError(409,'response_exists','Отклик уже существует. Посмотрите его состояние.',current_version=row.version)
    row=OpportunityResponse(foundation_id=principal.foundation_id,opportunity_id=opportunity_id,user_id=principal.user_id);db.add(row);await db.flush()
    db.add(OpportunityResponseEvent(response_id=row.id,version=1,state='submitted',reason=body.message,actor_id=principal.actor_id))
    return await response_view(db,row,principal)


async def decide_response(db,principal,id,body,state,own=False):
    query=select(OpportunityResponse).where(OpportunityResponse.id==id,OpportunityResponse.foundation_id==principal.foundation_id)
    if own:query=query.where(OpportunityResponse.user_id==principal.user_id)
    row=await db.scalar(query.with_for_update())
    if row is None:raise ApiError(404,'response_not_found','Отклик не найден.')
    check_version(row,body.expected_version)
    if state=='submitted':
        if row.state not in ('withdrawn','declined'):raise ApiError(409,'response_state_conflict','Отклик уже на рассмотрении.')
        await find_opportunity(db,principal,row.opportunity_id)
    elif state=='withdrawn' and row.state in ('withdrawn','declined') or state!='withdrawn' and row.state not in ('submitted','under_review','preparation_requested'):raise ApiError(409,'response_state_conflict','Состояние отклика уже изменилось.')
    row.state=state;row.version+=1;row.updated_at=utcnow();row.decision_reason=getattr(body,'reason','')
    db.add(OpportunityResponseEvent(response_id=id,version=row.version,state=state,reason=row.decision_reason,actor_id=principal.actor_id))
    return await response_view(db,row,principal)


class ActivityAssignmentAccess:
    async def participants(self,db,principal,assignment_id):
        require_user(principal)
        item=await assignment(db,principal,assignment_id,own=True)
        event=await db.get(EventOccurrence,item.occurrence_id)
        if item.status!='confirmed' or event.status=='cancelled':raise ApiError(403,'assignment_inactive','Памятка доступна по действующему подтверждённому назначению.')
        ids=(await db.scalars(select(AssignmentParticipantSnapshot.participant_id).where(AssignmentParticipantSnapshot.assignment_id==item.id))).all()
        return AssignmentParticipantAccess(assignment_id=item.id,group_ids=(item.group_id_snapshot,) if item.group_id_snapshot else (),participant_ids=tuple(ids))


async def cancel_occurrence_assignments(db,principal,occurrence_id):
    items=(await db.scalars(select(Assignment).where(Assignment.occurrence_id==occurrence_id,Assignment.status.in_(['invited','confirmed'])).order_by(Assignment.id).with_for_update())).all()
    if items and await db.scalar(select(Attendance.id).where(Attendance.assignment_id.in_([item.id for item in items])).limit(1)):
        raise ApiError(409,'attendance_already_recorded','По занятию уже есть факты участия. Исправьте отметки, сохранив историю.')
    for item in items:
        item.status='cancelled';item.version+=1;item.updated_at=utcnow()
        await db.execute(update(ResourceReservation).where(ResourceReservation.source_type=='activity',ResourceReservation.source_id==item.id).values(active=False))
        await assignment_event(db,principal,item,'cancelled','Занятие отменено координатором.')


async def ensure_occurrence_change_safe(db,occurrence_id,fields,current):
    if any(name in fields and fields[name]!=getattr(current,name) for name in ('starts_at','ends_at','location','group_id')):
        confirmed=await db.scalar(select(func.count()).select_from(Assignment).where(Assignment.occurrence_id==occurrence_id,Assignment.status=='confirmed'))
        if confirmed:raise ApiError(409,'reconfirmation_required','Есть подтверждённые назначения. Сначала отмените их и пересогласуйте новые условия.')
