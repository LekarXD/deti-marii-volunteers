"""Real PostgreSQL HTTP contract tests. Opt in with a dedicated disposable database."""
import os
from uuid import uuid4
from datetime import timedelta
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.db import Base, get_db
from app.core.config import get_settings
from app.core.models import Foundation, User, StaffMembership, PermissionGrant, Session
from app.core.auth import issue_session
from app.core.clock import utcnow
from app.core.errors import ApiError, install_error_handlers
from app.modules.auth.router import router as auth_router
from app.modules.applications.router import router
from app.modules.applications.models import Application, ApplicationRevision, ConsentEvent, FormVersion
from app.modules.applications.form import validate_answers

VALID = dict(firstName="Анна",lastName="Тестовая",birthdate="2012-01-01",phone="+7 (999) 123-45-67",
    email="anna@example.test",area="Другой город",directions=["Творчество"],participation="Каждую неделю",volExp="Нет",
    specialExp="Хочу обсудить на встрече",record="Хочу обсудить",source="Друзья")

def body(answers=None, version=0):
    return dict(expected_version=version, answers=answers or VALID, consents=dict(personal_data=True,news=False,document_version="4"))

def test_no_invented_age_certificate_gate():
    assert validate_answers(VALID,complete=True)["birthdate"]=="2012-01-01"
    with pytest.raises(ApiError) as error:validate_answers({**VALID,"directions":["Творчество","Пока не знаю"]},complete=True)
    assert "directions" in error.value.field_errors


@pytest_asyncio.fixture
async def env():
    url=os.environ.get("OPORA_CANDIDATES_TEST_DATABASE_URL","")
    if not url:pytest.skip("Set OPORA_CANDIDATES_TEST_DATABASE_URL to a disposable dedicated database")
    if not url.endswith("/opora_candidates_test"):raise RuntimeError("Dedicated candidate test DB required")
    engine=create_async_engine(url)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:
        db.add(Foundation(id=get_settings().foundation_id,name="Тестовый фонд"));await db.commit()
    app=FastAPI();install_error_handlers(app);app.include_router(auth_router);app.include_router(router)
    async def override_db():
        async with factory() as db:
            try:yield db
            except Exception:await db.rollback();raise
    app.dependency_overrides[get_db]=override_db
    yield app,factory
    await engine.dispose()

async def actor(app):
    client=AsyncClient(transport=ASGITransport(app=app),base_url="http://testserver")
    session=(await client.get("/api/v1/auth/session")).json()
    client.headers.update({"Origin":"http://testserver","X-CSRF-Token":session["csrf_token"]})
    return client

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
    candidate=await actor(app)
    try:
        submitted=(await post(candidate,'/applications/submit',body())).json()
        async with factory() as db:
            application=await db.get(Application,submitted['id'])
            original_id=application.id;registration_id=application.registration_id
            user=User(foundation_id=get_settings().foundation_id,display_name='Анна');db.add(user);await db.flush()
            await claim_registration(db,registration_id,user.id);await db.commit()
            await db.refresh(application)
            assert application.id==original_id and application.user_id==user.id and application.registration_id is None
            another_registration=RegistrationSession(foundation_id=user.foundation_id,expires_at=utcnow()+timedelta(days=1));db.add(another_registration);await db.flush()
            other_application=Application(foundation_id=user.foundation_id,registration_id=another_registration.id);db.add(other_application);await db.flush()
            with pytest.raises(ApiError) as error:await claim_registration(db,another_registration.id,user.id)
            assert error.value.code=='registration_application_conflict'
            await db.rollback()
    finally:await candidate.aclose()
