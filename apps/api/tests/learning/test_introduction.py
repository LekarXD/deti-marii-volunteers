"""Real PostgreSQL tests; never run destructive setup on a shared database."""
import os
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.db import Base, get_db
from app.core.errors import install_error_handlers
from app.core.crypto import digest
from app.core.models import Foundation, RegistrationSession, Session
from app.modules.learning.models import LearningAssignment, LearningRelease, LearningTrack
from app.modules.learning.router import router
from app.modules.learning.seed import seed_introduction


@pytest_asyncio.fixture
async def setup():
    url = os.getenv('OPORA_LEARNING_TEST_DATABASE_URL')
    if not url:
        pytest.skip('Set OPORA_LEARNING_TEST_DATABASE_URL to an isolated PostgreSQL database')
    assert url.rsplit('/', 1)[-1] == 'opora_learning_test'
    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    foundation_id = uuid4()
    async with factory() as db:
        db.add(Foundation(id=foundation_id, name='Learning integration fixture'))
        await db.flush()
        await seed_introduction(db, foundation_id)
        for token in ['one', 'two']:
            registration = RegistrationSession(foundation_id=foundation_id, expires_at=datetime.now(timezone.utc)+timedelta(days=1))
            db.add(registration)
            await db.flush()
            db.add(Session(foundation_id=foundation_id, registration_id=registration.id, token_hash=digest(token+str(foundation_id)), csrf_hash=digest('csrf'), csrf_cipher='fixture', expires_at=datetime.now(timezone.utc)+timedelta(days=1)))
        await db.commit()
    app = FastAPI()
    app.include_router(router)
    install_error_handlers(app)
    async def dependency():
        async with factory() as db:
            try:
                yield db
            except BaseException:
                await db.rollback()
                raise
    app.dependency_overrides[get_db] = dependency
    async with AsyncClient(transport=ASGITransport(app), base_url='http://testserver', headers={'Origin':'http://testserver','X-CSRF-Token':'csrf'}, cookies={'opora_session':'one'+str(foundation_id)}) as client:
        yield client, factory, foundation_id
    await engine.dispose()


async def post(client, path, body=None, key=None):
    return await client.post('/api/v1'+path, json=body or {}, headers={'Idempotency-Key':key or str(uuid4())})


@pytest.mark.asyncio
async def test_server_score_reload_repeat_acl_and_version_history(setup):
    client, factory, foundation_id = setup
    prep = (await client.get('/api/v1/me/preparation')).json()
    assert prep['booking_requires_introduction'] is False
    assignment = prep['assignments'][0]
    assert len(assignment['lessons']) == 4
    version_id = assignment['assessment_version_id']
    started = await post(client, f'/assessments/{version_id}/attempts', key='start')
    assert started.status_code == 200, started.text
    attempt = started.json()
    assert len(attempt['questions']) == 10 and attempt['score'] is None
    assert all(set(q) == {'id','prompt','options'} for q in attempt['questions'])
    replay = await post(client, f'/assessments/{version_id}/attempts', key='start')
    assert replay.json()['id'] == attempt['id']
    assert (await post(client, f"/assessment-attempts/{attempt['id']}/submit", {'score':10})).status_code == 422
    assert (await post(client, f"/assessment-attempts/{attempt['id']}/submit")).status_code == 422
    for index, question in enumerate(attempt['questions']):
        # Deliberately wrong on every question: zero is completion, never failure.
        correct = [0,1,1,0,1,0,1,1,0,1][index]
        selected = 1-correct
        response = await post(client, f"/assessment-attempts/{attempt['id']}/answers", {'question_id':question['id'],'selected_option':selected})
        assert response.status_code == 200, response.text
        assert response.json()['correct'] is False and response.json()['explanation']
    reload = (await client.get(f"/api/v1/assessment-attempts/{attempt['id']}/result")).json()
    assert len(reload['answers']) == 10 and reload['score'] is None
    submitted = (await post(client, f"/assessment-attempts/{attempt['id']}/submit")).json()
    assert submitted['score'] == 0 and submitted['state'] == 'submitted'
    for lesson in assignment['lessons']:
        detail = (await client.get(f"/api/v1/learning/lessons/{lesson['id']}")).json()
        assert 'correct_option' not in str(detail)
        for block in detail['blocks']:
            if block['type'] == 'quiz':
                assert all(set(q) == {'q','o'} for q in block['items'])
                feedback = await post(client, f"/learning/lessons/{lesson['id']}/blocks/{block['id']}/answer", {'question_index':0,'selected_option':0})
                assert feedback.status_code == 200 and feedback.json()['explanation']
        assert (await post(client, f"/learning/progress/{lesson['id']}/complete", {'assignment_id':assignment['id']})).status_code == 200
    await post(client, '/policy-acknowledgements', {'assignment_id':assignment['id']})
    assert (await client.get('/api/v1/me/preparation')).json()['introduction_completed'] is True
    repeat = (await post(client, f'/assessments/{version_id}/attempts')).json()
    assert repeat['id'] != attempt['id'] and repeat['score'] is None and repeat['answers'] == []
    assert (await client.get(f"/api/v1/assessment-attempts/{attempt['id']}/result")).json()['score'] == 0
    # A new release requires its own work and preserves earlier completion/history.
    async with factory() as db:
        track = await db.scalar(select(LearningTrack).where(LearningTrack.foundation_id == foundation_id))
        old = await db.get(LearningRelease, track.current_release_id)
        new = LearningRelease(track_id=track.id, foundation_id=foundation_id, number=2, title=old.title, intro='Second immutable version', lesson_version_ids=old.lesson_version_ids, assessment_version_id=old.assessment_version_id, reacknowledgement_required=True)
        db.add(new)
        await db.flush()
        track.current_release_id = new.id
        await db.commit()
    reloaded = (await client.get('/api/v1/me/preparation')).json()
    assert len(reloaded['assignments']) == 2 and reloaded['introduction_completed'] is True
    assert sum(item['completed'] for item in reloaded['assignments']) == 1
    # Another scoped owner sees none of this history and cannot mutate it.
    client.cookies.set('opora_session', 'two'+str(foundation_id))
    assert (await client.get(f"/api/v1/assessment-attempts/{attempt['id']}/result")).status_code == 404
    assert (await post(client, f"/learning/progress/{assignment['lessons'][0]['id']}/complete", {'assignment_id':assignment['id']})).status_code == 404
    assert (await client.get(f"/api/v1/learning/lessons/{assignment['lessons'][0]['id']}")).status_code == 404
    own = (await client.get('/api/v1/me/preparation')).json()
    assert own['introduction_completed'] is False


@pytest.mark.asyncio
async def test_csrf_invalid_option_and_forged_completion(setup):
    client, _, _ = setup
    assignment = (await client.get('/api/v1/me/preparation')).json()['assignments'][0]
    missing = await client.post(f"/api/v1/assessments/{assignment['assessment_version_id']}/attempts", json={}, headers={'X-CSRF-Token':'wrong','Idempotency-Key':'bad'})
    assert missing.status_code == 403
    attempt = (await post(client, f"/assessments/{assignment['assessment_version_id']}/attempts")).json()
    for value in [-1, 999]:
        assert (await post(client, f"/assessment-attempts/{attempt['id']}/answers", {'question_id':attempt['questions'][0]['id'],'selected_option':value})).status_code == 422
    for lesson in assignment['lessons']:
        await post(client, f"/learning/progress/{lesson['id']}/complete", {'assignment_id':assignment['id']})
    await post(client, '/policy-acknowledgements', {'assignment_id':assignment['id']})
    assert (await client.get('/api/v1/me/preparation')).json()['introduction_completed'] is False


@pytest.mark.asyncio
async def test_verified_identity_claim_preserves_progress_and_rejects_collision(setup):
    from app.core.models import User
    from app.modules.learning.service import claim_registration
    client, factory, foundation_id = setup
    item = (await client.get('/api/v1/me/preparation')).json()['assignments'][0]
    await post(client, f"/learning/progress/{item['lessons'][0]['id']}/complete", {'assignment_id':item['id']})
    async with factory() as db:
        original = await db.get(LearningAssignment, UUID(item['id']))
        registration_id = original.registration_id
        user = User(foundation_id=foundation_id, display_name='Verified fixture')
        db.add(user)
        await db.flush()
        await claim_registration(db, registration_id, user.id)
        await db.commit()
        original = await db.get(LearningAssignment, UUID(item['id']))
        assert original.user_id == user.id and original.registration_id is None
        client.cookies.set('opora_session', 'two'+str(foundation_id))
    second = (await client.get('/api/v1/me/preparation')).json()['assignments'][0]
    from app.core.errors import ApiError
    async with factory() as db:
        duplicate = await db.get(LearningAssignment, UUID(second['id']))
        with pytest.raises(ApiError) as rejected:
            await claim_registration(db, duplicate.registration_id, user.id)
        assert rejected.value.code == 'learning_history_conflict'
        await db.rollback()
