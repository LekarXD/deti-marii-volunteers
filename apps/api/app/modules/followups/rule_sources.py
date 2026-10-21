"""Read canonical operational facts, never infer attendance from a missing ledger."""
from collections import defaultdict
from datetime import timedelta
from uuid import uuid5,NAMESPACE_URL
from sqlalchemy import select,func
from app.core.models import User
from app.modules.activities.assignment_models import Assignment,Attendance
from app.modules.activities.calendar_models import EventOccurrence,StaffingNeed
from app.modules.crm.models import CrmVolunteer,ContactEvent
from app.modules.learning.models import LearningAssignment,LessonProgress,LearningRelease
from app.modules.applications.models import Application,ApplicationReviewEvent

PERMISSIONS={'miss':'assignments.manage','quiet':'crm.read','learn':'learning.read','app':'candidates.read','shift':'schedule.read'}
LABELS={'miss':'Пропуски подряд','quiet':'Давно не было контакта','learn':'Обучение без прогресса','app':'Заявка без ответа','shift':'На роль нет подтверждённых волонтёров'}
LIMIT=5000

def observation(rule,entity,group,user,details,href):return dict(rule=rule,entity_id=entity,group_id=group,subject_user_id=user,title=LABELS[rule],details={**details,'href':href})
async def collect(db,foundation_id,rule,threshold,now):
    found=[];unknown=0
    if rule=='miss':
        rows=(await db.execute(select(Assignment,EventOccurrence,Attendance).join(EventOccurrence,EventOccurrence.id==Assignment.occurrence_id).outerjoin(Attendance,Attendance.assignment_id==Assignment.id).join(User,User.id==Assignment.user_id).where(Assignment.foundation_id==foundation_id,EventOccurrence.foundation_id==foundation_id,User.foundation_id==foundation_id,User.account_state=='active',Assignment.status=='confirmed',EventOccurrence.status!='cancelled',EventOccurrence.ends_at<=now).order_by(EventOccurrence.ends_at.desc(),Assignment.id).limit(LIMIT+1))).all()
        groups=defaultdict(list)
        for item,event,attendance in rows:groups[(item.user_id,item.group_id_snapshot)].append((item,event,attendance))
        for (user,group),values in groups.items():
            consecutive=[]
            for item,event,attendance in values:
                if attendance is None:unknown+=1;break
                if attendance.foundation_id!=foundation_id:unknown+=1;break
                if attendance.outcome!='absent':break
                consecutive.append((item,event,attendance))
            # An unknown more recent outcome cannot be bypassed with older absences.
            if len(consecutive)>=threshold:
                item,event,_=consecutive[0];entity=uuid5(NAMESPACE_URL,f'opora:miss:{foundation_id}:{user}:{group}')
                found.append(observation(rule,entity,group,user,dict(count=len(consecutive),threshold=threshold,assignments=[str(x[0].id) for x in consecutive],attendance_versions=[x[2].version for x in consecutive],last_event_at=event.ends_at.isoformat()),f'/fund/events/{event.id}'))
    elif rule=='quiet':
        rows=(await db.scalars(select(CrmVolunteer).where(CrmVolunteer.foundation_id==foundation_id,CrmVolunteer.merged_into_id.is_(None),CrmVolunteer.no_contact.is_(False),CrmVolunteer.relationship_state.in_(['active','contacted','awaiting_reply','ready'])).limit(LIMIT+1))).all()
        latest=dict((await db.execute(select(ContactEvent.volunteer_id,func.max(ContactEvent.occurred_at)).join(CrmVolunteer,CrmVolunteer.id==ContactEvent.volunteer_id).where(CrmVolunteer.foundation_id==foundation_id,ContactEvent.kind.in_(['phone','telegram','meeting','email','other']),ContactEvent.direction.in_(['incoming','outgoing','recorded']),ContactEvent.occurred_at<=now).group_by(ContactEvent.volunteer_id))).all())
        for person in rows:
            last=latest.get(person.id)
            if last is None:unknown+=1;continue
            days=(now-last).days
            if days>=threshold:found.append(observation(rule,person.id,None,person.user_id,dict(days=days,threshold=threshold,last_contact_at=last.isoformat()),f'/fund/volunteers/{person.id}'))
    elif rule=='learn':
        rows=(await db.execute(select(LearningAssignment,LearningRelease).join(LearningRelease,LearningRelease.id==LearningAssignment.release_id).join(User,User.id==LearningAssignment.user_id).where(LearningAssignment.foundation_id==foundation_id,LearningRelease.foundation_id==foundation_id,LearningAssignment.completed_at.is_(None),User.foundation_id==foundation_id,User.account_state=='active').limit(LIMIT+1))).all()
        latest=dict((await db.execute(select(LessonProgress.assignment_id,func.max(LessonProgress.completed_at)).join(LearningAssignment,LearningAssignment.id==LessonProgress.assignment_id).where(LearningAssignment.foundation_id==foundation_id,LessonProgress.completed_at<=now).group_by(LessonProgress.assignment_id))).all())
        for assignment,release in rows:
            if not release.lesson_version_ids:unknown+=1;continue
            last=latest.get(assignment.id) or assignment.assigned_at
            if last>now:unknown+=1;continue
            days=(now-last).days
            if days>=threshold:found.append(observation(rule,assignment.id,None,assignment.user_id,dict(days=days,threshold=threshold,last_progress_or_assignment_at=last.isoformat()),f'/fund/learning?track={release.track_id}'))
    elif rule=='app':
        rows=(await db.scalars(select(Application).where(Application.foundation_id==foundation_id,Application.submission_state=='submitted',Application.review_state.in_(['new','reviewing','paused'])).limit(LIMIT+1))).all()
        answered=set((await db.scalars(select(ApplicationReviewEvent.application_id).join(Application,Application.id==ApplicationReviewEvent.application_id).where(Application.foundation_id==foundation_id,func.length(func.trim(ApplicationReviewEvent.public_message))>0))).all())
        for application in rows:
            if application.id in answered:continue
            days=(now-application.submitted_at).days
            if days<0:unknown+=1;continue
            if days>=threshold:found.append(observation(rule,application.id,None,application.user_id,dict(days=days,threshold=threshold,submitted_at=application.submitted_at.isoformat(),application_version=application.version),f'/fund/candidates/{application.id}'))
    else:
        rows=(await db.execute(select(StaffingNeed,EventOccurrence).join(EventOccurrence,EventOccurrence.id==StaffingNeed.occurrence_id).where(StaffingNeed.foundation_id==foundation_id,EventOccurrence.foundation_id==foundation_id,EventOccurrence.status=='scheduled',EventOccurrence.starts_at>now,StaffingNeed.capacity_required>0).limit(LIMIT+1))).all()
        counts=dict((await db.execute(select(Assignment.staffing_need_id,func.count()).where(Assignment.foundation_id==foundation_id,Assignment.status=='confirmed').group_by(Assignment.staffing_need_id))).all())
        for need,event in rows:
            if now<event.starts_at<=now+timedelta(days=threshold) and counts.get(need.id,0)==0:found.append(observation(rule,need.id,event.group_id,None,dict(required=need.capacity_required,confirmed=0,threshold=threshold,starts_at=event.starts_at.isoformat(),need_version=need.version),f'/fund/events/{event.id}'))
    if len(rows)>LIMIT:return [],dict(state='unknown',reason='source_limit',unknown=0)
    return found,dict(state='evaluated' if rows else 'unknown',reason=None if rows else 'no_source_facts',unknown=unknown,matched=len(found))
