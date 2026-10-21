from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func
from app.core.clock import utcnow
from app.core.crypto import seal,unseal
import json
from app.core.models import MfaFactor,PermissionGrant,StaffMembership,OutboxMessage
from app.modules.messaging.models import Message
from app.modules.messaging.consumers import deliver_internal
from app.modules.reporting.models import ReportDigestSchedule,ReportDigestDelivery
from app.modules.reporting.digests import next_run
from app.modules.reporting.jobs import run_digest
from app.modules.reporting.tests.test_reporting import env,reporter,principal
from app.modules.applications.tests.test_applications import staff

async def factor(factory,user_id):
    async with factory() as db:
        db.add(MfaFactor(user_id=user_id,secret_cipher=seal('JBSWY3DPEHPK3PXP'),confirmed_at=utcnow()));await db.commit()

async def save(client,body,key=None):
    return await client.put('/api/v1/coord/report-digests',json=body,headers={'Idempotency-Key':key or str(uuid4())})

def test_weekly_dispatch_uses_explicit_timezone_and_strict_next_occurrence():
    after=datetime(2026,10,19,6,0,tzinfo=timezone.utc)
    assert next_run(0,540,'Europe/Moscow',after)==after+timedelta(days=7)
    assert next_run(0,541,'Europe/Moscow',after)==after+timedelta(minutes=1)

@pytest.mark.asyncio
async def test_schedule_requires_background_mfa_valid_recipients_and_cas(env):
    app,factory=env;owner=await reporter(app,factory);recipient=await staff(app,factory,('reports.read',));other=await staff(app,factory,())
    op=await principal(owner,factory);rp=await principal(recipient,factory);np=await principal(other,factory)
    try:
        body=dict(expected_version=0,enabled=True,recipient_ids=[str(rp.user_id)],weekday=0,minute_of_day=540,timezone='Europe/Moscow')
        assert (await save(owner,body)).status_code==403
        await factor(factory,op.user_id);await factor(factory,rp.user_id)
        bad=await save(owner,dict(body,recipient_ids=[str(np.user_id)]));assert bad.status_code==422
        response=await save(owner,body,'weekly');assert response.status_code==200,response.text
        schedule=response.json();assert schedule['state']=='scheduled' and schedule['version']==1 and schedule['next_run_at']
        assert (await save(owner,body,'weekly')).json()==schedule
        assert (await save(owner,body)).status_code==409
        disabled=await save(owner,dict(body,expected_version=1,enabled=False));assert disabled.status_code==200
        assert disabled.json()['next_run_at'] is None and disabled.json()['state']=='disabled'
    finally:
        for client in (owner,recipient,other):await client.aclose()

@pytest.mark.asyncio
async def test_due_digest_is_idempotent_and_delivery_rechecks_revocation(env):
    app,factory=env;owner=await reporter(app,factory);recipient=await staff(app,factory,('reports.read',))
    op=await principal(owner,factory);rp=await principal(recipient,factory)
    try:
        await factor(factory,op.user_id);await factor(factory,rp.user_id)
        response=await save(owner,dict(expected_version=0,enabled=True,recipient_ids=[str(rp.user_id)],weekday=0,minute_of_day=540,timezone='Europe/Moscow'));assert response.status_code==200,response.text
        scheduled=response.json();due=utcnow()-timedelta(seconds=1);fences=[]
        async def fence(db):fences.append(True)
        context=SimpleNamespace(foundation_id=op.foundation_id,payload=dict(schedule_id=scheduled['id'],version=1,scheduled_for=due.isoformat()),fence=fence)
        async with factory() as db:
            row=await db.get(ReportDigestSchedule,UUID(scheduled['id']));row.next_run_at=due;await db.commit()
            result=await run_digest(db,context);assert result['queued']==1 and fences
            await db.commit();assert (await run_digest(db,context))['state']=='superseded'
            assert await db.scalar(select(func.count()).select_from(ReportDigestDelivery))==1
            outbox=await db.scalar(select(OutboxMessage));payload=json.loads(unseal(outbox.payload_cipher))
            membership=await db.scalar(select(StaffMembership).where(StaffMembership.user_id==rp.user_id))
            grant=await db.scalar(select(PermissionGrant).where(PermissionGrant.membership_id==membership.id,PermissionGrant.permission=='reports.read'));grant.revoked_at=utcnow();await db.commit()
            assert await deliver_internal(db,outbox,payload)=='suppressed_report_revoked'
            assert not await db.scalar(select(Message.id).where(Message.source_outbox_id==outbox.id))
            await db.rollback()
    finally:
        for client in (owner,recipient):await client.aclose()

@pytest.mark.asyncio
async def test_delivery_rebuilds_real_metrics_without_cached_numbers(env):
    from app.modules.reporting.tests.test_reporting import fixture_facts
    app,factory=env;facts=await fixture_facts(app,factory);owner=facts['coord'];recipient=await staff(app,factory,('reports.read',));op=await principal(owner,factory);rp=await principal(recipient,factory)
    try:
        await factor(factory,op.user_id);await factor(factory,rp.user_id)
        response=await save(owner,dict(expected_version=0,enabled=True,recipient_ids=[str(rp.user_id)],weekday=0,minute_of_day=540,timezone='Europe/Moscow'));assert response.status_code==200,response.text
        due=utcnow()-timedelta(seconds=1)
        async def fence(db):pass
        context=SimpleNamespace(foundation_id=op.foundation_id,payload=dict(schedule_id=response.json()['id'],version=1,scheduled_for=due.isoformat()),fence=fence)
        async with factory() as db:
            schedule=await db.get(ReportDigestSchedule,UUID(response.json()['id']));schedule.next_run_at=due;await db.commit()
            assert (await run_digest(db,context))['queued']==1;await db.commit()
            outbox=await db.scalar(select(OutboxMessage));payload=json.loads(unseal(outbox.payload_cipher));payload['text']='Cached invented 99999 minutes';payload['subject']='Invented'
            assert await deliver_internal(db,outbox,payload)=='delivered';await db.flush()
            message=await db.scalar(select(Message).where(Message.source_outbox_id==outbox.id));assert '225 минут' in message.text and '99999' not in message.text and 'Волонтёров: 2' in message.text
            assert await deliver_internal(db,outbox,payload)=='delivered'
            assert await db.scalar(select(func.count()).select_from(Message).where(Message.source_outbox_id==outbox.id))==1
            await db.rollback()
    finally:
        for client in (facts['first'],facts['second'],owner,recipient):await client.aclose()

@pytest.mark.asyncio
@pytest.mark.parametrize('change,expected_state',[
    ('revoked','suppressed_report_revoked'),
    ('superseded','suppressed_report_stale'),
    ('removed','suppressed_report_removed'),
])
async def test_worker_persists_digest_suppression_as_terminal_without_state_overflow(env,monkeypatch,change,expected_state):
    from sqlalchemy import delete
    from app.core.models import Job
    from app.modules.notifications.models import NotificationDelivery,DeliveryAttempt
    from app.modules.reporting.models import ReportDigestRecipient
    from app.worker import main as worker
    app,factory=env;owner=await reporter(app,factory);recipient=await staff(app,factory,('reports.read',));op=await principal(owner,factory);rp=await principal(recipient,factory)
    try:
        await factor(factory,op.user_id);await factor(factory,rp.user_id)
        response=await save(owner,dict(expected_version=0,enabled=True,recipient_ids=[str(rp.user_id)],weekday=0,minute_of_day=540,timezone='Europe/Moscow'));assert response.status_code==200,response.text
        schedule_id=UUID(response.json()['id']);due=utcnow()-timedelta(seconds=1)
        async def fence(db):pass
        context=SimpleNamespace(foundation_id=op.foundation_id,payload=dict(schedule_id=str(schedule_id),version=1,scheduled_for=due.isoformat()),fence=fence)
        async with factory() as db:
            schedule=await db.get(ReportDigestSchedule,schedule_id);schedule.next_run_at=due;await db.commit()
            assert (await run_digest(db,context))['queued']==1;await db.commit()
            outbox=await db.scalar(select(OutboxMessage));outbox_id,job_id=outbox.id,outbox.job_id
            if change=='revoked':
                membership=await db.scalar(select(StaffMembership).where(StaffMembership.user_id==rp.user_id))
                grant=await db.scalar(select(PermissionGrant).where(PermissionGrant.membership_id==membership.id,PermissionGrant.permission=='reports.read'));grant.revoked_at=utcnow()
            elif change=='superseded':schedule.version+=1
            else:await db.execute(delete(ReportDigestRecipient).where(ReportDigestRecipient.schedule_id==schedule_id,ReportDigestRecipient.user_id==rp.user_id))
            await db.commit()
        # Exercise the actual worker → process_internal → journal/outbox writes.
        # The fixture's factory is restricted to the dedicated fictitious database.
        monkeypatch.setattr(worker,'SessionLocal',factory)
        assert await worker.run_once(['outbox.deliver']) is True
        async with factory() as db:
            saved=await db.get(OutboxMessage,outbox_id);job=await db.get(Job,job_id)
            assert saved.state==expected_state and len(saved.state)<=OutboxMessage.__table__.c.state.type.length
            assert job.state=='succeeded' and job.result=={'delivery':expected_state} and job.attempts==1
            delivery=await db.scalar(select(NotificationDelivery).where(NotificationDelivery.outbox_id==outbox_id))
            attempts=(await db.scalars(select(DeliveryAttempt).where(DeliveryAttempt.delivery_id==delivery.id))).all()
            assert delivery.state==expected_state and len(attempts)==1 and attempts[0].state==expected_state and attempts[0].completed_at
            assert not await db.scalar(select(Message.id).where(Message.source_outbox_id==outbox_id))
        assert await worker.run_once(['outbox.deliver']) is False
    finally:
        for client in (owner,recipient):await client.aclose()
