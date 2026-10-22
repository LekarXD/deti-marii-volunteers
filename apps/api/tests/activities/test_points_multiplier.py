import pytest
from sqlalchemy import select
from app.modules.activities.assignment_models import Assignment
from app.modules.activities.calendar_models import StaffingNeed
from .test_p07 import context,headers
from .test_p08 import seed
from .test_p09 import setup,invite_approve,user_headers


async def patch_needs(context,event,needs):
    current=(await context.client.get(f"/api/v1/event-occurrences/{event['id']}")).json()
    response=await context.client.patch(f"/api/v1/coord/event-occurrences/{event['id']}/staffing-needs",headers=headers(),json={'expected_version':current['version'],'staffing_needs':needs})
    assert response.status_code==200,response.text
    return response.json()['staffing_needs'][0]


@pytest.mark.asyncio
async def test_multiplier_keeps_invitation_valid_and_is_fixed_at_confirm(context):
    event,need,user1,_,_=await setup(context)
    assert need['points_multiplier']==1
    item=await invite_approve(context,need,user1)
    boosted=await patch_needs(context,event,[{'role_id':need['role_id'],'capacity_required':1,'points_multiplier':1.5}])
    assert boosted['points_multiplier']==1.5 and boosted['version']==need['version']
    invited=(await context.client.get(f"/api/v1/assignments/{item['id']}",headers=user_headers())).json()
    assert invited['points_multiplier']==1.5
    confirmed=await context.client.post(f"/api/v1/assignments/{item['id']}/confirm",headers=user_headers(),json={'expected_version':item['version']})
    assert confirmed.status_code==200,confirmed.text
    assert confirmed.json()['points_multiplier']==1.5
    plain=await patch_needs(context,event,[{'role_id':need['role_id'],'capacity_required':1,'points_multiplier':1}])
    assert plain['points_multiplier']==1 and plain['version']==need['version']
    after=(await context.client.get(f"/api/v1/assignments/{item['id']}",headers=user_headers())).json()
    assert after['points_multiplier']==1.5
    async with context.db() as db:assert (await db.get(Assignment,item['id'])).points_multiplier==1.5
    grown=await patch_needs(context,event,[{'role_id':need['role_id'],'capacity_required':2,'points_multiplier':1}])
    assert grown['version']==need['version']+1


@pytest.mark.asyncio
async def test_series_template_carries_multiplier_to_occurrences(context):
    created,body=await seed(context)
    assert created['staffing_needs'][0]['points_multiplier']==1
    boosted={**body,'staffing_needs':[{**body['staffing_needs'][0],'points_multiplier':1.5}],'expected_version':created['version']}
    preview=await context.client.post(f"/api/v1/coord/event-series/{created['id']}/preview-change",json=boosted,headers=headers())
    assert preview.status_code==200,preview.text
    applied=await context.client.post(f"/api/v1/coord/event-series/{created['id']}/apply-change",json={**boosted,'preview_hash':preview.json()['preview_hash']},headers=headers())
    assert applied.status_code==200,applied.text
    assert applied.json()['staffing_needs'][0]['points_multiplier']==1.5
    async with context.db() as db:
        needs=(await db.scalars(select(StaffingNeed).where(StaffingNeed.role_id==body['staffing_needs'][0]['role_id']))).all()
        assert needs and all(row.points_multiplier==1.5 and row.version==1 for row in needs)
    invalid=await context.client.post('/api/v1/coord/event-series',json={**body,'title':'Другое','start_date':'2028-01-04','staffing_needs':[{**body['staffing_needs'][0],'points_multiplier':2}]},headers=headers())
    assert invalid.status_code==422
