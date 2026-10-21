"""Verified contact replacement in the existing identity challenge store."""
import secrets
from datetime import timedelta
from fastapi import APIRouter,Depends,Response
from sqlalchemy import select,text,update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal,authz_guard,issue_session,session_view
from app.core.audit import audit
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.crypto import digest
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.models import AuthChallenge,ContactChannel,Session,StaffMembership
from app.core.rate_limit import rate_limit
from app.worker.queue import enqueue_outbox
from .schemas import ContactChangeRequestCommand,ContactChangeVerifyCommand,ContactChangeChallengeView,AuthSessionView
router=APIRouter()

async def require_recent_identity(db,principal):
    await authz_guard(db,principal)
    if principal.user_id is None:raise ApiError(403,'verified_account_required','Подтвердите почту')
    session=await db.get(Session,principal.session_id)
    staff=await db.scalar(select(StaffMembership.id).where(StaffMembership.user_id==principal.user_id,StaffMembership.foundation_id==principal.foundation_id,StaffMembership.revoked_at.is_(None)))
    if session.created_at<utcnow()-timedelta(minutes=10) or (staff and (not session.mfa_at or session.mfa_at<utcnow()-timedelta(minutes=10))):
        raise ApiError(403,'step_up_required','Войдите снова перед сменой почты')
    return session

@router.post('/contact-change',operation_id='auth_contact_change_request',response_model=ContactChangeChallengeView)
async def request_change(body:ContactChangeRequestCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    await require_recent_identity(db,principal)
    email=body.email.strip().lower()
    if '@' not in email or any(c.isspace() for c in email):raise ApiError(422,'invalid_contact','Укажите корректную почту')
    await rate_limit(db,principal.actor_id,'contact_change',limit=5)
    await rate_limit(db,email,'challenge_contact')
    raw=secrets.token_urlsafe(32)
    row=AuthChallenge(foundation_id=principal.foundation_id,bound_user_id=principal.user_id,bound_session_id=principal.session_id,normalized_contact=email,token_hash=digest(raw),purpose='contact_change',expires_at=utcnow()+timedelta(minutes=15))
    db.add(row)
    await db.flush()
    enqueue_outbox(db,principal.foundation_id,'email',{'purpose':'contact_change','to':email,'challenge_id':str(row.id),'token':raw})
    audit(db,principal,'auth.contact_change.request','auth_challenge',row.id)
    await db.commit()
    return {'challenge_id':row.id,'expires_at':row.expires_at,'delivery_state':'dev_inbox' if get_settings().dev_inbox else 'pending'}

@router.post('/contact-change/verify',operation_id='auth_contact_change_verify',response_model=AuthSessionView)
async def verify_change(body:ContactChangeVerifyCommand,response:Response,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    session=await require_recent_identity(db,principal)
    await rate_limit(db,principal.actor_id,'contact_change_verify',limit=20)
    row=await db.scalar(select(AuthChallenge).where(AuthChallenge.id==body.challenge_id).with_for_update())
    if not row or row.foundation_id!=principal.foundation_id or row.purpose!='contact_change' or row.bound_user_id!=principal.user_id or row.bound_session_id!=principal.session_id or row.consumed_at or row.expires_at<=utcnow() or row.attempts>=5:
        await db.commit()
        raise ApiError(400,'challenge_invalid','Код недействителен или истёк')
    row.attempts+=1
    if not secrets.compare_digest(row.token_hash,digest(body.token)):
        await db.commit()
        raise ApiError(400,'challenge_invalid','Код недействителен или истёк')
    current=await db.scalar(select(ContactChannel).where(ContactChannel.user_id==principal.user_id,ContactChannel.type=='email'))
    # Match login's normalized-contact lock; sorted old/new contacts also protect reciprocal requests.
    for key in sorted({int(digest(email)[:15],16) for email in (row.normalized_contact,current.normalized_value if current else row.normalized_contact)}):
        await db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':key})
    occupied=await db.scalar(select(ContactChannel).where(ContactChannel.normalized_value==row.normalized_contact))
    row.consumed_at=utcnow()
    if occupied and occupied.user_id!=principal.user_id:
        await db.commit()
        raise ApiError(409,'contact_unavailable','Эту почту нельзя связать с аккаунтом')
    if current is None:
        current=ContactChannel(user_id=principal.user_id,normalized_value=row.normalized_contact,verified_at=utcnow())
        db.add(current)
    else:current.normalized_value,current.verified_at=row.normalized_contact,utcnow()
    await db.execute(update(Session).where(Session.user_id==principal.user_id,Session.revoked_at.is_(None)).values(revoked_at=utcnow()))
    created,_=await issue_session(db,response,user_id=principal.user_id,mfa_at=session.mfa_at)
    audit(db,principal,'auth.contact_change.verify','user',principal.user_id,('verified_email','sessions'))
    result=await session_view(db,created)
    await db.commit()
    return result
