"""Real PostgreSQL HTTP contract tests. Opt in with a dedicated disposable database."""
import os
import json
from uuid import UUID, uuid4
from datetime import timedelta
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.db import Base, get_db
from app.core.config import get_settings
from app.core.models import Foundation, User, StaffMembership, PermissionGrant, Session, OutboxMessage, ContactChannel
from app.core.auth import issue_session
from app.core.clock import utcnow
from app.core.errors import ApiError, install_error_handlers
from app.modules.auth.router import router as auth_router
from app.modules.applications.router import router
from app.modules.applications.models import Application, ApplicationRevision, ConsentEvent, FormVersion
from app.modules.applications.form import validate_answers

VALID = dict(firstName="Анна",lastName="Тестовая",birthdate="2012-01-01",phone="+7 (999) 123-45-67",
    email="anna@example.test",area="Другой город",directions=["Творчество"],participation="Каждую неделю",volExp="Нет",
    specialExp="Нет",record="Хочу обсудить",source="Друзья")

def body(answers=None, version=0):
    return dict(expected_version=version, answers=answers or VALID, consents=dict(personal_data=True,news=False,document_version="4"))

def test_no_invented_age_certificate_gate():
    assert validate_answers(VALID,complete=True)["birthdate"]=="2012-01-01"
    with pytest.raises(ApiError) as error:validate_answers({**VALID,"directions":["Творчество","Пока не знаю"]},complete=True)
    assert "directions" in error.value.field_errors
    changed=validate_answers({**VALID,"directions":["Юрист, IT, маркетинг"],"skills":["Керамика","IT","Свой навык"]},complete=True)
    assert changed["skills"]==["IT","Свой навык"]


@pytest_asyncio.fixture
async def env():
    url=os.environ.get("OPORA_CANDIDATES_TEST_DATABASE_URL","")
    if not url:pytest.skip("Set OPORA_CANDIDATES_TEST_DATABASE_URL to a disposable dedicated database")
    if not url.endswith("/opora_candidates_test"):raise RuntimeError("Dedicated candidate test DB required")
    from app.core.model_loader import load_models
    load_models()
    engine=create_async_engine(url)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(Foundation(id=get_settings().foundation_id,name="Тестовый фонд"));await db.commit()
    app=FastAPI();install_error_handlers(app);app.include_router(auth_router);app.include_router(router)
    async def override_db():
        async with factory() as db:
            try:yield db
            except Exception:await db.rollback();raise
    app.state.test_factory = factory
    app.dependency_overrides[get_db]=override_db
    yield app,factory
    await engine.dispose()

async def anonymous_actor(app):
    client=AsyncClient(transport=ASGITransport(app=app),base_url="http://testserver")
    session=(await client.get("/api/v1/auth/session")).json()
    client.headers.update({"Origin":"http://testserver","X-CSRF-Token":session["csrf_token"]})
    return client

async def verify_email(client, factory, email):
    """Use the normal email challenge HTTP flow, reading only the fixture inbox."""
    from app.core.crypto import unseal
    challenge = await post(client, '/auth/challenges', {'email': email})
    assert challenge.status_code == 200, challenge.text
    challenge_id = challenge.json()['challenge_id']
    async with factory() as db:
        payloads = [json.loads(unseal(row.payload_cipher)) for row in (await db.scalars(select(OutboxMessage))).all()]
        payload = next(value for value in payloads if value.get('challenge_id') == challenge_id)
    verified = await post(client, '/auth/challenges/verify', {'challenge_id': challenge_id, 'token': payload['token']})
    assert verified.status_code == 200, verified.text
    client.headers['X-CSRF-Token'] = verified.json()['csrf_token']
    return verified.json()


async def actor(app):
    client = await anonymous_actor(app)
    await verify_email(client, app.state.test_factory, f'candidate-{uuid4().hex}@fixture.example.test')
    return client


async def seed_legacy_registration_application(client, factory, answers=None):
    """Persist a historical anonymous submission; current HTTP routes reject this flow.

    Claim migrations still need to preserve records created before email-first
    registration, so these tests seed the old state rather than bypassing auth.
    """
    from app.core.crypto import digest
    from app.modules.applications.service import current_form
    async with factory() as db:
        session = await db.scalar(select(Session).where(Session.token_hash == digest(client.cookies.get('opora_session'))))
        assert session.registration_id and session.user_id is None
        form = await current_form(db, session.foundation_id, create=True)
        application = Application(foundation_id=session.foundation_id, registration_id=session.registration_id)
        db.add(application)
        await db.flush()
        revision = ApplicationRevision(application_id=application.id, form_version_id=form.id, number=1,
            answers=answers or VALID, author_id=str(session.registration_id))
        db.add(revision)
        await db.flush()
        application.submitted_revision_id = revision.id
        await db.commit()
        return {'id': str(application.id), 'revision': {'id': str(revision.id)}}


async def post(client,path,payload,key=None):
    return await client.post('/api/v1'+path,json=payload,headers={"Idempotency-Key":key or str(uuid4())})

async def staff(app,factory, permissions=("candidates.read","candidates.review","candidates.notes")):
    from starlette.responses import Response
    client=AsyncClient(transport=ASGITransport(app=app),base_url="http://testserver")
    async with factory() as db:
        user=User(foundation_id=get_settings().foundation_id,display_name="Координатор");db.add(user);await db.flush()
        membership=StaffMembership(foundation_id=get_settings().foundation_id,user_id=user.id);db.add(membership);await db.flush()
        for permission in permissions:db.add(PermissionGrant(membership_id=membership.id,permission=permission))
        response=Response();_,csrf=await issue_session(db,response,user_id=user.id,mfa_at=utcnow());await db.commit()
        cookie=response.headers["set-cookie"].split(';')[0].split('=',1)[1]
    client.cookies.set("opora_session",cookie);client.headers.update({"Origin":"http://testserver","X-CSRF-Token":csrf})
    return client

@pytest.mark.asyncio
async def test_revision_queue_privacy_and_public_responses(env):
    app,factory=env
    candidate=await actor(app); other=await actor(app);coord=await staff(app,factory)
    try:
        draft=(await candidate.get('/api/v1/registration/draft')).json();assert draft['version']==0
        async with factory() as db:assert await db.scalar(select(func.count()).select_from(FormVersion))==0
        save=await candidate.put('/api/v1/registration/draft',json=dict(expected_version=0,step=0,answers={'firstName':'Анна'}),headers={'Idempotency-Key':'draft'})
        assert save.status_code==200,save.text
        key=str(uuid4());first=await post(candidate,'/applications/submit',body(),key);assert first.status_code==200,first.text
        value=first.json();assert (await post(candidate,'/applications/submit',body(),key)).json()==value
        assert (await post(candidate,'/applications/submit',body(),str(uuid4()))).status_code==409
        assert (await other.get('/api/v1/me/application')).status_code==404
        assert (await candidate.get('/api/v1/coord/candidates')).status_code==403
        # Matching a contact does not reveal or adopt the first person's data.
        second=await post(other,'/applications/submit',body({**VALID,'firstName':'Другой'}));assert second.json()['id']!=value['id']
        assert len((await coord.get('/api/v1/coord/candidates')).json()['items'])==2
        note=await post(coord,f"/coord/candidates/{value['id']}/notes",dict(text='Только внутри команды'));assert note.status_code==200,note.text
        own=(await candidate.get('/api/v1/me/application')).json();assert 'notes' not in own and 'Только внутри команды' not in str(own)
        revised=await post(candidate,'/me/application/revisions',body({**VALID,'email':'new@example.test'},1));assert revised.status_code==200,revised.text
        assert revised.json()['id']==value['id'] and revised.json()['revision']['number']==2
        assert revised.json()['revision']['answers']['email']==(await candidate.get('/api/v1/auth/session')).json()['verified_email']
        assert (await post(candidate,'/me/application/revisions',body(version=1))).status_code==409
        review=await post(coord,f"/coord/candidates/{value['id']}/review",dict(expected_version=2,state='paused',public_message='Договоримся позже'));assert review.status_code==200,review.text
        reopened=await post(coord,f"/coord/candidates/{value['id']}/reopen",dict(expected_version=3));assert reopened.status_code==200,reopened.text
        req=(await post(candidate,'/me/candidate-requests',dict(kind='alternate_time',text='Можно вечером?'))).json()
        assert (await other.get('/api/v1/me/candidate-requests/'+req['id'])).status_code==404
        reply=await post(coord,f"/coord/candidate-requests/{req['id']}/respond",dict(expected_version=1,text='Да, подберём время'));assert reply.status_code==200,reply.text
        public=(await candidate.get('/api/v1/me/candidate-requests/'+req['id'])).json();assert public['responses'][0]['text']=='Да, подберём время'
        assert 'author_id' not in public['responses'][0]
        async with factory() as db:
            assert await db.scalar(select(func.count()).select_from(ApplicationRevision))==3
            assert await db.scalar(select(func.count()).select_from(ConsentEvent).where(ConsentEvent.purpose=='news',ConsentEvent.granted.is_(False)))==3

    finally:
        await candidate.aclose();await other.aclose();await coord.aclose()

@pytest.mark.asyncio
async def test_concurrent_submissions_and_missing_consent(env):
    import asyncio
    app,factory=env
    candidate=await actor(app)
    try:
        invalid=body();invalid['consents']['personal_data']=False
        assert (await post(candidate,'/applications/submit',invalid)).status_code==422
        results=await asyncio.gather(post(candidate,'/applications/submit',body()),post(candidate,'/applications/submit',body()))
        assert sorted(r.status_code for r in results)==[200,409]
        result=next(r.json() for r in results if r.status_code==200)
        assert (await post(candidate,'/me/application/withdraw',dict(expected_version=result['version']))).status_code==200
        assert (await post(candidate,'/me/application/revisions',body(version=2))).status_code==409

    finally:
        await candidate.aclose()

@pytest.mark.asyncio
async def test_verified_registration_claim_preserves_identity_and_rejects_overwrite(env):
    from app.modules.applications.service import claim_registration
    from app.core.models import RegistrationSession
    app,factory=env
    candidate=await anonymous_actor(app)
    try:
        submitted=await seed_legacy_registration_application(candidate,factory)
        async with factory() as db:
            user=User(foundation_id=get_settings().foundation_id,display_name='Анна');db.add(user);await db.flush()
            db.add(ContactChannel(user_id=user.id,normalized_value='legacy-claim@fixture.example.test',verified_at=utcnow()))
            await db.commit();user_id=user.id
        verified=await verify_email(candidate,factory,'legacy-claim@fixture.example.test')
        assert verified['user_id']==str(user_id)
        async with factory() as db:
            application=await db.get(Application,UUID(submitted['id']))
            user=await db.get(User,user_id)
            assert str(application.id)==submitted['id'] and application.user_id==user.id and application.registration_id is None
            another_registration=RegistrationSession(foundation_id=user.foundation_id,expires_at=utcnow()+timedelta(days=1));db.add(another_registration);await db.flush()
            other_application=Application(foundation_id=user.foundation_id,registration_id=another_registration.id);db.add(other_application);await db.flush()
            with pytest.raises(ApiError) as error:await claim_registration(db,another_registration.id,user.id)
            assert error.value.code=='registration_application_conflict'
            await db.rollback()
    finally:await candidate.aclose()

@pytest.mark.asyncio
async def test_recipient_boundary_checks_scope_and_never_returns_contact_match(env):
    from app.modules.applications.service import learning_recipient_options, learning_recipient_owner
    from app.core.auth import Principal
    from uuid import UUID
    app,factory=env
    candidate=await actor(app)
    try:
        submitted=(await post(candidate,'/applications/submit',body())).json()
        async with factory() as db:
            principal=Principal(uuid4(),None,get_settings().foundation_id,uuid4(),True,'staff',grants=(("candidates.read","foundation",None),))
            options=await learning_recipient_options(db,principal,'Анна')
            assert options==[dict(application_id=UUID(submitted['id']),label='Анна Тестовая')]
            assert await learning_recipient_options(db,principal,'%')==[]
            owner=await learning_recipient_owner(db,principal,UUID(submitted['id']))
            assert owner['user_id'] is not None and owner['registration_id'] is None
            principal.foundation_id=uuid4()
            assert await learning_recipient_options(db,principal)==[]
            with pytest.raises(ApiError) as error:await learning_recipient_owner(db,principal,UUID(submitted['id']))
            assert error.value.status_code==404
            principal.grants=()
            with pytest.raises(ApiError) as error:await learning_recipient_options(db,principal)
            assert error.value.status_code==403
    finally:await candidate.aclose()

@pytest.mark.asyncio
async def test_new_source_form_is_versioned_and_old_draft_edits_keep_identity(env):
    from app.core.models import Session
    from app.core.crypto import digest
    from app.modules.applications.models import ApplicationDraft
    from app.modules.applications.service import current_form
    from app.modules.applications.form import FORM_VERSIONS
    app,factory=env;old=await actor(app);fresh=await actor(app)
    legacy={**VALID,'email':(await old.get('/api/v1/auth/session')).json()['verified_email'],'directions':['Как специалист'],'skills':['IT'],'participation':'Иногда, когда получится','specialExp':'Хочу обсудить на встрече','record':'Да'}
    try:
        async with factory() as db:
            session=await db.scalar(select(Session).where(Session.token_hash==digest(old.cookies.get('opora_session'))))
            form=await current_form(db,session.foundation_id,create=True,version=4)
            draft=ApplicationDraft(foundation_id=session.foundation_id,user_id=session.user_id,registration_id=session.registration_id,form_version_id=form.id,answers=legacy,version=1,step=2);db.add(draft);await db.commit()
        pinned=(await old.get('/api/v1/registration/draft')).json();assert pinned['form']['version']==4 and pinned['answers']==legacy
        new=(await fresh.get('/api/v1/registration/draft')).json();assert new['form']['version']==5
        fields={field['id']:field for step in new['form']['content']['steps'] for field in step['fields']}
        assert 'Юрист, IT, маркетинг' in [option['label'] for option in fields['directions']['options']]
        assert fields['specialExp']['options']==['Да','Нет'] and 'желательно' in fields['record']['label']
        submitted=await post(old,'/applications/submit',body(legacy));assert submitted.status_code==200,submitted.text
        first=submitted.json();assert first['revision']['form_version_id']==str(form.id)
        assert (await old.get('/api/v1/registration/draft')).json()['form']['version']==4
        revised=await post(old,'/me/application/revisions',body({**legacy,'lastName':'Новая фамилия'},version=first['version']));assert revised.status_code==200,revised.text
        assert revised.json()['id']==first['id'] and revised.json()['revision']['form_version_id']==str(form.id)
        assert revised.json()['revision']['answers']['participation']=='Иногда, когда получится'
    finally:await old.aclose();await fresh.aclose()


def test_candidate_stage_follows_review_course_interview_and_first_event():
    from types import SimpleNamespace
    from app.modules.applications.service import candidate_stage
    def stage(review='reviewing', intro='in_progress', interview='none', submission='submitted', attended=False):
        return candidate_stage(SimpleNamespace(submission_state=submission, review_state=review), dict(introduction=dict(status=intro), interview=dict(status=interview)), attended)
    assert stage(review='new', interview='booked') == 'new'
    assert stage() == 'intro' and stage(intro='not_started') == 'intro'
    assert stage(intro='completed') == 'interview' and stage(intro='unavailable') == 'interview'
    assert stage(interview='booked') == 'interview' and stage(intro='completed', interview='missed') == 'interview'
    assert stage(interview='completed') == 'ready' and stage(review='discussed') == 'ready'
    assert stage(interview='completed', attended=True) == 'done'
    assert stage(review='paused') == 'closed' and stage(review='closed') == 'closed' and stage(submission='withdrawn') == 'closed'


async def seed_introduction(db, foundation_id, lessons=2):
    from app.modules.learning.models import LearningTrack, LearningRelease, Lesson, LessonVersion
    track = LearningTrack(foundation_id=foundation_id, key='introduction', title='Знакомство с фондом'); db.add(track); await db.flush()
    versions = []
    for number in range(lessons):
        lesson = Lesson(track_id=track.id, foundation_id=foundation_id, key=f'lesson-{number}'); db.add(lesson); await db.flush()
        version = LessonVersion(lesson_id=lesson.id, number=1, title=f'Урок {number + 1}'); db.add(version); await db.flush()
        versions.append(version.id)
    release = LearningRelease(track_id=track.id, foundation_id=foundation_id, number=1, title='Знакомство', lesson_version_ids=[str(v) for v in versions])
    db.add(release); await db.flush()
    track.current_release_id = release.id
    return release, versions


async def seed_booking(db, application, coordinator_id, status, starts_at):
    from app.modules.interviews.models import AvailabilitySeries, InterviewSlot, InterviewBooking
    series = AvailabilitySeries(foundation_id=application.foundation_id, coordinator_id=coordinator_id, local_start_date=starts_at.date(),
        start_minute=600, end_minute=660, venue='Офис фонда'); db.add(series); await db.flush()
    ends_at = starts_at + timedelta(minutes=30)
    slot = InterviewSlot(foundation_id=application.foundation_id, series_id=series.id, coordinator_id=coordinator_id, origin_date=starts_at.date(),
        origin_minute=600, starts_at=starts_at, ends_at=ends_at, busy_until=ends_at); db.add(slot); await db.flush()
    booking = InterviewBooking(foundation_id=application.foundation_id, application_id=application.id, user_id=application.user_id,
        candidate_key=f'user:{application.user_id}', slot_id=slot.id, coordinator_id=coordinator_id, starts_at=starts_at, ends_at=ends_at,
        busy_until=ends_at, venue='Офис фонда', status=status)
    db.add(booking); await db.flush()
    return booking


@pytest.mark.asyncio
async def test_candidate_funnel_stages_summary_and_reminder(env):
    from sqlalchemy import event
    from app.modules.learning.models import LearningAssignment, LessonProgress
    app, factory = env
    names = ['Новая', 'Учится', 'Прошла', 'Записана', 'Готова', 'Отказ']
    people = [await actor(app) for _ in names]
    coord = await staff(app, factory)
    try:
        ids = []
        for client, name in zip(people, names):
            submitted = await post(client, '/applications/submit', body({**VALID, 'firstName': name}))
            assert submitted.status_code == 200, submitted.text
            ids.append(submitted.json()['id'])
        new, intro, passed, booked, ready, declined = ids
        for application_id in ids[1:]:
            state = 'closed' if application_id == declined else 'reviewing'
            accepted = await post(coord, f'/coord/candidates/{application_id}/review', dict(expected_version=1, state=state, public_message='Анкета принята'))
            assert accepted.status_code == 200, accepted.text
        now = utcnow()
        async with factory() as db:
            rows = {row.id: row for row in (await db.scalars(select(Application))).all()}
            release, lessons = await seed_introduction(db, get_settings().foundation_id)
            learning = LearningAssignment(foundation_id=release.foundation_id, release_id=release.id, user_id=rows[UUID(intro)].user_id); db.add(learning); await db.flush()
            db.add(LessonProgress(assignment_id=learning.id, lesson_version_id=lessons[0]))
            db.add(LearningAssignment(foundation_id=release.foundation_id, release_id=release.id, user_id=rows[UUID(passed)].user_id, completed_at=now))
            coordinator = User(foundation_id=get_settings().foundation_id, display_name='Ведущий'); db.add(coordinator); await db.flush()
            meeting = await seed_booking(db, rows[UUID(booked)], coordinator.id, 'booked', now + timedelta(days=1))
            done = await seed_booking(db, rows[UUID(ready)], coordinator.id, 'completed', now - timedelta(days=1))
            await db.commit()
        summary = await coord.get('/api/v1/coord/candidates/summary')
        assert summary.status_code == 200, summary.text
        assert summary.json() == dict(new=1, intro=1, interview=2, ready=1, done=0, closed=1)
        assert (await people[0].get('/api/v1/coord/candidates/summary')).status_code == 403

        learning_row = (await coord.get('/api/v1/coord/candidates?stage=intro')).json()
        assert [item['id'] for item in learning_row['items']] == [intro] and learning_row['total'] == 1
        assert learning_row['items'][0]['progress']['introduction'] == dict(status='in_progress', completed_lessons=1, total_lessons=2)
        interview = (await coord.get('/api/v1/coord/candidates?stage=interview')).json()
        assert [item['id'] for item in interview['items']] == [passed, booked]
        assert interview['items'][0]['progress']['interview']['status'] == 'none'
        assert interview['items'][1]['progress']['interview']['booking_id'] == str(meeting.id)
        assert (await coord.get('/api/v1/coord/candidates?stage=interview&limit=1&offset=1')).json()['items'][0]['id'] == booked
        ready_row = (await coord.get('/api/v1/coord/candidates?stage=ready')).json()['items'][0]
        assert ready_row['id'] == ready and ready_row['stage'] == 'ready' and UUID(ready_row['progress']['interview']['booking_id']) == done.id
        from datetime import datetime
        assert abs(datetime.fromisoformat(ready_row['stage_since'].replace('Z', '+00:00')) - done.starts_at) < timedelta(seconds=1)
        assert [item['id'] for item in (await coord.get('/api/v1/coord/candidates?stage=new&q=Нова')).json()['items']] == [new]
        assert (await coord.get('/api/v1/coord/candidates?stage=new&q=Учится')).json()['total'] == 0
        assert (await coord.get('/api/v1/coord/candidates?stage=closed')).json()['items'][0]['id'] == declined
        assert (await coord.get('/api/v1/coord/candidates?stage=unknown')).status_code == 422
        # The old filters keep their meaning and every row carries its stage.
        everyone = (await coord.get('/api/v1/coord/candidates')).json()
        assert everyone['total'] == 6 and {item['id']: item['stage'] for item in everyone['items']}[booked] == 'interview'
        assert [item['id'] for item in (await coord.get('/api/v1/coord/candidates?review_state=new')).json()['items']] == [new]
        detail = (await coord.get(f'/api/v1/coord/candidates/{intro}')).json()
        assert detail['stage'] == 'intro' and detail['progress']['introduction']['completed_lessons'] == 1

        # The list reads a page with a fixed number of queries, not one batch per row.
        engine = factory.kw['bind'].sync_engine
        statements = []
        def count(*_args):statements.append(1)
        event.listen(engine, 'before_cursor_execute', count)
        try:
            await coord.get('/api/v1/coord/candidates?offset=4&limit=1'); one = len(statements); statements.clear()
            await coord.get('/api/v1/coord/candidates?limit=6'); six = len(statements)
        finally:
            event.remove(engine, 'before_cursor_execute', count)
        assert six == one

        async with factory() as db:outbox = await db.scalar(select(func.count()).select_from(OutboxMessage))
        reminded = await post(coord, f'/coord/candidates/{intro}/remind', dict(expected_version=detail['version']))
        assert reminded.status_code == 200, reminded.text
        assert reminded.json()['history'][-1]['kind'] == 'reminded' and reminded.json()['version'] == detail['version'] + 1
        async with factory() as db:assert await db.scalar(select(func.count()).select_from(OutboxMessage)) == outbox + 1
        again = await post(coord, f'/coord/candidates/{intro}/remind', dict(expected_version=detail['version'] + 1))
        assert again.status_code == 409 and again.json()['code'] == 'already_reminded'
        early = await post(coord, f'/coord/candidates/{new}/remind', dict(expected_version=1))
        assert early.status_code == 409 and early.json()['code'] == 'reminder_not_needed'
        reader = await staff(app, factory, permissions=('candidates.read',))
        try:assert (await post(reader, f'/coord/candidates/{intro}/remind', dict(expected_version=detail['version'] + 1))).status_code == 403
        finally:await reader.aclose()
        own = (await people[1].get('/api/v1/me/application')).json()
        assert 'stage' not in own and 'progress' not in own
    finally:
        for client in people:await client.aclose()
        await coord.aclose()
