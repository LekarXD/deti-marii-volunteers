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
            assert await deliver_internal(db,outbox,payload)=='suppressed_report_access_revoked'
            assert not await db.scalar(select(Message.id).where(Message.source_outbox_id==outbox.id))
            await db.rollback()
    finally:
        for client in (owner,recipient):await client.aclose()
