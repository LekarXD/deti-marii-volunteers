"""Concurrent real HTTP transfer must serialize with source-bound notice delivery."""
import asyncio
import json
from uuid import UUID
import pytest
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.crypto import seal, unseal
from app.core.models import MfaFactor, OutboxMessage
from app.modules.applications.tests.test_applications import staff, post
from app.modules.dobro.tests.test_dobro import world, link_fixture, fact_fixture, enroll, period, mark_body
from app.modules.dobro import notifications
from app.modules.dobro.jobs import run_reminders
from app.modules.notifications.delivery import process_internal
from app.modules.messaging.models import Message
from app.worker.queue import claim, complete
from app.worker.registry import JobContext


@pytest.mark.asyncio
async def test_different_coordinator_transfer_waits_for_current_reminder_delivery(world, monkeypatch):
    opportunity, activity = await link_fixture(world)
    await fact_fixture(world, opportunity, '2026-09-06', 60)
    await enroll(world, activity)
    async with world[1]() as db:
        db.add(MfaFactor(user_id=world[4].user_id, secret_cipher=seal('JBSWY3DPEHPK3PXP'), confirmed_at=utcnow()))
        await db.commit()
    settings = (await world[2].get('/api/v1/fund/integrations/dobro/settings')).json()
    body = {name:settings[name] for name in ('organization_url','registration_url','verified','monthly_day','hard_deadline_days','risk_days','rules_confirmed','reminder_template')}
    body.update(expected_version=0, reminders_enabled=True, monthly_day=1)
    response = await world[2].put('/api/v1/fund/integrations/dobro/settings', json=body, headers={'Idempotency-Key':'audit-enable-reminder'})
    assert response.status_code == 200, response.text
    async with world[1]() as db:
        job = await claim(db, ['dobro.reminders.scan'])
        result = await run_reminders(db, JobContext(job.id, job.claim_token, job.foundation_id, job.payload))
        assert result['queued'] == 1
        await complete(db, job.id, job.claim_token, result)
        await db.commit()
    # A separate staff identity avoids the sender's authorization lock masking
    # the missing domain lock. Authentication/CSRF remain ordinary HTTP.
    other = await staff(world[0], world[1], ('hours.review',))
    view = await period(world, '2026-09')
    mark = mark_body(view, view['groups'][0]['rows'][0], activity['id'])
    observed, release = asyncio.Event(), asyncio.Event()
    original = notifications.transfer_period
    async def pause_after_projection(*args, **kwargs):
        result = await original(*args, **kwargs)
        observed.set()
        await release.wait()
        return result
    monkeypatch.setattr(notifications, 'transfer_period', pause_after_projection)
    async def deliver():
        async with world[1]() as db:
            job = await claim(db, ['outbox.deliver'])
            outbox = await db.get(OutboxMessage, UUID(job.payload['outbox_id']))
            state = await process_internal(db, job, outbox, json.loads(unseal(outbox.payload_cipher)))
            await complete(db, job.id, job.claim_token, {'state':state})
            await db.commit()
            return state
    delivery = asyncio.create_task(deliver())
    marking = None
    try:
        await asyncio.wait_for(observed.wait(), 5)
        marking = asyncio.create_task(post(other, '/fund/integrations/dobro/transfers/mark-entered', mark, 'audit-other-coordinator'))
        done, _ = await asyncio.wait({marking}, timeout=0.25)
        assert not done, 'Transfer committed while delivery retained a stale hours-due projection'
    finally:
        release.set()
        assert await asyncio.wait_for(delivery, 5) == 'delivered'
        if marking:
            response = await asyncio.wait_for(marking, 5)
            assert response.status_code == 200, response.text
            assert response.json()['groups'][0]['rows'][0]['hours_due'] == 0
        async with world[1]() as db:
            text = await db.scalar(select(Message.text))
            assert 'К переносу: 1 ч' in text
        await other.aclose()
