from datetime import timedelta
from hashlib import sha256
from uuid import UUID
import secrets
from sqlalchemy import select,text,update,or_
from app.core.auth import authz_guard
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.errors import ApiError
from app.core.models import User,StaffMembership,PermissionGrant,Session,ContactChannel,MfaFactor,OutboxMessage
from app.core.contact_policy import contact_guard
from app.worker.queue import enqueue_outbox
from app.integrations.delivery.email import readiness
from .catalog import LABELS,scopes
from .models import StaffInvitation

def deny():raise ApiError(404,'staff_invitation_invalid','Приглашение недействительно или недоступно.')
async def guard(db,p,*targets,manage=True,step_up=True):
    subjects={p.user_id or p.registration_id,*targets}-{None}
    keys=sorted(int.from_bytes(sha256(f'authz:{p.foundation_id}:{subject}'.encode()).digest()[:8],'big',signed=True) for subject in subjects)
    for key in keys:await db.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':key})
    await authz_guard(db,p)
    if manage and not p.has_permission('staff.manage'):raise ApiError(403,'permission_denied','Недостаточно прав для управления командой.')
    current=await db.get(Session,p.session_id,populate_existing=True);p.mfa_at=current.mfa_at
    if step_up and (not current.mfa_at or current.mfa_at<utcnow()-timedelta(minutes=10)):raise ApiError(403,'step_up_required','Подтвердите вход перед изменением доступа.')
async def require_user(db,p,id):
    user=await db.get(User,id,populate_existing=True)
    if not user or user.foundation_id!=p.foundation_id or user.account_state!='active':raise ApiError(404,'user_not_found','Пользователь не найден.')
    if not await db.scalar(select(ContactChannel.id).where(ContactChannel.user_id==id,ContactChannel.type=='email',ContactChannel.verified_at.is_not(None))):raise ApiError(409,'verified_contact_required','Пользователь должен подтвердить почту.')
    return user
async def scope_label(db,foundation_id,scope_type,scope_id):
    if scope_type=='foundation':
        if scope_id is not None:raise ApiError(422,'invalid_scope','Область всего фонда не содержит отдельный объект.')
        return 'Весь фонд'
    if scope_id is None:raise ApiError(422,'invalid_scope','Выберите область доступа.')
    if scope_type=='group':
        from app.modules.participants.models import ParticipantGroup
        row=await db.scalar(select(ParticipantGroup).where(ParticipantGroup.id==scope_id,ParticipantGroup.foundation_id==foundation_id,ParticipantGroup.lifecycle=='active'))
        if row:return row.title
    if scope_type=='webinar':
        from app.modules.studio.models import Webinar
        row=await db.scalar(select(Webinar).where(Webinar.id==scope_id,Webinar.foundation_id==foundation_id,Webinar.state.in_(['draft','published'])))
        if row:return row.title
    raise ApiError(422,'invalid_scope','Область доступа не найдена в этом фонде.')
async def selections(db,foundation_id,values):
    result=[];seen=set()
    for value in values:
        data=value.model_dump(mode='json') if hasattr(value,'model_dump') else dict(value)
        name=data['permission'];kind=data.get('scope_type','foundation');id=UUID(str(data['scope_id'])) if data.get('scope_id') else None
        if name not in LABELS or kind not in scopes(name):raise ApiError(422,'invalid_permission','Выберите право и область из каталога.')
        await scope_label(db,foundation_id,kind,id)
        key=(name,kind,id)
        if key not in seen:seen.add(key);result.append({'permission':name,'scope_type':kind,'scope_id':str(id) if id else None})
    return result
async def grant_view(db,foundation_id,row):
    try:label=await scope_label(db,foundation_id,row.scope_type,row.scope_id)
    except ApiError:label='Объект недоступен'
    return {'id':str(row.id),'permission':row.permission,'scope_type':row.scope_type,'scope_id':str(row.scope_id) if row.scope_id else None,'scope_label':label,'revoked_at':row.revoked_at}
def check_version(user,expected):
    if expected is not None and user.authz_version!=expected:raise ApiError(409,'version_conflict','Права изменились. Обновите данные.',current_version=user.authz_version)
async def membership(db,p,user):
    member=await db.scalar(select(StaffMembership).where(StaffMembership.foundation_id==p.foundation_id,StaffMembership.user_id==user.id).with_for_update())
    if member is None:member=StaffMembership(foundation_id=p.foundation_id,user_id=user.id);db.add(member);await db.flush()
    if member.revoked_at:
        # Re-activation must never revive historical permissions before explicit approval.
        await db.execute(update(PermissionGrant).where(PermissionGrant.membership_id==member.id,PermissionGrant.revoked_at.is_(None)).values(revoked_at=utcnow()))
        member.revoked_at=None
    return member
async def apply_grant(db,member,data):
    id=UUID(data['scope_id']) if data.get('scope_id') else None
    query=select(PermissionGrant).where(PermissionGrant.membership_id==member.id,PermissionGrant.permission==data['permission'],PermissionGrant.scope_type==data['scope_type'],PermissionGrant.scope_id==id,PermissionGrant.revoked_at.is_(None))
    row=await db.scalar(query)
    if row:return row,False
    row=PermissionGrant(membership_id=member.id,permission=data['permission'],scope_type=data['scope_type'],scope_id=id);db.add(row);await db.flush();return row,True
async def check_issuer(db,row):
    user=await db.get(User,row.invited_by_user_id,populate_existing=True)
    valid=await db.scalar(select(PermissionGrant.id).join(StaffMembership,StaffMembership.id==PermissionGrant.membership_id).where(StaffMembership.foundation_id==row.foundation_id,StaffMembership.user_id==row.invited_by_user_id,StaffMembership.revoked_at.is_(None),PermissionGrant.revoked_at.is_(None),PermissionGrant.permission=='staff.manage',PermissionGrant.scope_type=='foundation',PermissionGrant.scope_id.is_(None)))
    if not user or user.account_state!='active' or not valid:deny()
async def invitation_view(db,row,p=None):
    outbox=await db.get(OutboxMessage,row.outbox_id) if row.outbox_id else None
    state='expired' if row.expires_at<=utcnow() and row.state in ('pending','accepted_pending_mfa') else row.state
    action='none'
    if p and p.user_id:
        if state=='accepted_pending_mfa' and row.accepted_user_id==p.user_id:
            factor=await db.scalar(select(MfaFactor).where(MfaFactor.user_id==p.user_id))
            session=await db.get(Session,p.session_id,populate_existing=True)
            action='enroll_mfa' if not factor or not factor.confirmed_at else 'verify_mfa' if not session.mfa_at or session.mfa_at<utcnow()-timedelta(minutes=10) else 'finalize'
        elif state=='accepted':action='complete'
    return {'id':str(row.id),'contact':row.normalized_contact,'state':state,'expires_at':row.expires_at,'grants':row.grants,'delivery_state':outbox.state if outbox else 'unavailable','version':row.version,'accepted_user_id':str(row.accepted_user_id) if row.accepted_user_id else None,'membership_id':str(row.accepted_membership_id) if row.accepted_membership_id else None,'next_action':action}
async def queue_invitation(db,p,row,token):
    from app.modules.notifications.service import hard_contact_allowed
    from . import delivery
    contact=await db.scalar(select(ContactChannel).where(ContactChannel.normalized_value==row.normalized_contact,ContactChannel.type=='email',ContactChannel.verified_at.is_not(None)))
    if contact:
        user=await db.get(User,contact.user_id)
        if not user or user.foundation_id!=p.foundation_id:raise ApiError(409,'contact_unavailable','Этот контакт недоступен для приглашения.')
        allowed,reason=await hard_contact_allowed(db,p.foundation_id,user.id)
        if not allowed:raise ApiError(409,'contact_suppressed','Получатель запретил контакты с фондом.')
    if readiness()['state']=='unavailable':return
    outbox=enqueue_outbox(db,p.foundation_id,'email',{'purpose':'staff_invitation','to':row.normalized_contact,'invitation_id':str(row.id),'invitation_version':row.version,'token':token,'actor_user_id':str(p.user_id),'actor_session_id':str(p.session_id)})
    await db.flush();row.outbox_id=outbox.id
async def recipient_invitation(db,p,id=None,token=None):
    if not p.user_id:raise ApiError(401,'verified_user_required','Войдите с подтверждённой почтой получателя приглашения.')
    query=select(StaffInvitation).where(StaffInvitation.foundation_id==p.foundation_id)
    query=query.where(StaffInvitation.id==id) if id else query.where(StaffInvitation.token_hash==digest(token))
    row=await db.scalar(query)
    if not row:deny()
    await guard(db,p,row.invited_by_user_id,manage=False,step_up=False)
    row=await db.scalar(select(StaffInvitation).where(StaffInvitation.id==row.id).with_for_update().execution_options(populate_existing=True))
    if row.state=='revoked' or row.expires_at<=utcnow():deny()
    await check_issuer(db,row)
    contact=await db.scalar(select(ContactChannel.id).where(ContactChannel.user_id==p.user_id,ContactChannel.normalized_value==row.normalized_contact,ContactChannel.type=='email',ContactChannel.verified_at.is_not(None)))
    if not contact or row.accepted_user_id not in (None,p.user_id):deny()
    return row
async def directory(db,p):
    members=(await db.scalars(select(StaffMembership).where(StaffMembership.foundation_id==p.foundation_id).order_by(StaffMembership.created_at))).all();items=[]
    for member in members:
        user=await db.get(User,member.user_id);factor=await db.scalar(select(MfaFactor).where(MfaFactor.user_id==user.id));contact=await db.scalar(select(ContactChannel.normalized_value).where(ContactChannel.user_id==user.id,ContactChannel.type=='email',ContactChannel.verified_at.is_not(None)))
        grants=(await db.scalars(select(PermissionGrant).where(PermissionGrant.membership_id==member.id).order_by(PermissionGrant.created_at))).all()
        pending=await db.scalar(select(StaffInvitation.id).where(StaffInvitation.accepted_membership_id==member.id,StaffInvitation.state=='accepted_pending_mfa',StaffInvitation.expires_at>utcnow()))
        items.append({'user_id':str(user.id),'display_name':user.display_name,'verified_contact':contact,'membership_id':str(member.id),'state':'revoked' if member.revoked_at else 'pending_mfa' if pending else 'active','mfa_state':'not_enrolled' if not factor else 'enabled' if factor.confirmed_at else 'pending','version':user.authz_version,'grants':[await grant_view(db,p.foundation_id,g) for g in grants]})
    return {'items':items}
