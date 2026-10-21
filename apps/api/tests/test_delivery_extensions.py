from uuid import UUID,uuid4
from datetime import timedelta
import httpx
import pytest
from sqlalchemy import select,func
from app.cli import fixtures
from app.core.auth import load_background_staff_authorization
from app.core.clock import utcnow
from app.core.crypto import digest,seal
from app.core.db import SessionLocal
from app.core.models import ContactChannel,Job,MfaFactor,Session,StaffMembership,PermissionGrant,User
from app.integrations.delivery.registry import register_email_purpose
from app.modules.messaging.consumers import enqueue_notice
from app.modules.messaging.models import Message
from app.modules.messaging.registry import register_notice_source
from app.modules.notifications.delivery import process_email,process_internal
from app.modules.notifications.models import NotificationPreference
from app.worker.queue import enqueue_outbox
from test_notifications import app
from test_messaging import actor

@pytest.mark.asyncio
async def test_trusted_mail_purpose_rechecks_hard_optout_and_sender(app):
    await fixtures()
    calls=[]
    async def source(db,outbox,payload):calls.append(payload['source_id']);return None
    register_email_purpose('fixture.staff_invitation',validate=source,render=lambda payload:('Internal fixture','Invented body'),required_permission='staff.manage')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as staff:
        identity,headers=await actor(staff,'coordinator@example.test',True)
        async with SessionLocal() as db:
            actor_session=await db.scalar(select(Session).where(Session.token_hash==digest(staff.cookies.get('opora_session'))))
            user=User(foundation_id=UUID(identity['foundation_id']),display_name='Invented staff recipient');db.add(user);await db.flush()
            email=uuid4().hex+'@fixture.example.test';db.add(ContactChannel(user_id=user.id,normalized_value=email,verified_at=utcnow()))
            preference=NotificationPreference(foundation_id=user.foundation_id,user_id=user.id,no_contact=True,email_enabled=False);db.add(preference);await db.flush()
            payload={'purpose':'fixture.staff_invitation','to':email,'source_id':uuid4().hex,'actor_session_id':str(actor_session.id),'actor_user_id':str(actor_session.user_id)}
            blocked=enqueue_outbox(db,user.foundation_id,'email',payload);await db.flush()
            assert (await process_email(db,await db.get(Job,blocked.job_id),blocked,payload)).state=='suppressed_no_contact'
            assert calls==[]
            preference.no_contact=False;await db.flush()
            allowed=enqueue_outbox(db,user.foundation_id,'email',payload);await db.flush()
            job=await db.get(Job,allowed.job_id);job.state='running';job.claim_token=uuid4();job.lease_until=utcnow()+timedelta(seconds=60);job.attempts=1
            await db.flush()
            assert (await process_email(db,await db.get(Job,allowed.job_id),allowed,payload)).state=='dev_inbox'
            assert calls==[payload['source_id'],payload['source_id']]
            actor_session.revoked_at=utcnow();await db.flush()
            revoked=enqueue_outbox(db,user.foundation_id,'email',payload);await db.flush()
            assert (await process_email(db,await db.get(Job,revoked.job_id),revoked,payload)).state=='suppressed_authz'
            await db.rollback()

@pytest.mark.asyncio
async def test_background_grants_have_no_session_and_notices_rebuild_from_source():
    seed=await fixtures()
    enabled=True
    async def resolve(db,outbox,source):
        if not enabled:return 'suppressed_schedule_changed'
        return {'recipient_id':source['recipient_id'],'subject':'Actual source','text':'Rebuilt current content','topic':'messages'}
    register_notice_source('fixture.report_digest',resolve)
    async with SessionLocal() as db:
        user=User(foundation_id=UUID(seed['foundation_id']),display_name='Invented background staff');db.add(user);await db.flush()
        member=StaffMembership(foundation_id=user.foundation_id,user_id=user.id);db.add(member);await db.flush()
        grant=PermissionGrant(membership_id=member.id,permission='reports.read',scope_type='foundation');db.add(grant)
        db.add(MfaFactor(user_id=user.id,secret_cipher=seal('JBSWY3DPEHPK3PXP'),confirmed_at=utcnow()));await db.flush()
        auth=await load_background_staff_authorization(db,user.foundation_id,user.id)
        assert auth and auth.has_permission('reports.read')
        assert await db.scalar(select(func.count()).select_from(Session).where(Session.user_id==user.id))==0
        source={'kind':'fixture.report_digest','recipient_id':str(user.id),'version':1}
        outbox=enqueue_notice(db,user.foundation_id,user.id,'CACHED SHOULD NOT APPEAR','cached',source=source);await db.flush()
        payload={'source':source,'recipient_id':str(user.id),'subject':'cached','text':'cached'}
        assert await process_internal(db,await db.get(Job,outbox.job_id),outbox,payload)=='delivered'
        message=await db.scalar(select(Message).where(Message.source_outbox_id==outbox.id));assert message.text=='Actual source\nRebuilt current content'
        enabled=False
        other=enqueue_notice(db,user.foundation_id,user.id,'cached','cached',source=source);await db.flush()
        assert await process_internal(db,await db.get(Job,other.job_id),other,payload)=='suppressed_schedule_changed'
        assert not await db.scalar(select(Message.id).where(Message.source_outbox_id==other.id))
        grant.revoked_at=utcnow();await db.flush()
        assert not (await load_background_staff_authorization(db,user.foundation_id,user.id)).has_permission('reports.read')
        await db.rollback()
