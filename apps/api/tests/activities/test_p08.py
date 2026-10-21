from datetime import date, datetime, time, timezone
from uuid import UUID
import asyncio
import pytest
from sqlalchemy import select
from app.modules.activities.calendar_models import EventOccurrence, EventSeries, OccurrenceOverride
from app.modules.activities.recurrence import dates_in_range, local_interval
from app.modules.activities.calendar_schemas import RecurrenceRule
from app.core.models import PermissionGrant
from app.modules.participants.models import ParticipantGroup
from .test_p07 import context, headers, post_role


def test_recurrence_leap_monthly_biweekly_dst():
    assert list(dates_in_range(date(2028,1,31),RecurrenceRule(frequency='monthly'),date(2028,1,1),date(2028,5,1)))==[date(2028,1,31),date(2028,3,31)]
    assert list(dates_in_range(date(2028,2,29),RecurrenceRule(frequency='monthly'),date(2028,2,1),date(2028,4,30)))==[date(2028,2,29),date(2028,3,29),date(2028,4,29)]
    assert list(dates_in_range(date(2028,1,3),RecurrenceRule(frequency='biweekly',weekdays=[0,2]),date(2028,1,1),date(2028,1,20)))==[date(2028,1,3),date(2028,1,5),date(2028,1,17),date(2028,1,19)]
    assert local_interval(date(2028,3,26),time(2,30),'Europe/Berlin',60) is None
    before=local_interval(date(2028,3,19),time(10),'Europe/Berlin',60)
    after=local_interval(date(2028,4,2),time(10),'Europe/Berlin',60)
    assert before[0].hour==9 and after[0].hour==8
    fold=local_interval(date(2028,10,29),time(2,30),'Europe/Berlin',60)
    assert fold[0]==datetime(2028,10,29,0,30,tzinfo=timezone.utc)


async def seed(context,frequency='weekly',group_id=None):
    async with context.db() as db:
        member_id=context.grants[0].membership_id
        db.add_all([PermissionGrant(membership_id=member_id,permission=p,scope_type='foundation') for p in ['schedule.read','schedule.manage']]);await db.commit()
    role=await post_role(context)
    body={'title':'Творческая встреча','program':'Мастерская','start_date':'2028-01-03','start_time':'14:00','duration_minutes':120,'timezone':'Europe/Moscow','location':'Мастерская','recurrence':{'frequency':frequency,'weekdays':[0] if frequency=='weekly' else []},'staffing_needs':[{'role_id':role['id'],'capacity_required':2}],'group_id':str(group_id) if group_id else None}
    response=await context.client.post('/api/v1/coord/event-series',json=body,headers=headers())
    assert response.status_code==200,response.text
    return response.json(),body


@pytest.mark.asyncio
async def test_arbitrary_future_range_multiple_roles_and_stable_override(context):
    created,body=await seed(context)
    # This is years beyond six-week/six-month initial materialization.
    response=await context.client.get('/api/v1/event-occurrences?from=2030-01-01&to=2030-01-31')
    assert response.status_code==200,response.text
    assert len(response.json()['items'])==4
    response=await context.client.get('/api/v1/event-occurrences?from=2028-01-01&to=2028-01-31')
    items=sorted(response.json()['items'],key=lambda r:r['starts_at'])
    first,second=items[:2]
    patched=await context.client.patch(f"/api/v1/coord/event-occurrences/{first['id']}",json={'expected_version':1,'title':'Перенесённая встреча','starts_at':'2028-01-04T11:00:00Z','ends_at':'2028-01-04T13:00:00Z','location':'Другая мастерская','group_id':None},headers=headers())
    assert patched.status_code==200,patched.text
    assert patched.json()['id']==first['id'] and patched.json()['origin_local_date']=='2028-01-03'
    fresh=await context.client.get(f"/api/v1/event-occurrences/{second['id']}")
    assert fresh.json()['starts_at']==second['starts_at']
    next_role=await post_role(context,'Фотограф')
    staffing=await context.client.patch(f"/api/v1/coord/event-occurrences/{first['id']}/staffing-needs",json={'expected_version':2,'staffing_needs':[{'role_id':first['staffing_needs'][0]['role_id'],'capacity_required':3},{'role_id':next_role['id'],'capacity_required':1}]},headers=headers())
    assert staffing.status_code==200,staffing.text
    assert sorted(row['required'] for row in staffing.json()['staffing_needs'])==[1,3]
    assert all(row['confirmed']==0 and row['invited']==0 for row in staffing.json()['staffing_needs'])
    changed={**body,'title':'Название всей серии','expected_version':1}
    preview=await context.client.post(f"/api/v1/coord/event-series/{created['id']}/preview-change",json=changed,headers=headers())
    assert preview.status_code==200,preview.text
    assert first['id'] in preview.json()['retained_override_ids']
    applied=await context.client.post(f"/api/v1/coord/event-series/{created['id']}/apply-change",json={**changed,'preview_hash':preview.json()['preview_hash']},headers=headers())
    assert applied.status_code==200,applied.text
    retained=(await context.client.get(f"/api/v1/event-occurrences/{first['id']}")).json()
    assert retained['title']=='Перенесённая встреча' and len(retained['staffing_needs'])==2
    neighbor=(await context.client.get(f"/api/v1/event-occurrences/{second['id']}")).json()
    assert neighbor['title']=='Название всей серии'


@pytest.mark.asyncio
async def test_stale_preview_and_cancel_restore_preserve_manual_exceptions(context):
    created,body=await seed(context)
    items=(await context.client.get('/api/v1/event-occurrences?from=2028-01-01&to=2028-01-31')).json()['items']
    first=items[0]
    changed={**body,'start_time':'15:00','expected_version':1}
    preview=(await context.client.post(f"/api/v1/coord/event-series/{created['id']}/preview-change",json=changed,headers=headers())).json()
    cancelled=await context.client.post(f"/api/v1/coord/event-occurrences/{first['id']}/cancel",json={'expected_version':1},headers=headers())
    assert cancelled.status_code==200
    stale=await context.client.post(f"/api/v1/coord/event-series/{created['id']}/apply-change",json={**changed,'preview_hash':preview['preview_hash']},headers=headers())
    assert stale.status_code==409,stale.text
    assert (await context.client.post(f"/api/v1/coord/event-series/{created['id']}/cancel",json={'expected_version':1},headers=headers())).status_code==200
    restored=await context.client.post(f"/api/v1/coord/event-series/{created['id']}/restore",json={'expected_version':2},headers=headers())
    assert restored.status_code==200,restored.text
    manual=(await context.client.get(f"/api/v1/event-occurrences/{first['id']}")).json()
    assert manual['status']=='cancelled'
    self_headers={'Origin':'http://testserver','X-CSRF-Token':'self-csrf','Idempotency-Key':str(UUID(int=9))}
    context.client.cookies.set('opora_session','self')
    assert (await context.client.get('/api/v1/event-occurrences?from=2028-01-01&to=2028-01-31')).status_code==403
    assert (await context.client.get(f"/api/v1/event-occurrences/{first['id']}")).status_code==403


@pytest.mark.asyncio
async def test_group_scope_and_overlaps_rejected(context):
    async with context.db() as db:
        group=ParticipantGroup(foundation_id=context.foundation.id,title='Группа')
        db.add(group);await db.commit()
    created,body=await seed(context,group_id=group.id)
    overlap=await context.client.post('/api/v1/coord/event-series',json={**body,'title':'В то же время'},headers=headers())
    assert overlap.status_code==409,overlap.text
    async with context.db() as db:
        foreign=ParticipantGroup(foundation_id=context.other.id,title='Другая группа')
        db.add(foreign);await db.commit()
    bad=await context.client.post('/api/v1/coord/event-series',json={**body,'group_id':str(foreign.id),'start_date':'2028-01-04'},headers=headers())
    assert bad.status_code==422,bad.text


@pytest.mark.asyncio
async def test_local_edit_and_staffing_are_atomic_and_dst_gap_is_rejected(context):
    created,body=await seed(context)
    first=(await context.client.get('/api/v1/event-occurrences?from=2028-01-01&to=2028-01-31')).json()['items'][0]
    missing_role='00000000-0000-0000-0000-000000000099'
    mutation={'expected_version':1,'title':'Не должно сохраниться','group_id':None,'location':'Другое место','local_date':'2028-01-05','local_time':'16:00','timezone':'Europe/Moscow','duration_minutes':90,'staffing_needs':[{'role_id':missing_role,'capacity_required':1}]}
    failed=await context.client.patch(f"/api/v1/coord/event-occurrences/{first['id']}",json=mutation,headers=headers())
    assert failed.status_code==422,failed.text
    unchanged=(await context.client.get(f"/api/v1/event-occurrences/{first['id']}")).json()
    assert unchanged['version']==1 and unchanged['starts_at']==first['starts_at'] and not unchanged['has_override']
    gap=await context.client.patch(f"/api/v1/coord/event-occurrences/{first['id']}",json={**mutation,'local_date':'2028-03-26','local_time':'02:30','timezone':'Europe/Berlin','staffing_needs':[]},headers=headers())
    assert gap.status_code==422 and gap.json()['code']=='nonexistent_local_time'
    successful=await context.client.patch(f"/api/v1/coord/event-occurrences/{first['id']}",json={**mutation,'staffing_needs':[{'role_id':first['staffing_needs'][0]['role_id'],'capacity_required':3}]},headers=headers())
    assert successful.status_code==200,successful.text
    saved=successful.json()
    assert saved['version']==2 and saved['starts_at']=='2028-01-05T13:00:00Z' and saved['staffing_needs'][0]['required']==3
    assert saved['origin_local_date']==first['origin_local_date']
