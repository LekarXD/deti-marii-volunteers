"""The single consent history; verified identity ownership is the only bridge."""
from sqlalchemy import select,or_,and_
from app.core.errors import ApiError
from app.core.models import User
from .models import Application,ConsentEvent

async def consent_events(db,foundation_id,*,user_id=None,application_id=None):
    clauses=[]
    if user_id is not None:
        user=await db.scalar(select(User).where(User.id==user_id,User.foundation_id==foundation_id))
        if user is None:raise ApiError(404,'user_not_found','Пользователь не найден')
        owned=select(Application.id).where(Application.foundation_id==foundation_id,Application.user_id==user_id)
        clauses=[ConsentEvent.subject_user_id==user_id,ConsentEvent.application_id.in_(owned)]
    if application_id is not None:
        query=select(Application.id).where(Application.id==application_id,Application.foundation_id==foundation_id)
        if user_id is not None:query=query.where(Application.user_id==user_id)
        if await db.scalar(query) is None:raise ApiError(404,'application_not_found','Анкета не найдена')
        clauses.append(ConsentEvent.application_id==application_id)
    if not clauses:return []
    return list((await db.scalars(select(ConsentEvent).where(or_(*clauses)).order_by(ConsentEvent.created_at,ConsentEvent.id))).all())

async def newsletter_consent(db,foundation_id,user_id)->bool:
    events=await consent_events(db,foundation_id,user_id=user_id)
    latest=next((event for event in reversed(events) if event.purpose=='news'),None)
    return bool(latest and latest.granted)
