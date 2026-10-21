"""P20 actual profile authority + durable AI gateway, controlled HTTP only."""
import json
from uuid import UUID,uuid4
import httpx
import pytest
from sqlalchemy import select,func
from app.integrations.ai.models import AIRun
from app.modules.profile.router import router as profile_router
from app.modules.profile.models import ProfileChangeSuggestion
from app.integrations.ai.profile import materialize_profile_suggestion
from test_knowledge import setup,post,process_ai,configured

async def save(client,version,about='Люблю рисовать',optin=True):
    response=await client.put('/api/v1/me/profile',json={'expected_version':version,'display_name':'Profile producer fixture','about':about,'ai_about':optin,'ai_skills':False,'ai_interests':False,'tags':[]},headers={'Idempotency-Key':str(uuid4())})
    assert response.status_code==200,response.text
    return response.json()

async def decide(client,suggestion_id,version,decision):
    response=await post(client,f'/me/profile/suggestions/{suggestion_id}/decision',{'expected_version':version,'decision':decision})
    assert response.status_code==200,response.text
    return response.json()

@pytest.mark.asyncio
async def test_profile_request_proposal_accept_revert_reject_and_replay(setup,monkeypatch):
    client,factory,foundation=setup
    client._transport.app.include_router(profile_router)
    configured(monkeypatch)
    await save(client,0)
    requested=await post(client,'/me/profile/ai-runs',{'expected_profile_version':1},key='profile-start')
    assert requested.status_code==200,requested.text
    assert requested.json()['state']=='queued' and requested.json()['suggestion_id'] is None
    sent=[]
    async def provider(request):
        data=json.loads(request.content);sent.append(data)
        fields=json.loads(data['messages'][1]['content'])['fields']
        assert fields=={'about':'Люблю рисовать'}
        assert 'contacts' not in data['messages'][1]['content'] and 'private_notes' not in data['messages'][1]['content']
        return httpx.Response(200,json={'id':'controlled-profile','choices':[{'message':{'content':json.dumps({'about':'Мне нравится рисование.','skills':['DO NOT MATERIALIZE OPTED OUT'],'interests':[]})}}],'usage':{'total_tokens':30}})
    run_id=await process_ai(factory,foundation,httpx.MockTransport(provider))
    status=(await client.get(f'/api/v1/me/profile/ai-runs/{run_id}')).json()
    assert status['state']=='succeeded' and status['suggestion_id']
    proposal_id=status['suggestion_id']
    proposals=(await client.get('/api/v1/me/profile/suggestions')).json()
    assert len(proposals)==1 and proposals[0]['patch']=={'about':'Мне нравится рисование.'}
    assert proposals[0]['source_refs']==[{'source_id':str((await client.get('/api/v1/me/profile')).json()['user_id']),'version':1,'fragment':'public_profile'}]
    assert (await client.get('/api/v1/me/profile')).json()['about']=='Люблю рисовать'
    assert (await client.get(f'/api/v1/ai/runs/{run_id}')).json()['output'] is None
    await decide(client,proposal_id,1,'accept')
    assert (await client.get('/api/v1/me/profile')).json()['version']==2
    replay=await post(client,'/me/profile/ai-runs',{'expected_profile_version':1},key='profile-start')
    assert replay.json()['suggestion_id']==proposal_id
    await decide(client,proposal_id,2,'revert')
    assert (await client.get('/api/v1/me/profile')).json()['about']=='Люблю рисовать'
    second=await post(client,'/me/profile/ai-runs',{'expected_profile_version':3})
    assert second.status_code==200
    second_run=await process_ai(factory,foundation,httpx.MockTransport(provider))
    second_status=(await client.get(f'/api/v1/me/profile/ai-runs/{second_run}')).json()
    rejected=await decide(client,second_status['suggestion_id'],3,'reject')
    assert rejected['state']=='rejected'
    class Fence:
        async def fence(self,db):pass
    async with factory() as db:
        run=await db.get(AIRun,second_run)
        replayed=await materialize_profile_suggestion(db,run,Fence())
        assert replayed.state=='rejected'
        await db.commit()
        assert await db.scalar(select(func.count()).select_from(ProfileChangeSuggestion).where(ProfileChangeSuggestion.foundation_id==foundation))==2
    assert len(sent)==2
    client.cookies.set('opora_session','two'+str(foundation))
    assert (await client.get(f'/api/v1/me/profile/ai-runs/{run_id}')).status_code==404
    assert (await post(client,'/me/profile/ai-runs',{'expected_profile_version':3})).status_code==403

@pytest.mark.asyncio
async def test_profile_version_optin_rechecked_before_io_and_after_provider(setup,monkeypatch):
    client,factory,foundation=setup
    client._transport.app.include_router(profile_router)
    configured(monkeypatch)
    await save(client,0)
    queued=(await post(client,'/me/profile/ai-runs',{'expected_profile_version':1},key='queued-old')).json()
    await save(client,1,about='Changed source')
    def forbidden(request):raise AssertionError('stale source must not reach provider')
    old_id=await process_ai(factory,foundation,httpx.MockTransport(forbidden))
    assert old_id==UUID(queued['id'])
    stale=(await client.get(f'/api/v1/me/profile/ai-runs/{old_id}')).json()
    assert stale['state']=='sources_changed' and stale['suggestion_id'] is None
    replay=await post(client,'/me/profile/ai-runs',{'expected_profile_version':1},key='queued-old')
    assert replay.json()['state']=='sources_changed'
    await post(client,'/me/profile/ai-runs',{'expected_profile_version':2})
    async def changed_during_call(request):
        await save(client,2,about='Final manual wording',optin=False)
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({'about':'OUTDATED OUTPUT','skills':[],'interests':[]})}}],'usage':{'total_tokens':20}})
    new_id=await process_ai(factory,foundation,httpx.MockTransport(changed_during_call))
    fresh=(await client.get(f'/api/v1/me/profile/ai-runs/{new_id}')).json()
    assert fresh['state']=='sources_changed' and fresh['suggestion_id'] is None
    assert (await client.get('/api/v1/me/profile')).json()['about']=='Final manual wording'
    assert (await client.get('/api/v1/me/profile/suggestions')).json()==[]
    async with factory() as db:
        run=await db.get(AIRun,new_id)
        assert run.output is None and run.charged_tokens==20
    denied=await post(client,'/me/profile/ai-runs',{'expected_profile_version':3})
    assert denied.status_code==422 and denied.json()['code']=='profile_ai_optin_required'
