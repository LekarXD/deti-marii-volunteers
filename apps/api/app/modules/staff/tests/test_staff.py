import asyncio,json,os
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID,uuid4
import pyotp,pytest
from fastapi import Response
from starlette.requests import Request
from sqlalchemy import select,text,func
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.core.clock import utcnow
from app.core.auth import resolve_principal
from app.core.crypto import digest,seal,unseal
from app.core.config import get_settings
from app.core.db import Base
from app.core.errors import ApiError
from app.core.model_loader import load_models
from app.core.models import Foundation,User,Session,ContactChannel,StaffMembership,PermissionGrant,MfaFactor,MutationReceipt,OutboxMessage
from app.modules.staff import router as r,service as s,delivery
from app.modules.staff.models import StaffInvitation
from app.modules.staff.schemas import StaffInvitationInput,StaffInvitationAcceptInput,StaffVersionCommand,GrantInput

@pytest.fixture
async def world(tmp_path,monkeypatch):
    url=os.environ.get('OPORA_STAFF_TEST_DATABASE_URL') or os.environ.get('OPORA_TEST_DATABASE_URL')
    if not url:pytest.skip('Set disposable OPORA_STAFF_TEST_DATABASE_URL')
    load_models()
    from app.modules.activities import assignment_models
    schema='staff_'+uuid4().hex;admin=create_async_engine(url)
    async with admin.begin() as c:await c.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'));await c.execute(text(f'CREATE SCHEMA "{schema}"'))
    engine=create_async_engine(url,connect_args={'options':f'-csearch_path={schema}'});factory=async_sessionmaker(engine,expire_on_commit=False)
    async with engine.begin() as c:await c.run_sync(Base.metadata.create_all)
    async with factory() as db:
        foundation=Foundation(name='Staff fixture');foreign=Foundation(name='Foreign fixture');db.add_all([foundation,foreign]);await db.flush()
        users=[];sessions=[]
        for name,scope in [('Admin',foundation),('Recipient',foundation),('Wrong',foundation),('Foreign',foreign)]:
            user=User(foundation_id=scope.id,display_name=name);db.add(user);await db.flush();db.add(ContactChannel(user_id=user.id,normalized_value=name.lower()+'@staff.example.test',verified_at=utcnow()))
            session=Session(foundation_id=scope.id,user_id=user.id,token_hash=uuid4().hex,csrf_hash=uuid4().hex,csrf_cipher=seal('fixture-csrf'),expires_at=utcnow()+timedelta(days=1),mfa_at=utcnow() if name=='Admin' else None);db.add(session);users.append(user);sessions.append(session)
        membership=StaffMembership(foundation_id=foundation.id,user_id=users[0].id);db.add(membership);await db.flush();db.add(PermissionGrant(membership_id=membership.id,permission='staff.manage'));db.add(MfaFactor(user_id=users[0].id,secret_cipher=seal(pyotp.random_base32()),confirmed_at=utcnow()))
        await db.commit();actors=[await resolve_principal(db,session) for session in sessions]
    settings=get_settings();monkeypatch.setattr(settings,'environment','development');monkeypatch.setattr(settings,'dev_inbox',True);monkeypatch.setattr(settings,'foundation_id',foundation.id)
    yield SimpleNamespace(factory=factory,foundation=foundation,foreign=foreign,admin=actors[0],recipient=actors[1],wrong=actors[2],foreign_actor=actors[3],users=users)
    await engine.dispose()
    async with admin.begin() as c:await c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await admin.dispose()

def request(key):return Request({'type':'http','method':'POST','path':'/api/v1/coord/staff/grants','headers':[(b'idempotency-key',key.encode())]})
def body(contact='recipient@staff.example.test',permission='roles.manage'):return StaffInvitationInput(contact=contact,grants=[{'permission':permission}])
async def invitation(w,contact='recipient@staff.example.test',key='invite'):
    async with w.factory() as db:value=await r.invite(body(contact),w.admin,db,key)
    async with w.factory() as db:
        row=await db.get(StaffInvitation,UUID(value['id']));outbox=await db.get(OutboxMessage,row.outbox_id);payload=json.loads(unseal(outbox.payload_cipher)) if outbox else None
    return value,payload
async def accept(w,token,key='accept'):
    async with w.factory() as db:return await r.accept(StaffInvitationAcceptInput(token=token),w.recipient,db,key)

@pytest.mark.asyncio
async def test_verified_accept_requires_actual_mfa_before_any_new_grants(world):
    from app.modules.auth.router import enroll,mfa_verify,MfaInput
    w=world;created,payload=await invitation(w);accepted=await accept(w,payload['token'])
    assert accepted['state']=='accepted_pending_mfa' and accepted['next_action']=='enroll_mfa'
    async with w.factory() as db:
        member=await db.get(StaffMembership,UUID(accepted['membership_id']));assert member.user_id==w.recipient.user_id
        assert await db.scalar(select(func.count()).select_from(PermissionGrant).where(PermissionGrant.membership_id==member.id))==0
        principal=await resolve_principal(db,await db.get(Session,w.recipient.session_id));assert not principal.is_staff
        with pytest.raises(ApiError) as denied:await r.finalize(UUID(created['id']),StaffVersionCommand(expected_version=2),principal,db,'finalize')
        assert denied.value.code=='step_up_required'
    async with w.factory() as db:enrolled=await enroll(w.recipient,db)
    async with w.factory() as db:
        response=Response();verified=await mfa_verify(MfaInput(code=pyotp.TOTP(enrolled['secret']).now()),response,w.recipient,db);assert verified['is_staff'] and not verified['permissions']
        session=await db.scalar(select(Session).where(Session.user_id==w.recipient.user_id,Session.revoked_at.is_(None)).order_by(Session.created_at.desc()));w.recipient=await resolve_principal(db,session)
    async with w.factory() as db:final=await r.finalize(UUID(created['id']),StaffVersionCommand(expected_version=2),w.recipient,db,'finalize')
    assert final['state']=='accepted' and final['next_action']=='complete'
    async with w.factory() as db:
        assert await r.finalize(UUID(created['id']),StaffVersionCommand(expected_version=2),w.recipient,db,'finalize')==final
        fresh=await resolve_principal(db,await db.get(Session,w.recipient.session_id));assert fresh.has_permission('roles.manage')
        assert await db.scalar(select(func.count()).select_from(PermissionGrant).where(PermissionGrant.membership_id==UUID(accepted['membership_id'])))==1
        row=await db.get(StaffInvitation,UUID(created['id']));outbox=await db.get(OutboxMessage,row.outbox_id);assert await delivery.validate(db,outbox,payload)=='suppressed_stale_invitation'

@pytest.mark.asyncio
async def test_wrong_contact_foreign_invalid_expired_and_revoked_invites_cannot_accept(world):
    w=world;created,payload=await invitation(w)
    for principal,token in [(w.wrong,payload['token']),(w.foreign_actor,payload['token']),(w.recipient,'wrong-token-at-least-twenty-characters')]:
        async with w.factory() as db:
            with pytest.raises(ApiError):await r.accept(StaffInvitationAcceptInput(token=token),principal,db,uuid4().hex)
    async with w.factory() as db:await r.revoke_invitation(UUID(created['id']),StaffVersionCommand(expected_version=1),w.admin,db,'revoke-invite')
    with pytest.raises(ApiError):await accept(w,payload['token'])
    second,second_payload=await invitation(w,key='second')
    async with w.factory() as db:
        row=await db.get(StaffInvitation,UUID(second['id']));row.expires_at=utcnow()-timedelta(seconds=1);await db.commit()
    with pytest.raises(ApiError):await accept(w,second_payload['token'])

@pytest.mark.asyncio
async def test_receipt_replay_rechecks_current_issuer_grant_and_scope_is_real(world):
    w=world;body_grant=GrantInput(user_id=w.recipient.user_id,permission='roles.manage',expected_version=1)
    async with w.factory() as db:granted=await r.grant(body_grant,request('grant'),w.admin,db)
    async with w.factory() as db:assert await r.grant(body_grant,request('grant'),w.admin,db)==granted
    async with w.factory() as db:
        for bad in [GrantInput(user_id=w.foreign_actor.user_id,permission='roles.manage'),GrantInput(user_id=w.recipient.user_id,permission='staff.wish'),GrantInput(user_id=w.recipient.user_id,permission='participants.read',scope_type='group',scope_id=uuid4())]:
            with pytest.raises(ApiError):await r.grant(bad,request(uuid4().hex),w.admin,db)
    async with w.factory() as db:
        own=await db.scalar(select(PermissionGrant).where(PermissionGrant.permission=='staff.manage'));own.revoked_at=utcnow();await db.commit()
    async with w.factory() as db:
        with pytest.raises(ApiError) as denied:await r.grant(body_grant,request('grant'),w.admin,db)
        assert denied.value.code=='permission_denied'

@pytest.mark.asyncio
async def test_grant_version_race_and_revoke_receipt_are_serialized(world):
    w=world
    async def grant(permission):
        async with w.factory() as db:return await r.grant(GrantInput(user_id=w.recipient.user_id,permission=permission,expected_version=1),request(permission),w.admin,db)
    results=await asyncio.gather(grant('roles.manage'),grant('candidates.read'),return_exceptions=True)
    assert sum(isinstance(value,dict) for value in results)==1
    assert next(value for value in results if isinstance(value,ApiError)).code=='version_conflict'
    value=next(value for value in results if isinstance(value,dict))
    async with w.factory() as db:revoked=await r.revoke(UUID(value['id']),request('revoke'),StaffVersionCommand(expected_version=2),w.admin,db)
    async with w.factory() as db:assert await r.revoke(UUID(value['id']),request('revoke'),StaffVersionCommand(expected_version=2),w.admin,db)==revoked
    assert revoked['version']==3

@pytest.mark.asyncio
async def test_delivery_is_canonical_and_unavailable_provider_does_not_enqueue(world,monkeypatch):
    w=world;created,payload=await invitation(w)
    async with w.factory() as db:
        row=await db.get(StaffInvitation,UUID(created['id']));outbox=await db.get(OutboxMessage,row.outbox_id)
        assert await delivery.validate(db,outbox,payload) is None
        assert 'token' not in created and payload['token'] not in json.dumps(created,default=str)
    async with w.factory() as db:await r.resend_invitation(UUID(created['id']),StaffVersionCommand(expected_version=1),w.admin,db,'resend')
    async with w.factory() as db:assert await delivery.validate(db,outbox,payload)=='suppressed_stale_invitation'
    monkeypatch.setattr(s,'readiness',lambda:{'state':'unavailable'})
    async with w.factory() as db:
        result=await r.invite(body('new@staff.example.test'),w.admin,db,'unavailable');assert result['delivery_state']=='unavailable'
        row=await db.get(StaffInvitation,UUID(result['id']));assert row.outbox_id is None

@pytest.mark.asyncio
async def test_hard_no_contact_blocks_enqueue_and_existing_dispatch_without_topic_opt_in(world):
    from app.modules.crm.models import CrmVolunteer
    from app.modules.notifications.delivery import check_email
    w=world;created,payload=await invitation(w)
    async with w.factory() as db:
        row=await db.get(StaffInvitation,UUID(created['id']));outbox=await db.get(OutboxMessage,row.outbox_id)
        # Administrative invitation is supported without newsletter/volunteer topic opt-in.
        assert await check_email(db,outbox,payload) is None
        db.add(CrmVolunteer(foundation_id=w.foundation.id,user_id=w.recipient.user_id,display_name='Recipient',no_contact=True));await db.commit()
    async with w.factory() as db:assert await check_email(db,outbox,payload)=='suppressed_no_contact'
    async with w.factory() as db:await r.revoke_invitation(UUID(created['id']),StaffVersionCommand(expected_version=1),w.admin,db,'revoke')
    async with w.factory() as db:
        with pytest.raises(ApiError) as denied:await r.invite(body(),w.admin,db,'new-contact-attempt')
        assert denied.value.code=='contact_suppressed'
    async with w.factory() as db:assert await db.scalar(select(func.count()).select_from(StaffInvitation))==1

@pytest.mark.asyncio
async def test_http_directory_catalog_scope_and_cross_foundation_acl(world,monkeypatch):
    import httpx
    from fastapi import FastAPI
    from app.core.db import get_db
    from app.core.errors import install_error_handlers
    from app.modules.participants.models import ParticipantGroup
    w=world;monkeypatch.setattr(get_settings(),'trusted_origins',['http://testserver'])
    async with w.factory() as db:
        admin_session=await db.get(Session,w.admin.session_id);admin_session.token_hash=digest('staff-test-cookie');admin_session.csrf_hash=digest('staff-test-csrf')
        recipient_session=await db.get(Session,w.recipient.session_id);recipient_session.token_hash=digest('recipient-test-cookie')
        foreign_group=ParticipantGroup(foundation_id=w.foreign.id,title='Foreign group');db.add(foreign_group);await db.commit()
    app=FastAPI();install_error_handlers(app);app.include_router(r.router)
    async def database():
        async with w.factory() as db:yield db
    app.dependency_overrides[get_db]=database
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',cookies={'opora_session':'staff-test-cookie'}) as client:
        directory=await client.get('/api/v1/coord/staff');assert directory.status_code==200 and directory.json()['items'][0]['display_name']=='Admin'
        catalog=(await client.get('/api/v1/coord/staff/permission-catalog')).json()['items'];assert any(p['permission']=='participants.read' and p['scope_types']==['foundation','group'] for p in catalog)
        scope_values=(await client.get('/api/v1/coord/staff/scopes')).json();assert not any(s['label']=='Foreign group' for s in scope_values)
        options=(await client.get('/api/v1/coord/staff/user-options?q=staff.example.test')).json();assert all(p['display_name']!='Foreign' for p in options)
        headers={'Origin':'http://testserver','X-CSRF-Token':'staff-test-csrf','Idempotency-Key':'foreign-grant'}
        denied=await client.post('/api/v1/coord/staff/grants',json={'user_id':str(w.foreign_actor.user_id),'permission':'roles.manage'},headers=headers);assert denied.status_code==404
        denied=await client.post('/api/v1/coord/staff/grants',json={'user_id':str(w.recipient.user_id),'permission':'participants.read','scope_type':'group','scope_id':str(foreign_group.id)},headers=headers);assert denied.status_code==422
        client.cookies.set('opora_session','recipient-test-cookie')
        assert (await client.get('/api/v1/coord/staff')).status_code==403

@pytest.mark.asyncio
async def test_actual_outbox_worker_records_development_delivery_without_smtp(world,monkeypatch):
    import smtplib
    from app.modules.notifications.delivery import process_email
    from app.worker.queue import claim,complete
    w=world;created,payload=await invitation(w)
    def forbidden_smtp(*args,**kwargs):raise AssertionError('External SMTP must never run in staff tests')
    monkeypatch.setattr(smtplib,'SMTP',forbidden_smtp)
    async with w.factory() as db:
        job=await claim(db,kinds=['outbox.deliver']);await db.commit()
        outbox=await db.get(OutboxMessage,UUID(job.payload['outbox_id']));outcome=await process_email(db,job,outbox,payload)
        assert outcome.state=='dev_inbox';await complete(db,job.id,job.claim_token,{'state':outcome.state});await db.commit()
    async with w.factory() as db:
        row=await db.get(StaffInvitation,UUID(created['id']));assert (await s.invitation_view(db,row))['delivery_state']=='dev_inbox'
        assert payload['token'] not in delivery.render(payload)[0]

@pytest.mark.asyncio
async def test_queued_permission_revocation_wins_before_grant_reauthorization(world):
    from hashlib import sha256
    w=world
    async with w.factory() as db:
        member=StaffMembership(foundation_id=w.foundation.id,user_id=w.wrong.user_id);db.add(member);await db.flush();db.add(PermissionGrant(membership_id=member.id,permission='staff.manage'))
        session=await db.get(Session,w.wrong.session_id);session.mfa_at=utcnow();db.add(MfaFactor(user_id=w.wrong.user_id,secret_cipher=seal(pyotp.random_base32()),confirmed_at=utcnow()));await db.commit();other=await resolve_principal(db,session)
        original=await db.scalar(select(PermissionGrant).join(StaffMembership).where(StaffMembership.user_id==w.admin.user_id,PermissionGrant.permission=='staff.manage'));original_id=original.id
    key=int.from_bytes(sha256(f'authz:{w.foundation.id}:{w.admin.user_id}'.encode()).digest()[:8],'big',signed=True)
    pids={}
    async def revoker():
        async with w.factory() as db:
            pids['revoke']=await db.scalar(text('SELECT pg_backend_pid()'))
            return await r.revoke(original_id,request('queued-revoke'),None,other,db)
    async def granter():
        async with w.factory() as db:
            pids['grant']=await db.scalar(text('SELECT pg_backend_pid()'))
            return await r.grant(GrantInput(user_id=w.recipient.user_id,permission='roles.manage'),request('queued-grant'),w.admin,db)
    async def blocked(name,observer):
        for _ in range(100):
            if name in pids and await observer.scalar(text('SELECT cardinality(pg_blocking_pids(:pid))>0'),{'pid':pids[name]}):return
            await asyncio.sleep(.01)
        raise AssertionError('Command did not reach the held authorization lock')
    async with w.factory() as holder:
        await holder.execute(text('SELECT pg_advisory_xact_lock(:key)'),{'key':key})
        revoke_task=asyncio.create_task(revoker());await blocked('revoke',holder)
        grant_task=asyncio.create_task(granter());await blocked('grant',holder)
        await holder.commit()
        results=await asyncio.gather(revoke_task,grant_task,return_exceptions=True)
    assert results[0]['status']=='revoked'
    assert isinstance(results[1],ApiError) and results[1].code=='permission_denied'
    async with w.factory() as db:
        assert await db.scalar(select(func.count()).select_from(PermissionGrant).where(PermissionGrant.permission=='roles.manage'))==0
        assert await db.scalar(select(func.count()).select_from(MutationReceipt).where(MutationReceipt.key=='queued-grant'))==0
