"""Real PostgreSQL tests. Use only an isolated OPORA_TEST_DATABASE_URL ending in _test."""
import asyncio
from datetime import timedelta
import os
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import Principal, resolve_principal
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.db import Base, get_db
from app.core.errors import ApiError
from app.core.models import AuditEvent, Foundation, PermissionGrant, Session, StaffMembership, User
from app.modules.activities.models import Opportunity, OpportunityRoleLink, VolunteerRole, VolunteerRoleVersion
from app.modules.activities.router import router
from app.modules.activities.schemas import OpportunityCreate, RoleCreate, RoleUpdate, VersionCommand, normalized_title
from app.modules.activities import service

URL=os.getenv('OPORA_TEST_DATABASE_URL')
pytestmark=pytest.mark.skipif(not URL, reason='Set an isolated PostgreSQL OPORA_TEST_DATABASE_URL')


@pytest_asyncio.fixture
async def context():
    if not URL:pytest.skip('Set an isolated PostgreSQL OPORA_TEST_DATABASE_URL')
    assert URL.rsplit('/',1)[-1].endswith('_test'), 'Refusing non-test database'
    from app.core.model_loader import load_models
    load_models()
    # Shared readiness helpers can load these modules lazily during a previous run.
    import importlib
    for model_module in ('app.modules.knowledge.models','app.integrations.ai.models','app.modules.profile.models','app.modules.crm.models'):
        try:importlib.import_module(model_module)
        except ModuleNotFoundError as error:
            if error.name not in (model_module,model_module.rsplit('.',1)[0]):raise
    engine=create_async_engine(URL)
    async with engine.begin() as connection:
        await connection.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    async with factory() as db:
        foundation=Foundation(name='Invented foundation')
        other=Foundation(name='Other invented foundation')
        db.add_all([foundation,other]);await db.flush()
        user=User(foundation_id=foundation.id,display_name='Invented coordinator')
        db.add(user);await db.flush()
        member=StaffMembership(foundation_id=foundation.id,user_id=user.id)
        db.add(member);await db.flush()
        grants=[PermissionGrant(membership_id=member.id,permission=p,scope_type='foundation') for p in ['roles.manage','opportunities.manage']]
        db.add_all(grants)
        session=Session(foundation_id=foundation.id,user_id=user.id,token_hash=digest('staff'),csrf_hash=digest('csrf'),csrf_cipher='unused',expires_at=utcnow()+timedelta(hours=1),mfa_at=utcnow())
        volunteer=User(foundation_id=foundation.id,display_name='Invented volunteer');db.add(volunteer);await db.flush()
        self_session=Session(foundation_id=foundation.id,user_id=volunteer.id,token_hash=digest('self'),csrf_hash=digest('self-csrf'),csrf_cipher='unused',expires_at=utcnow()+timedelta(hours=1))
        db.add_all([session,self_session]);await db.flush();await db.commit()
        principal=await resolve_principal(db,session)
        foreign_principal=Principal(None,None,other.id,uuid4(),False,'other')
    app=FastAPI();app.include_router(router,prefix='/api/v1')
    from app.modules.participants.router import router as participants_router
    from app.modules.participants.access import get_assignment_access
    from app.modules.activities.assignment_service import ActivityAssignmentAccess
    app.include_router(participants_router)
    app.dependency_overrides[get_assignment_access]=ActivityAssignmentAccess
    @app.exception_handler(ApiError)
    async def handler(request:Request,error:ApiError):
        return JSONResponse(status_code=error.status_code,content={'code':error.code,'message':error.message})
    async def override():
        async with factory() as db:
            try:yield db
            except BaseException:
                await db.rollback();raise
    app.dependency_overrides[get_db]=override
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',cookies={'opora_session':'staff'}) as client:
        yield SimpleNamespace(db=factory,principal=principal,foreign=foreign_principal,client=client,grants=grants,foundation=foundation,other=other)
    await engine.dispose()


def headers(key=None):
    return {'Origin':'http://testserver','X-CSRF-Token':'csrf','Idempotency-Key':key or str(uuid4())}


async def post_role(context,title='Ассистент'):
    response=await context.client.post('/api/v1/coord/roles',headers=headers(),json={'title':title,'task':'Помогать ведущей','preparation_defaults':[{'key':'intro','title':'Обсудить задачу','level':'recommended'}]})
    assert response.status_code==200,response.text
    return response.json()


@pytest.mark.asyncio
async def test_normalization_snapshot_archive_restore_conflict(context):
    role=await post_role(context,'  Ассистент   на занятии ')
    duplicate=await context.client.post('/api/v1/coord/roles',headers=headers(),json={'title':'ассистент НА  занятии'})
    assert duplicate.status_code==409
    opportunity=await context.client.post('/api/v1/coord/opportunities',headers=headers(),json={'title':'Помощь','role_ids':[role['id']],'program':'Творчество','audience':'Взрослые','location':'Мастерская','schedule':'По субботам'})
    assert opportunity.status_code==200,opportunity.text
    snapshot=opportunity.json()
    updated=await context.client.patch(f"/api/v1/coord/roles/{role['id']}",headers=headers(),json={'title':role['title'],'task':'Другая задача','preparation_defaults':[],'expected_version':1})
    assert updated.status_code==200
    read=await context.client.get(f"/api/v1/coord/opportunities/{snapshot['id']}")
    assert read.json()['task']=='Помогать ведущей'
    assert read.json()['preparation_requirements'][0]['level']=='recommended'
    archived=await context.client.post(f"/api/v1/coord/roles/{role['id']}/archive",headers=headers(),json={'expected_version':2})
    assert archived.status_code==200
    replacement=await post_role(context,'Ассистент на занятии')
    restored=await context.client.post(f"/api/v1/coord/roles/{role['id']}/restore",headers=headers(),json={'expected_version':3})
    assert restored.status_code==409
    async with context.db() as db:
        saved=await db.get(VolunteerRole,role['id']);assert saved.archived_at is not None and saved.version==3
        assert await db.scalar(select(func.count()).select_from(VolunteerRoleVersion).where(VolunteerRoleVersion.role_id==saved.id))==3


@pytest.mark.asyncio
async def test_idempotency_commit_version_conflict_and_isolation(context):
    key=str(uuid4());body={'title':'Фотограф'}
    one,two=await asyncio.gather(*[context.client.post('/api/v1/coord/roles',headers=headers(key),json=body) for _ in range(2)])
    assert one.status_code==two.status_code==200
    assert one.json()['id']==two.json()['id']
    conflict=await context.client.post('/api/v1/coord/roles',headers=headers(key),json={'title':'Другая роль'})
    assert conflict.status_code==409
    role=one.json()
    first,second=await asyncio.gather(*[context.client.patch(f"/api/v1/coord/roles/{role['id']}",headers=headers(),json={'title':f'Изменение {i}','expected_version':1}) for i in range(2)])
    assert sorted([first.status_code,second.status_code])==[200,409]
    async with context.db() as db:
        with pytest.raises(ApiError) as error:await service.find_role(db,context.foreign,role['id'])
        assert error.value.status_code==404
        assert await db.scalar(select(func.count()).select_from(AuditEvent))==2


@pytest.mark.asyncio
async def test_published_only_acl_csrf_and_revocation(context):
    role=await post_role(context)
    opportunity=await context.client.post('/api/v1/coord/opportunities',headers=headers(),json={'title':'Занятие','role_ids':[role['id']],'program':'Творчество','audience':'Взрослые','location':'Мастерская','schedule':'Суббота'})
    item=opportunity.json();assert opportunity.status_code==200
    public=f"/api/v1/opportunities/{item['id']}"
    assert (await context.client.get(public)).status_code==404
    assert (await context.client.get('/api/v1/opportunities')).json()['items']==[]
    published=await context.client.post(f"/api/v1/coord/opportunities/{item['id']}/publish",headers=headers(),json={'expected_version':1})
    assert published.status_code==200,published.text
    view=(await context.client.get(public)).json()
    assert view['matching']['reasons']==[] and 'availability' in view['matching']['missing_data']
    assert 'score' not in view['matching'] and view['allowed_actions']==[]
    # A staff cookie alone is not command authorization: browser CSRF is enforced.
    no_csrf=await context.client.post('/api/v1/coord/roles',headers={'Origin':'http://testserver','Idempotency-Key':str(uuid4())},json={'title':'No'})
    assert no_csrf.status_code==403
    context.client.cookies.set('opora_session','self')
    assert (await context.client.get('/api/v1/coord/roles')).status_code==403
    assert (await context.client.get(public)).status_code==200
    context.client.cookies.set('opora_session','staff')
    async with context.db() as db:
        for grant in context.grants:
            g=await db.get(PermissionGrant,grant.id);g.revoked_at=utcnow()
        await db.commit()
    assert (await context.client.post('/api/v1/coord/roles',headers=headers(),json={'title':'Revoked'})).status_code==403


@pytest.mark.asyncio
async def test_cross_foundation_links_are_rejected_by_database(context):
    async with context.db() as db:
        role=await service.create_role(db,context.principal,RoleCreate(title='Одна роль'))
        other_role=VolunteerRole(foundation_id=context.other.id,title='Other',normalized_title='other',updated_by='fixture')
        db.add(other_role);await db.flush()
        revision=VolunteerRoleVersion(role_id=other_role.id,version=1,snapshot={},actor_id='fixture');db.add(revision);await db.flush()
        opp=Opportunity(foundation_id=context.foundation.id,title='Fixture',updated_by='fixture');db.add(opp);await db.flush()
        db.add(OpportunityRoleLink(opportunity_id=opp.id,foundation_id=context.foundation.id,role_id=other_role.id,role_version_id=revision.id))
        with pytest.raises(IntegrityError):await db.flush()
        await db.rollback()


@pytest.mark.asyncio
async def test_scoped_grant_never_escalates_to_foundation_role_directory(context):
    async with context.db() as db:
        for grant in context.grants:
            row=await db.get(PermissionGrant,grant.id);row.scope_type='group';row.scope_id=uuid4()
        await db.commit()
    assert (await context.client.get('/api/v1/coord/roles')).status_code==403
    assert (await context.client.get('/api/v1/coord/opportunities')).status_code==403
    assert (await context.client.post('/api/v1/coord/roles',headers=headers(),json={'title':'Denied'})).status_code==403


@pytest.mark.asyncio
async def test_requirements_validation_and_archive_never_rewrites_links(context):
    invalid=await context.client.post('/api/v1/coord/roles',headers=headers(),json={'title':'Роль','preparation_defaults':[{'key':'blank','title':'   '}]})
    assert invalid.status_code==422
    invalid=await context.client.post('/api/v1/coord/roles',headers=headers(),json={'title':'Роль','preparation_defaults':[{'key':'same','title':'Первое'},{'key':'same','title':'Второе'}]})
    assert invalid.status_code==422
    role=await post_role(context)
    opportunity=await context.client.post('/api/v1/coord/opportunities',headers=headers(),json={'title':'Условие','role_ids':[role['id']]})
    item=opportunity.json()
    assert (await context.client.post(f"/api/v1/coord/roles/{role['id']}/archive",headers=headers(),json={'expected_version':1})).status_code==200
    read=(await context.client.get(f"/api/v1/coord/opportunities/{item['id']}")).json()
    assert read['role_ids']==[role['id']]
    # Existing opportunity is editable even though its historical role is archived.
    body={k:v for k,v in read.items() if k in OpportunityCreate.model_fields};body.update(title='Новое название',expected_version=1)
    assert (await context.client.patch(f"/api/v1/coord/opportunities/{item['id']}",headers=headers(),json=body)).status_code==200
    new=await context.client.post('/api/v1/coord/opportunities',headers=headers(),json={'title':'Недоступно','role_ids':[role['id']]})
    assert new.status_code==422
