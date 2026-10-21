from datetime import timedelta
from uuid import UUID
import secrets
from fastapi import APIRouter,Depends,Request,Header
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select,or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal,get_principal,require_permission
from app.core.audit import audit
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.idempotency import begin_command,finish_command
from app.core.models import User,StaffMembership,PermissionGrant,ContactChannel,MfaFactor
from app.core.contact_policy import contact_guard
from .schemas import GrantInput,GrantView,RevokeView,StaffDirectoryView,StaffPermissionCatalogView,StaffScopeOptionView,StaffUserOptionView,StaffInvitationInput,StaffInvitationView,StaffInvitationAcceptInput,StaffVersionCommand
from .models import StaffInvitation
from .catalog import permission_catalog
from . import service as s
router=APIRouter(prefix='/api/v1',tags=['staff'])
manage=Depends(require_permission('staff.manage'))
async def grant_guard(db,principal,target):return await s.guard(db,principal,target)
async def command(db,p,operation,key,payload,authorize,action):
    try:
        context=await authorize()
        replay=await begin_command(db,p,operation,key,payload)
        if replay is not None:await db.commit();return replay
        result=jsonable_encoder(await action(context))
        await finish_command(db,p,operation,key,result);await db.commit();return result
    except IntegrityError as exc:
        await db.rollback()
        if getattr(exc.orig,'sqlstate',None)=='23505':raise ApiError(409,'staff_conflict','Приглашение или доступ уже изменились. Обновите данные.') from None
        raise
    except BaseException:await db.rollback();raise

@router.get('/coord/staff',response_model=StaffDirectoryView,operation_id='staff_directory')
async def directory(principal:Principal=manage,db:AsyncSession=Depends(get_db)):
    await s.guard(db,principal,step_up=False);return await s.directory(db,principal)
@router.get('/coord/staff/permission-catalog',response_model=StaffPermissionCatalogView,operation_id='staff_permission_catalog')
async def catalog(principal:Principal=manage,db:AsyncSession=Depends(get_db)):
    await s.guard(db,principal,step_up=False);return permission_catalog()
@router.get('/coord/staff/scopes',response_model=list[StaffScopeOptionView],operation_id='staff_scope_options')
async def scope_options(principal:Principal=manage,db:AsyncSession=Depends(get_db)):
    await s.guard(db,principal,step_up=False)
    from app.modules.participants.models import ParticipantGroup
    from app.modules.studio.models import Webinar
    groups=(await db.scalars(select(ParticipantGroup).where(ParticipantGroup.foundation_id==principal.foundation_id,ParticipantGroup.lifecycle=='active').order_by(ParticipantGroup.title))).all()
    webinars=(await db.scalars(select(Webinar).where(Webinar.foundation_id==principal.foundation_id,Webinar.state.in_(['draft','published'])).order_by(Webinar.starts_at))).all()
    return [{'scope_type':'foundation','id':None,'label':'Весь фонд'}]+[{'scope_type':'group','id':g.id,'label':g.title} for g in groups]+[{'scope_type':'webinar','id':w.id,'label':w.title} for w in webinars]
@router.get('/coord/staff/user-options',response_model=list[StaffUserOptionView],operation_id='staff_user_options')
async def user_options(q:str='',principal:Principal=manage,db:AsyncSession=Depends(get_db)):
    await s.guard(db,principal,step_up=False)
    q=q.strip()
    if len(q)<2:return []
    if len(q)>100:raise ApiError(422,'query_too_long','Сократите запрос до 100 символов.')
    pattern='%'+q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
    rows=(await db.execute(select(User,ContactChannel.normalized_value).join(ContactChannel,ContactChannel.user_id==User.id).where(User.foundation_id==principal.foundation_id,User.account_state=='active',ContactChannel.type=='email',ContactChannel.verified_at.is_not(None),or_(User.display_name.ilike(pattern,escape='\\'),ContactChannel.normalized_value.ilike(pattern,escape='\\'))).order_by(User.display_name,User.id).limit(20))).all()
    return [{'id':user.id,'display_name':user.display_name,'contact':contact,'version':user.authz_version} for user,contact in rows]

@router.post('/coord/staff/grants',operation_id='staff_grant',response_model=GrantView)
async def grant(body:GrantInput,request:Request,principal:Principal=manage,db:AsyncSession=Depends(get_db)):
    async def authorize():await s.guard(db,principal,body.user_id);return await s.require_user(db,principal,body.user_id)
    async def action(user):
        s.check_version(user,body.expected_version);data=(await s.selections(db,principal.foundation_id,[body]))[0];member=await s.membership(db,principal,user);row,added=await s.apply_grant(db,member,data)
        if added:user.authz_version+=1
        audit(db,principal,'staff.grant','permission_grant',row.id,('permission','scope'));return await s.grant_view(db,principal.foundation_id,row)
    return await command(db,principal,'staff.grant',request.headers.get('Idempotency-Key'),body.model_dump(mode='json'),authorize,action)
@router.post('/coord/staff/grants/{grant_id}/revoke',operation_id='staff_revoke',response_model=RevokeView)
async def revoke(grant_id:UUID,request:Request,body:StaffVersionCommand|None=None,principal:Principal=manage,db:AsyncSession=Depends(get_db)):
    async def authorize():
        row=await db.get(PermissionGrant,grant_id);member=await db.get(StaffMembership,row.membership_id) if row else None
        if not member or member.foundation_id!=principal.foundation_id:raise ApiError(404,'grant_not_found','Право не найдено.')
        await s.guard(db,principal,member.user_id);await db.refresh(row,with_for_update=True);user=await db.get(User,member.user_id,populate_existing=True);return row,user
    async def action(context):
        row,user=context;s.check_version(user,body.expected_version if body else None)
        if row.revoked_at is None:row.revoked_at=utcnow();user.authz_version+=1
        audit(db,principal,'staff.revoke','permission_grant',row.id,('revoked_at',));return {'status':'revoked','version':user.authz_version}
    return await command(db,principal,'staff.revoke',request.headers.get('Idempotency-Key'),{'grant_id':str(grant_id),**(body.model_dump() if body else {})},authorize,action)

@router.get('/coord/staff/invitations',response_model=list[StaffInvitationView],operation_id='staff_invitations')
async def invitations(principal:Principal=manage,db:AsyncSession=Depends(get_db)):
    await s.guard(db,principal,step_up=False)
    rows=(await db.scalars(select(StaffInvitation).where(StaffInvitation.foundation_id==principal.foundation_id).order_by(StaffInvitation.created_at.desc()).limit(200))).all()
    return [await s.invitation_view(db,row) for row in rows]
@router.post('/coord/staff/invitations',response_model=StaffInvitationView,status_code=201,operation_id='staff_invitation_create')
async def invite(body:StaffInvitationInput,principal:Principal=manage,db:AsyncSession=Depends(get_db),key:str|None=Header(default=None,alias='Idempotency-Key')):
    contact=body.contact.strip().lower()
    if '@' not in contact or any(c.isspace() for c in contact):raise ApiError(422,'invalid_contact','Укажите корректную почту.')
    async def authorize():await s.guard(db,principal);await contact_guard(db,principal.foundation_id)
    async def action(_):
        grants=await s.selections(db,principal.foundation_id,body.grants)
        previous=await db.scalar(select(StaffInvitation).where(StaffInvitation.foundation_id==principal.foundation_id,StaffInvitation.normalized_contact==contact,StaffInvitation.state.in_(['pending','accepted_pending_mfa'])).with_for_update())
        if previous:
            if previous.expires_at>utcnow():raise ApiError(409,'invitation_already_pending','Приглашение уже ожидает принятия.')
            previous.state='revoked';previous.revoked_at=utcnow();previous.version+=1;await db.flush()
        token=secrets.token_urlsafe(32);row=StaffInvitation(foundation_id=principal.foundation_id,normalized_contact=contact,token_hash=digest(token),grants=grants,invited_by_user_id=principal.user_id,expires_at=utcnow()+timedelta(hours=body.expires_in_hours),version=1)
        db.add(row);await db.flush();await s.queue_invitation(db,principal,row,token);audit(db,principal,'staff.invite','staff_invitation',row.id,('contact','permissions','expires_at'));return await s.invitation_view(db,row)
    return await command(db,principal,'staff.invite',key,body.model_dump(mode='json'),authorize,action)
async def managed_invitation(db,p,id):
    row=await db.scalar(select(StaffInvitation).where(StaffInvitation.id==id,StaffInvitation.foundation_id==p.foundation_id))
    if not row:s.deny()
    await s.guard(db,p,row.accepted_user_id);await contact_guard(db,p.foundation_id);await db.refresh(row,with_for_update=True);return row
@router.post('/coord/staff/invitations/{id}/revoke',response_model=StaffInvitationView,operation_id='staff_invitation_revoke')
async def revoke_invitation(id:UUID,body:StaffVersionCommand,principal:Principal=manage,db:AsyncSession=Depends(get_db),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def action(row):
        if row.version!=body.expected_version:raise ApiError(409,'version_conflict','Приглашение изменилось.',current_version=row.version)
        if row.state=='accepted':raise ApiError(409,'invitation_already_accepted','Сотрудник уже активирован. Отзовите его права в команде.')
        if row.state!='revoked':row.state='revoked';row.revoked_at=utcnow();row.version+=1
        audit(db,principal,'staff.invite.revoke','staff_invitation',id,('state',));return await s.invitation_view(db,row)
    return await command(db,principal,'staff.invite.revoke:'+str(id),key,body.model_dump(),lambda:managed_invitation(db,principal,id),action)
@router.post('/coord/staff/invitations/{id}/resend',response_model=StaffInvitationView,operation_id='staff_invitation_resend')
async def resend_invitation(id:UUID,body:StaffVersionCommand,principal:Principal=manage,db:AsyncSession=Depends(get_db),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def action(row):
        if row.version!=body.expected_version:raise ApiError(409,'version_conflict','Приглашение изменилось.',current_version=row.version)
        if row.state!='pending':raise ApiError(409,'invitation_not_pending','Это приглашение нельзя отправить повторно.')
        token=secrets.token_urlsafe(32);row.token_hash=digest(token);row.expires_at=utcnow()+timedelta(hours=72);row.version+=1;row.outbox_id=None
        await s.queue_invitation(db,principal,row,token);audit(db,principal,'staff.invite.resend','staff_invitation',id,('version','expires_at'));return await s.invitation_view(db,row)
    return await command(db,principal,'staff.invite.resend:'+str(id),key,body.model_dump(),lambda:managed_invitation(db,principal,id),action)

@router.post('/staff/invitations/accept',response_model=StaffInvitationView,operation_id='staff_invitation_accept')
async def accept(body:StaffInvitationAcceptInput,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def action(row):
        if row.state=='pending':
            user=await s.require_user(db,principal,principal.user_id);member=await s.membership(db,principal,user);row.accepted_user_id=user.id;row.accepted_membership_id=member.id;row.accepted_at=utcnow();row.state='accepted_pending_mfa';row.version+=1
            audit(db,principal,'staff.invite.accept','staff_invitation',row.id,('state','accepted_user_id'))
        return await s.invitation_view(db,row,principal)
    return await command(db,principal,'staff.invite.accept',key,{'token_hash':digest(body.token)},lambda:s.recipient_invitation(db,principal,token=body.token),action)
@router.get('/staff/invitations/{id}',response_model=StaffInvitationView,operation_id='staff_invitation_self')
async def invitation_self(id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    row=await s.recipient_invitation(db,principal,id=id)
    if row.accepted_user_id!=principal.user_id:s.deny()
    return await s.invitation_view(db,row,principal)
@router.post('/staff/invitations/{id}/finalize',response_model=StaffInvitationView,operation_id='staff_invitation_finalize')
async def finalize(id:UUID,body:StaffVersionCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),key:str|None=Header(default=None,alias='Idempotency-Key')):
    async def authorize():
        row=await s.recipient_invitation(db,principal,id=id)
        if row.accepted_user_id!=principal.user_id:s.deny()
        await s.guard(db,principal,row.invited_by_user_id,manage=False)
        factor=await db.scalar(select(MfaFactor).where(MfaFactor.user_id==principal.user_id,MfaFactor.confirmed_at.is_not(None)))
        if not factor:raise ApiError(403,'mfa_required','Настройте и подтвердите второй фактор.')
        return row
    async def action(row):
        if row.version!=body.expected_version:raise ApiError(409,'version_conflict','Приглашение изменилось.',current_version=row.version)
        if row.state!='accepted_pending_mfa':raise ApiError(409,'invitation_not_pending','Приглашение уже завершено.')
        grants=await s.selections(db,principal.foundation_id,row.grants);user=await s.require_user(db,principal,principal.user_id);member=await s.membership(db,principal,user);changed=False
        for data in grants:
            _,added=await s.apply_grant(db,member,data);changed=changed or added
        if changed:user.authz_version+=1
        row.state='accepted';row.finalized_at=utcnow();row.version+=1;audit(db,principal,'staff.invite.finalize','staff_invitation',id,('permissions','state'));return await s.invitation_view(db,row,principal)
    return await command(db,principal,'staff.invite.finalize:'+str(id),key,body.model_dump(),authorize,action)
