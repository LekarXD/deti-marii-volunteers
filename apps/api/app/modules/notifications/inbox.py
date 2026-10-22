"""The volunteer's bell: a derived inbox built from facts other modules already store.

Nothing is written when something happens; every read recomputes the list from assignments,
questions, reflection reviews, prize requests and gratitudes. Only the "seen up to" marker is stored
(notification_preferences.inbox_seen_at). Unread messages are not here: Сообщения has its own counter.
"""
from datetime import datetime,timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo
from sqlalchemy import and_,func,or_,select
from sqlalchemy.dialects.postgresql import insert
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.modules.activities.assignment_models import Assignment,AssignmentEvent
from app.modules.activities.calendar_models import EventOccurrence
from app.modules.followups.models import AssignmentQuestion,Reflection,ReflectionReview
from app.modules.profile.models import Gratitude,Prize,PrizeRequest
from .models import NotificationPreference

WINDOW=timedelta(days=60)
LIMIT=30
MONTHS=('января','февраля','марта','апреля','мая','июня','июля','августа','сентября','октября','ноября','декабря')


def when(event:EventOccurrence)->str:
    local=event.starts_at.astimezone(ZoneInfo(event.timezone))
    return f'{local.day} {MONTHS[local.month-1]} в {local:%H:%M}'


def snippet(value:str,limit:int=140)->str:
    value=' '.join(value.split())
    return value if len(value)<=limit else value[:limit-1].rstrip(' ,.;:')+'…'


def item(kind,key,title,text,at,href):
    return {'key':f'{kind}:{key}','kind':kind,'title':title,'text':text,'at':at,'href':href}


async def assignment_items(db,foundation_id,user_id,since,now):
    rows=(await db.execute(select(Assignment,EventOccurrence).join(EventOccurrence,EventOccurrence.id==Assignment.occurrence_id).where(
        Assignment.foundation_id==foundation_id,Assignment.user_id==user_id,
        or_(
            # A coordinator's invitation still waiting for the volunteer's answer.
            and_(Assignment.status=='invited',Assignment.origin=='invitation',EventOccurrence.status=='scheduled',EventOccurrence.ends_at>now),
            # Own sign-up or a reserve place the coordinator approved.
            and_(Assignment.status=='confirmed',Assignment.origin.in_(('self','reserve')),Assignment.confirmed_at>=since),
            # The fund cancelled the occurrence while the volunteer was on it.
            and_(Assignment.status=='cancelled',EventOccurrence.status=='cancelled',Assignment.updated_at>=since))))).all()
    latest={}
    if rows:
        events=(await db.scalars(select(AssignmentEvent).where(AssignmentEvent.assignment_id.in_([a.id for a,_ in rows]),AssignmentEvent.command.in_(('invite','cancelled'))).order_by(AssignmentEvent.version))).all()
        for event in events:latest[(event.assignment_id,event.command)]=event
    result=[]
    for row,event in rows:
        href=f'/my/assignments/{row.id}';text=f'{event.title}, {when(event)}'
        if row.status=='invited':
            invited=latest.get((row.id,'invite'))
            result.append(item('invitation',row.id,'Тебя приглашают',text,invited.created_at if invited else row.updated_at,href))
        elif row.status=='confirmed':
            result.append(item('place_confirmed',row.id,'Место за тобой',text,row.confirmed_at,href))
        else:
            cancelled=latest.get((row.id,'cancelled'))
            # The volunteer's own cancellation is not news for them.
            if cancelled and cancelled.actor_id!=str(user_id):result.append(item('occurrence_cancelled',row.id,'Занятие отменено',text,cancelled.created_at,href))
    return result


async def question_items(db,foundation_id,user_id,since):
    rows=(await db.execute(select(AssignmentQuestion,EventOccurrence.title).join(Assignment,Assignment.id==AssignmentQuestion.assignment_id).join(EventOccurrence,EventOccurrence.id==Assignment.occurrence_id).where(
        AssignmentQuestion.foundation_id==foundation_id,AssignmentQuestion.user_id==user_id,AssignmentQuestion.answered_at>=since,AssignmentQuestion.public_answer!=''))).all()
    # A closed (restricted) question keeps its answer on the preparation page only.
    return [item('question_answered',row.id,'Координатор ответил',title if row.restricted else snippet(row.public_answer),row.answered_at,f'/my/assignments/{row.assignment_id}/preparation') for row,title in rows]


async def review_items(db,foundation_id,user_id,since):
    latest=select(ReflectionReview.reflection_id.label('reflection_id'),func.max(ReflectionReview.revision).label('revision')).join(Reflection,Reflection.id==ReflectionReview.reflection_id).where(
        Reflection.foundation_id==foundation_id,Reflection.user_id==user_id).group_by(ReflectionReview.reflection_id).subquery()
    rows=(await db.execute(select(ReflectionReview,Reflection,EventOccurrence.title)
        .join(latest,and_(latest.c.reflection_id==ReflectionReview.reflection_id,latest.c.revision==ReflectionReview.revision))
        .join(Reflection,Reflection.id==ReflectionReview.reflection_id).join(Assignment,Assignment.id==Reflection.assignment_id).join(EventOccurrence,EventOccurrence.id==Assignment.occurrence_id)
        .where(ReflectionReview.created_at>=since,ReflectionReview.public_message!=''))).all()
    return [item('reflection_review',review.id,'Что дальше после занятия',title if reflection.restricted else snippet(review.public_message),review.created_at,f'/my/assignments/{reflection.assignment_id}/reflection') for review,reflection,title in rows]


async def prize_items(db,foundation_id,user_id,since):
    rows=(await db.execute(select(PrizeRequest,Prize.title).join(Prize,Prize.id==PrizeRequest.prize_id).where(
        PrizeRequest.foundation_id==foundation_id,PrizeRequest.user_id==user_id,PrizeRequest.state.in_(('issued','rejected')),PrizeRequest.decided_by.is_not(None),PrizeRequest.updated_at>=since))).all()
    result=[]
    for row,title in rows:
        if row.state=='issued':result.append(item('prize_issued',row.id,'Приз выдан',title,row.updated_at,'/hours?tab=points'))
        else:result.append(item('prize_rejected',row.id,'Заявка на приз отклонена',snippet(f'{title}: {row.reason}' if row.reason.strip() else title),row.updated_at,'/hours?tab=points'))
    return result


async def gratitude_items(db,foundation_id,user_id,since):
    rows=(await db.scalars(select(Gratitude).where(Gratitude.foundation_id==foundation_id,Gratitude.user_id==user_id,Gratitude.created_at>=since))).all()
    return [item('gratitude',row.id,'Спасибо от команды',snippet(row.text),row.created_at,'/hours') for row in rows]


def require_user(principal):
    if principal.user_id is None:raise ApiError(403,'verified_account_required','Подтвердите почту')


async def inbox(db,principal,now:datetime|None=None):
    require_user(principal)
    now=now or utcnow();since=now-WINDOW
    foundation_id,user_id=principal.foundation_id,principal.user_id
    pref=await db.scalar(select(NotificationPreference).where(NotificationPreference.foundation_id==foundation_id,NotificationPreference.user_id==user_id))
    if pref and not pref.in_app_enabled:return {'items':[],'unread':0}
    items=[*await assignment_items(db,foundation_id,user_id,since,now),*await question_items(db,foundation_id,user_id,since),*await review_items(db,foundation_id,user_id,since),
        *await prize_items(db,foundation_id,user_id,since),*await gratitude_items(db,foundation_id,user_id,since)]
    items=sorted((row for row in items if row['at'] and row['at']>=since),key=lambda row:(row['at'],row['key']),reverse=True)[:LIMIT]
    seen=pref.inbox_seen_at if pref else None
    return {'items':items,'unread':sum(1 for row in items if seen is None or row['at']>seen)}


async def mark_seen(db,principal,at:datetime):
    """Moves the marker forward only; a stale tab cannot bring old items back as unread."""
    require_user(principal)
    at=min(at,utcnow())
    statement=insert(NotificationPreference).values(id=uuid4(),foundation_id=principal.foundation_id,user_id=principal.user_id,no_contact=False,email_enabled=False,in_app_enabled=True,version=0,updated_at=utcnow(),inbox_seen_at=at)
    # Not a preference change: version and updated_at stay as they are, so the settings form never conflicts.
    statement=statement.on_conflict_do_update(index_elements=[NotificationPreference.foundation_id,NotificationPreference.user_id],set_={'inbox_seen_at':func.greatest(NotificationPreference.inbox_seen_at,statement.excluded.inbox_seen_at)})
    await db.execute(statement)
