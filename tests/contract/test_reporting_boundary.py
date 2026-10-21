"""Independent reporting ACL/CAS checks using the domain's disposable PG fixture."""
import asyncio
from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.clock import utcnow
from app.core.models import Foundation, PermissionGrant, StaffMembership
from app.modules.participants.models import ParticipantGroup
from app.modules.reporting.models import ReportDraft
from app.modules.reporting.tests.test_reporting import (
    env, create, fixture_facts, group_reporter, principal,
)
from app.modules.applications.tests.test_applications import post


@pytest.mark.asyncio
async def test_report_foundation_and_group_boundaries_are_checked_before_write(env):
    app, factory = env
    facts = await fixture_facts(app, factory)
    scoped = await group_reporter(app, factory, facts['g1'].id)
    try:
        async with factory() as db:
            foreign = Foundation(name='Independent foreign synthetic foundation')
            db.add(foreign)
            await db.flush()
            foreign_group = ParticipantGroup(foundation_id=foreign.id, title='Foreign synthetic group')
            db.add(foreign_group)
            await db.commit()
        payload = dict(scope_type='group', scope_id=str(foreign_group.id),
                       period_from=facts['period_from'].isoformat(),
                       period_to=date.today().isoformat(), kind='grant', title='Synthetic forbidden report')
        # A global reporting grant applies only to its own foundation.
        assert (await post(facts['coord'], '/coord/reports', payload)).status_code == 404
        payload['scope_id'] = str(facts['g2'].id)
        assert (await post(scoped, '/coord/reports', payload)).status_code == 403
        payload.update(scope_type='foundation', scope_id=None)
        assert (await post(scoped, '/coord/reports', payload)).status_code == 403
        async with factory() as db:
            assert not (await db.scalars(select(ReportDraft))).all()
        # Directory/list endpoints do not broaden a group grant.
        assert (await scoped.get('/api/v1/coord/reports')).json() == []
        denied = await scoped.get('/api/v1/coord/reports/metrics', params={
            'period_from': facts['period_from'].isoformat(), 'period_to': date.today().isoformat(),
            'scope_type': 'foundation',
        })
        assert denied.status_code == 403
    finally:
        for client in (facts['first'], facts['second'], facts['coord'], scoped):
            await client.aclose()


@pytest.mark.asyncio
async def test_report_concurrent_section_edit_has_one_winner_and_revoked_receipt_denied(env):
    app, factory = env
    facts = await fixture_facts(app, factory)
    client = facts['coord']
    try:
        report = await create(client, facts['period_from'])
        section = next(row['key'] for row in report['sections'] if row['key'] != 'stories')
        route = f"/api/v1/coord/reports/{report['id']}/sections/{section}"
        keys = [uuid4().hex, uuid4().hex]
        async def edit(index):
            return await client.put(route, json={'expected_version': report['version'],
                                                 'text': f'Independent synthetic revision {index}'},
                                    headers={'Idempotency-Key': keys[index]})
        results = await asyncio.gather(edit(0), edit(1))
        assert sorted(result.status_code for result in results) == [200, 409]
        winner = next(i for i, result in enumerate(results) if result.status_code == 200)
        replay = await edit(winner)
        assert replay.status_code == 200 and replay.json() == results[winner].json()
        actor = await principal(client, factory)
        async with factory() as db:
            grants = (await db.scalars(select(PermissionGrant).join(StaffMembership).where(
                StaffMembership.user_id == actor.user_id,
                PermissionGrant.permission == 'reports.write',
            ))).all()
            assert grants
            for grant in grants:
                grant.revoked_at = utcnow()
            await db.commit()
        assert (await edit(winner)).status_code == 403
        assert (await client.get('/api/v1/coord/reports/' + report['id'])).status_code == 200
    finally:
        for identity in (facts['first'], facts['second'], client):
            await identity.aclose()
