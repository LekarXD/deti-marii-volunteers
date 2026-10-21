"""Waiting CRM commands must not overwrite a completed or opted-out follow-up."""
import asyncio
from datetime import date
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.core.auth import authz_guard
from app.core.models import PermissionGrant
from app.modules.crm import service
from app.modules.crm.models import CrmVolunteer, FollowUpTask, FollowUpTaskEvent
from app.modules.crm.router import router
from app.modules.crm.schemas import CrmPreferenceCommand, TaskUpdateCommand
from tests.activities.test_p07 import context, headers
from tests.activities.test_lock_refresh import wait_for_row_lock

@pytest.mark.asyncio
@pytest.mark.parametrize('winner', ['completed', 'no_contact'])
async def test_waiting_task_update_cannot_undo_newer_decision(context, winner):
    context.client._transport.app.include_router(router)
    async with context.db() as db:
        db.add(PermissionGrant(membership_id=context.grants[0].membership_id, permission='crm.write', scope_type='foundation'))
        volunteer = CrmVolunteer(foundation_id=context.foundation.id, display_name='Вымышленный контакт')
        db.add(volunteer)
        await db.flush()
        task = FollowUpTask(foundation_id=context.foundation.id, volunteer_id=volunteer.id, assigned_user_id=context.principal.user_id, due_on=date(2026,10,22), title='Согласованный следующий шаг', source_type='manual', source_id=uuid4(), source_revision=1)
        db.add(task)
        await db.commit()
        await authz_guard(db, context.principal)
        await db.commit()
    pending = None
    try:
        async with context.db() as held:
            await held.scalar(select(CrmVolunteer).where(CrmVolunteer.id==volunteer.id).with_for_update())
            pending = asyncio.create_task(context.client.post(f'/api/v1/coord/follow-up-tasks/{task.id}', headers=headers(), json={'expected_version':1,'state':'open','title':'Устаревшее изменение','reason':'Старая вкладка'}))
            await wait_for_row_lock(held, pending)
            if winner == 'completed':
                await service.update_task(held, context.principal, task.id, TaskUpdateCommand(expected_version=1, state='done', reason='Задача выполнена'))
            else:
                await service.set_preference(held, context.principal, volunteer.id, CrmPreferenceCommand(expected_version=1, no_contact=True, reason='Не связываться'))
            await held.commit()
        response = await asyncio.wait_for(pending, 5)
        assert response.status_code == 409, response.text
        assert response.json()['code'] == 'version_conflict'
        async with context.db() as db:
            saved = await db.get(FollowUpTask, task.id)
            assert saved.version == 2 and saved.state == ('done' if winner=='completed' else 'cancelled')
            assert saved.title == 'Согласованный следующий шаг'
            assert (await db.get(CrmVolunteer, volunteer.id)).no_contact == (winner=='no_contact')
            events = (await db.scalars(select(FollowUpTaskEvent).where(FollowUpTaskEvent.task_id==task.id))).all()
            assert len(events) == 1
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
