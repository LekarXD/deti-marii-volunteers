"""P16 persists real PG rows and uses the actual shared worker/provider boundary."""
import json
import os
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID,uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import func,select,text
from sqlalchemy.ext.asyncio import async_sessionmaker,create_async_engine
from app.core.auth import resolve_principal
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.db import Base,get_db
from app.core.errors import install_error_handlers
from app.core.models import Foundation,Job,PermissionGrant,RegistrationSession,Session,StaffMembership,User
from app.core.model_loader import load_models
from app.integrations.ai.models import AIRun,AISettings
from app.integrations.ai.service import execute_run
from app.modules.knowledge import models as knowledge_models
from app.modules.simulator.models import EvaluationAppeal,RubricVersion,SimulationEvaluation,SimulationSession,SimulationSupportRequest,SimulationTurn,SimulatorScenarioVersion,SimulatorTestCaseRun,SimulatorTestRun
from app.modules.simulator.router import router
from app.modules.simulator.service import apply_ai_result
from app.worker.queue import claim,complete
from app.worker.registry import JobContext

URL=os.getenv('OPORA_SIMULATOR_TEST_DATABASE_URL')


def headers(actor='author',key=None):
    return {'Cookie':f'opora_session={actor}','Origin':'http://testserver','X-CSRF-Token':f'csrf-{actor}','Idempotency-Key':key or str(uuid4())}


def draft():
    return {'title':'Отказывается участвовать','character_name':'Миша','character_profile':'Вымышленный персонаж, живопись.','situation':'Отодвинул лист.','first_turn':'Я не буду рисовать.','hints':['Начните с контакта.'],
        'criteria':[{'key':'contact','title':'Контакт','guidance':'Замечает чувство и предлагает поддержку.','critical':False},{'key':'choice','title':'Выбор','guidance':'Предлагает приемлемый выбор.','critical':False}],
        'evaluation_cases':[{'key':'good','title':'Бережный ответ','turns':[{'speaker':'character','content':'Не буду.'},{'speaker':'volunteer','content':'Похоже, тебе тревожно. Можешь посидеть рядом или выбрать краски.'}],'expected_scores':{'contact':2,'choice':2}},
                            {'key':'bad','title':'Давление','turns':[{'speaker':'character','content':'Не буду.'},{'speaker':'volunteer','content':'Ты обязан рисовать, как все.'}],'expected_scores':{'contact':0,'choice':0}}]}


@pytest_asyncio.fixture
async def context(monkeypatch):
    if not URL:pytest.skip('Set OPORA_SIMULATOR_TEST_DATABASE_URL to isolated PostgreSQL')
    assert URL.rsplit('/',1)[-1]=='opora_simulator_test','Refusing a shared database'
    load_models()
    engine=create_async_engine(URL)
    async with engine.begin() as connection:
        await connection.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    async with factory() as db:
        foundation=Foundation(name='Invented simulator foundation');other=Foundation(name='Other invented foundation');db.add_all([foundation,other]);await db.flush()
        actors={}
        for name,permissions in [('author',['simulator.manage']),('reviewer',['simulator.review']),('learner',[]),('stranger',[])]:
            user=User(foundation_id=foundation.id,display_name=f'Invented {name}');db.add(user);await db.flush()
            if permissions:
                member=StaffMembership(foundation_id=foundation.id,user_id=user.id);db.add(member);await db.flush()
                for permission in permissions:db.add(PermissionGrant(membership_id=member.id,permission=permission,scope_type='foundation'))
            session=Session(foundation_id=foundation.id,user_id=user.id,token_hash=digest(name),csrf_hash=digest(f'csrf-{name}'),csrf_cipher='unused',expires_at=utcnow()+timedelta(hours=2),mfa_at=utcnow() if permissions else None)
            db.add(session);await db.flush();actors[name]=(user,session)
        registration=RegistrationSession(foundation_id=foundation.id,expires_at=utcnow()+timedelta(days=1));db.add(registration);await db.flush()
        db.add(Session(foundation_id=foundation.id,registration_id=registration.id,token_hash=digest('registration'),csrf_hash=digest('csrf-registration'),csrf_cipher='unused',expires_at=utcnow()+timedelta(hours=2)))
        db.add(AISettings(foundation_id=foundation.id,enabled=True,daily_tokens=100000,daily_requests=100,max_concurrent=2));await db.commit()
    app=FastAPI();install_error_handlers(app);app.include_router(router,prefix='/api/v1')
    async def override():
        async with factory() as db:
            try:yield db
            except BaseException:
                await db.rollback();raise
    app.dependency_overrides[get_db]=override
    monkeypatch.setenv('OPORA_AI_ENABLED','true');monkeypatch.setenv('OPORA_AI_BASE_URL','http://127.0.0.1:9999/v1');monkeypatch.setenv('OPORA_AI_API_KEY','invented-test-only');monkeypatch.setenv('OPORA_AI_MODEL','test-fixture-model')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
        yield SimpleNamespace(db=factory,client=client,actors=actors,foundation=foundation,other=other,monkeypatch=monkeypatch)
    await engine.dispose()


def provider_transport(invalid_evidence=False):
    def reply(request):
        payload=json.loads(request.content);data=json.loads(payload['messages'][1]['content'])
        if 'criteria' not in data:output={'content':'Я пока посижу рядом.'}
        else:
            volunteer=[turn for turn in data['turns'] if turn['speaker']=='volunteer'][-1]
            score=2 if 'Можешь' in volunteer['content'] else 0
            evidence=[{'turn_id':volunteer['id'],'quote':'Не было такой реплики.' if invalid_evidence else volunteer['content']}] if score else []
            output={'summary':'Разбор учебной ситуации.','criteria':[{'criterion_key':criterion['key'],'score':score,'explanation':'По фрагменту ответа.' if score else 'В ответе не наблюдается.','evidence':evidence,'suggestion':'Оставьте человеку выбор.'} for criterion in data['criteria']]}
        return httpx.Response(200,json={'id':'mock-provider-run','choices':[{'message':{'content':json.dumps(output,ensure_ascii=False)}}],'usage':{'total_tokens':100}})
    return httpx.MockTransport(reply)


async def drain(context,invalid_evidence=False,replay=False,transport=None):
    processed=[]
    while True:
        async with context.db() as db:
            job=await claim(db,kinds=['ai.generate'])
            if job is None:break
            await db.commit()
            job_context=JobContext(job.id,job.claim_token,job.foundation_id,dict(job.payload))
            result=await execute_run(db,job_context,transport=transport or provider_transport(invalid_evidence))
            run=await db.get(AIRun,UUID(job.payload['run_id']))
            await apply_ai_result(db,run,job_context)
            if replay:await apply_ai_result(db,run,job_context)
            await complete(db,job.id,job.claim_token,result);await db.commit();processed.append(str(run.id))
    return processed


async def reviewed_scenario(context):
    created=await context.client.post('/api/v1/coord/simulator/scenarios',headers=headers(),json=draft())
    assert created.status_code==200,created.text
    value=created.json()
    reviewed=await context.client.post(f"/api/v1/coord/simulator/scenarios/{value['id']}/review",headers=headers('reviewer'),json={'expected_version':value['version'],'decision':'approved','reason':'Проверены вымышленные данные, критерии и оба эталонных примера.'})
    assert reviewed.status_code==200,reviewed.text
    return reviewed.json()


async def published_scenario(context):
    value=await reviewed_scenario(context)
    tested=await context.client.post(f"/api/v1/coord/simulator/scenarios/{value['id']}/test",headers=headers(),json={'expected_version':value['version']})
    assert tested.status_code==200,tested.text
    assert tested.json()['state']=='running'
    assert len(await drain(context))==2
    result=(await context.client.get(f"/api/v1/coord/simulator/test-runs/{tested.json()['id']}",headers=headers())).json()
    assert result['state']=='succeeded',result
    published=await context.client.post(f"/api/v1/coord/simulator/scenarios/{value['id']}/publish",headers=headers(),json={'expected_version':value['version'],'review_id':value['reviews'][0]['id'],'test_run_id':tested.json()['id']})
    assert published.status_code==200,published.text
    return published.json()


async def start(context,scenario,actor='learner'):
    response=await context.client.post('/api/v1/simulation-sessions',headers=headers(actor),json={'scenario_id':scenario['id'],'publication_id':scenario['publication_id']})
    assert response.status_code==200,response.text
    return response.json()


@pytest.mark.asyncio
async def test_review_test_publish_scope_immutable_version_and_no_fixed_scores(context):
    value=await reviewed_scenario(context)
    assert (await context.client.get(f"/api/v1/simulator/scenarios/{value['id']}",headers=headers('learner'))).status_code==404
    forbidden=await context.client.post(f"/api/v1/coord/simulator/scenarios/{value['id']}/review",headers=headers(),json={'expected_version':1,'decision':'approved','reason':'Автор не специалист.'})
    assert forbidden.status_code==403
    tested=await context.client.post(f"/api/v1/coord/simulator/scenarios/{value['id']}/test",headers=headers(),json={'expected_version':1})
    assert tested.status_code==200,tested.text
    await drain(context)
    detail=(await context.client.get(f"/api/v1/coord/simulator/test-runs/{tested.json()['id']}",headers=headers())).json()
    assert detail['state']=='succeeded' and {case['state'] for case in detail['cases']}=={'passed'}
    actual=[case['result']['actual_scores']['contact'] for case in detail['cases']]
    assert sorted(actual)==[0,2]
    publish=await context.client.post(f"/api/v1/coord/simulator/scenarios/{value['id']}/publish",headers=headers(),json={'expected_version':1,'review_id':value['reviews'][0]['id'],'test_run_id':tested.json()['id']})
    assert publish.status_code==200,publish.text
    old_id=publish.json()['publication_id']
    updated=await context.client.patch(f"/api/v1/coord/simulator/scenarios/{value['id']}",headers=headers(),json={**draft(),'title':'Новый черновик','expected_version':2})
    assert updated.status_code==200
    async with context.db() as db:
        old=await db.get(SimulatorScenarioVersion,UUID(old_id));assert old.content['title']=='Отказывается участвовать'
        rubric=await db.get(RubricVersion,old.rubric_version_id);assert len(rubric.criteria)==2
    stale=await context.client.post(f"/api/v1/coord/simulator/scenarios/{value['id']}/publish",headers=headers(),json={'expected_version':3,'review_id':value['reviews'][0]['id'],'test_run_id':tested.json()['id']})
    assert stale.status_code==409


@pytest.mark.asyncio
async def test_private_dialogue_idempotency_pause_replay_evidence_and_appeal(context):
    scenario=await published_scenario(context);session=await start(context,scenario)
    assert session['turns'][0]['source']=='authored' and len(session['turns'])==1
    assert (await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('stranger'))).status_code==404
    key=str(uuid4());body={'expected_version':session['version'],'content':'Похоже, тебе тревожно. Можешь посидеть рядом или выбрать краски.'}
    sent=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/turns",headers=headers('learner',key),json=body)
    repeat=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/turns",headers=headers('learner',key),json=body)
    assert sent.status_code==repeat.status_code==200 and len(sent.json()['turns'])==2
    assert sent.json()['state']=='waiting_reply'
    paused=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/pause",headers=headers('learner'),json={'expected_version':sent.json()['version']})
    assert paused.status_code==200
    await drain(context,replay=True)
    fresh=(await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('learner'))).json()
    assert fresh['state']=='paused' and len(fresh['turns'])==3 and fresh['turns'][-1]['source']=='ai'
    resumed=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/resume",headers=headers('learner'),json={'expected_version':fresh['version']})
    finished=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/finish",headers=headers('learner'),json={'expected_version':resumed.json()['version']})
    assert finished.status_code==200,finished.text
    assert finished.json()['evaluation']['result'] is None
    await drain(context,replay=True)
    ready=(await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('learner'))).json()
    assert ready['evaluation']['state']=='ready'
    assert {criterion['score'] for criterion in ready['evaluation']['result']['criteria']}=={2}
    assert ready['evaluation']['model']=='test-fixture-model' and ready['evaluation']['prompt_version']=='simulator.assessment.v1'
    appealed=await context.client.post(f"/api/v1/simulation-evaluations/{ready['evaluation']['id']}/appeals",headers=headers('learner'),json={'text':'Прошу обсудить объяснение критерия.'})
    assert appealed.status_code==200,appealed.text
    appeal=appealed.json()['evaluation']['appeal']
    assert (await context.client.get('/api/v1/coord/simulator/appeals',headers=headers('learner'))).status_code==403
    reviewer_context=await context.client.get(f"/api/v1/coord/simulator/appeals/{appeal['id']}",headers=headers('reviewer'))
    assert reviewer_context.status_code==200 and reviewer_context.json()['attempt']['allowed_actions']==[]
    resolved=await context.client.post(f"/api/v1/coord/simulator/appeals/{appeal['id']}/resolve",headers=headers('reviewer'),json={'expected_version':appeal['version'],'response':'Обсудили фрагменты диалога. Это учебная обратная связь.','corrected_result':{**ready['evaluation']['result'],'summary':'Специалист уточнил объяснение по сохранённому диалогу.'}})
    assert resolved.status_code==200,resolved.text
    own=(await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('learner'))).json()
    assert own['evaluation']['appeal']['state']=='resolved'
    assert own['evaluation']['appeal']['corrected_result']['summary'].startswith('Специалист')
    assert own['evaluation']['result']['summary']=='Разбор учебной ситуации.'


@pytest.mark.asyncio
async def test_unconfigured_provider_persists_unavailable_without_fabricated_reply_or_score(context):
    scenario=await published_scenario(context);session=await start(context,scenario,actor='registration')
    context.monkeypatch.setenv('OPORA_AI_BASE_URL','')
    sent=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/turns",headers=headers('registration'),json={'expected_version':session['version'],'content':'Я посижу рядом.'})
    assert sent.status_code==200,sent.text
    paused=sent.json()
    assert paused['state']=='paused' and paused['provider_state']=='unavailable' and len(paused['turns'])==2
    assert [turn['source'] for turn in paused['turns']]==['authored','volunteer']
    finished=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/finish",headers=headers('registration'),json={'expected_version':paused['version']})
    assert finished.status_code==200,finished.text
    done=finished.json()
    assert done['evaluation']['state']=='unavailable' and done['evaluation']['result'] is None
    support=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/support-requests",headers=headers('registration'),json={'expected_version':done['version'],'text':'Хочу обсудить ситуацию со специалистом.'})
    assert support.status_code==200,support.text
    request=support.json()['support_requests'][0]
    assert request['state']=='open' and request['response'] is None
    queue=await context.client.get('/api/v1/coord/simulator/support-requests',headers=headers('reviewer'))
    assert queue.status_code==200 and queue.json()[0]['text']=='Хочу обсудить ситуацию со специалистом.'
    response=await context.client.post(f"/api/v1/coord/simulator/support-requests/{request['id']}/resolve",headers=headers('reviewer'),json={'expected_version':1,'response':'Можем обсудить спокойный ответ и паузу в занятии.'})
    assert response.status_code==200,response.text
    own=(await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('registration'))).json()
    assert own['support_requests'][0]['response'].startswith('Можем обсудить')
    value=await reviewed_scenario(context)
    test=await context.client.post(f"/api/v1/coord/simulator/scenarios/{value['id']}/test",headers=headers(),json={'expected_version':value['version']})
    assert test.status_code==200 and test.json()['state']=='unavailable'
    rejected=await context.client.post(f"/api/v1/coord/simulator/scenarios/{value['id']}/publish",headers=headers(),json={'expected_version':value['version'],'review_id':value['reviews'][0]['id'],'test_run_id':test.json()['id']})
    assert rejected.status_code==409 and rejected.json()['code']=='scenario_test_required'


@pytest.mark.asyncio
async def test_made_up_evidence_never_becomes_an_evaluation_result(context):
    scenario=await published_scenario(context);session=await start(context,scenario)
    sent=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/turns",headers=headers('learner'),json={'expected_version':session['version'],'content':'Можешь выбрать краски или посидеть рядом.'})
    await drain(context)
    current=(await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('learner'))).json()
    finished=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/finish",headers=headers('learner'),json={'expected_version':current['version']})
    assert finished.status_code==200
    await drain(context,invalid_evidence=True)
    result=(await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('learner'))).json()
    assert result['evaluation']['state']=='failed' and result['evaluation']['result'] is None
    assert result['provider_error']=='invalid_evidence'
    async with context.db() as db:
        evaluation=await db.get(SimulationEvaluation,UUID(result['evaluation']['id']))
        run=await db.get(AIRun,evaluation.ai_run_id)
        assert run.state=='succeeded' # provider JSON schema success is insufficient evidence
        assert evaluation.result is None


@pytest.mark.asyncio
async def test_concurrent_turns_stop_and_revoked_session_never_append_late_reply(context):
    scenario=await published_scenario(context);session=await start(context,scenario)
    import asyncio
    requests=[context.client.post(f"/api/v1/simulation-sessions/{session['id']}/turns",headers=headers('learner'),json={'expected_version':session['version'],'content':content}) for content in ('Первый ответ.','Конкурирующий ответ.')]
    results=await asyncio.gather(*requests)
    assert sorted(response.status_code for response in results)==[200,409]
    current=next(response.json() for response in results if response.status_code==200)
    stopped=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/stop",headers=headers('learner'),json={'expected_version':current['version']})
    assert stopped.status_code==200
    await drain(context,replay=True)
    state=(await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('learner'))).json()
    assert state['state']=='stopped' and len(state['turns'])==2 and state['evaluation'] is None
    second=await start(context,scenario)
    pending=await context.client.post(f"/api/v1/simulation-sessions/{second['id']}/turns",headers=headers('learner'),json={'expected_version':second['version'],'content':'Я рядом.'})
    assert pending.status_code==200
    async with context.db() as db:
        row=await db.get(Session,context.actors['learner'][1].id);row.revoked_at=utcnow();await db.commit()
    await drain(context)
    assert (await context.client.get(f"/api/v1/simulation-sessions/{second['id']}",headers=headers('learner'))).status_code==401
    async with context.db() as db:
        turns=(await db.scalars(select(SimulationTurn).where(SimulationTurn.session_id==UUID(second['id'])))).all()
        assert len(turns)==2 and not any(turn.source=='ai' for turn in turns)


@pytest.mark.asyncio
async def test_latest_review_controls_publication_and_withdrawn_history_stays_private(context):
    value=await reviewed_scenario(context)
    later=await context.client.post(f"/api/v1/coord/simulator/scenarios/{value['id']}/review",headers=headers('reviewer'),json={'expected_version':1,'decision':'changes_requested','reason':'Нужно уточнить эталонный пример.'})
    assert later.status_code==200
    blocked=await context.client.post(f"/api/v1/coord/simulator/scenarios/{value['id']}/test",headers=headers(),json={'expected_version':1})
    assert blocked.status_code==409 and blocked.json()['code']=='dataset_review_required'
    scenario=await published_scenario(context);session=await start(context,scenario)
    assert (await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('reviewer'))).status_code==404
    withdrawn=await context.client.post(f"/api/v1/coord/simulator/scenarios/{scenario['id']}/withdraw",headers=headers(),json={'expected_version':scenario['version']})
    assert withdrawn.status_code==200
    assert (await context.client.get(f"/api/v1/simulator/scenarios/{scenario['id']}",headers=headers('learner'))).status_code==404
    assert (await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('learner'))).status_code==200
    assert (await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('stranger'))).status_code==404
    new=await context.client.post('/api/v1/simulation-sessions',headers=headers('learner'),json={'scenario_id':scenario['id']})
    assert new.status_code==404


@pytest.mark.asyncio
async def test_provider_timeout_and_budget_pause_without_extra_reply(context):
    scenario=await published_scenario(context);session=await start(context,scenario)
    sent=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/turns",headers=headers('learner'),json={'expected_version':session['version'],'content':'Можешь посидеть рядом.'})
    assert sent.status_code==200
    def timeout(request):
        raise httpx.ReadTimeout('Injected provider timeout',request=request)
    await drain(context,transport=httpx.MockTransport(timeout))
    state=(await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('learner'))).json()
    assert state['state']=='paused' and state['provider_state']=='unknown' and len(state['turns'])==2
    assert 'retry-reply' in state['allowed_actions']
    assert await drain(context)==[] # ambiguous provider request never retried automatically
    async with context.db() as db:
        settings=await db.get(AISettings,context.foundation.id);settings.daily_requests=1;await db.commit()
    second=await start(context,scenario)
    denied=await context.client.post(f"/api/v1/simulation-sessions/{second['id']}/turns",headers=headers('learner'),json={'expected_version':second['version'],'content':'Я рядом.'})
    assert denied.status_code==200
    await drain(context)
    result=(await context.client.get(f"/api/v1/simulation-sessions/{second['id']}",headers=headers('learner'))).json()
    assert result['state']=='paused' and result['provider_state']=='budget_exceeded'
    assert len(result['turns'])==2 and result['evaluation'] is None


@pytest.mark.asyncio
async def test_retry_evaluation_only_reruns_a_failed_evaluation(context):
    scenario=await published_scenario(context);session=await start(context,scenario)
    sent=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/turns",headers=headers('learner'),json={'expected_version':session['version'],'content':'Можешь выбрать краски или посидеть рядом.'})
    assert sent.status_code==200
    await drain(context)
    current=(await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('learner'))).json()
    finished=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/finish",headers=headers('learner'),json={'expected_version':current['version']})
    assert finished.status_code==200
    await drain(context,invalid_evidence=True)
    failed=(await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('learner'))).json()
    assert failed['evaluation']['state']=='failed' and 'retry-evaluation' in failed['allowed_actions']
    retried=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/retry-evaluation",headers=headers('learner'),json={'expected_version':failed['version']})
    assert retried.status_code==200,retried.text
    await drain(context)
    ready=(await context.client.get(f"/api/v1/simulation-sessions/{session['id']}",headers=headers('learner'))).json()
    assert ready['evaluation']['state']=='ready' and ready['evaluation']['version']==2 and 'retry-evaluation' not in ready['allowed_actions']
    async with context.db() as db:
        before=(await db.scalar(select(func.count()).select_from(SimulationEvaluation)),await db.scalar(select(func.count()).select_from(AIRun)))
    rerolled=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/retry-evaluation",headers=headers('learner'),json={'expected_version':ready['version']})
    assert rerolled.status_code==409 and rerolled.json()['code']=='simulation_state_conflict'
    async with context.db() as db:
        assert (await db.scalar(select(func.count()).select_from(SimulationEvaluation)),await db.scalar(select(func.count()).select_from(AIRun)))==before


@pytest.mark.asyncio
async def test_support_queue_keeps_open_requests_ahead_of_resolved_history(context):
    scenario=await published_scenario(context);session=await start(context,scenario)
    support=await context.client.post(f"/api/v1/simulation-sessions/{session['id']}/support-requests",headers=headers('learner'),json={'expected_version':session['version'],'text':'Хочу обсудить ситуацию со специалистом.'})
    assert support.status_code==200,support.text
    async with context.db() as db:
        db.add_all([SimulationSupportRequest(foundation_id=context.foundation.id,session_id=UUID(session['id']),text=f'Решено {index}',state='resolved',response='Ответили.',created_at=utcnow()+timedelta(minutes=1,seconds=index)) for index in range(101)])
        await db.commit()
    queue=(await context.client.get('/api/v1/coord/simulator/support-requests',headers=headers('reviewer'))).json()
    assert len(queue)==100 and queue[0]['id']==support.json()['support_requests'][0]['id']
