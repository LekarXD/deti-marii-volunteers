import os
from datetime import timedelta
from uuid import UUID,uuid4
import pytest,pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import select,text,delete
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.core.db import Base,get_db
from app.core.config import get_settings
from app.core.clock import utcnow
from app.core.auth import get_principal
from app.core.crypto import digest
from app.core.errors import install_error_handlers
from app.core.model_loader import load_models
from app.core.models import Foundation,User,AuditEvent,Session,StaffMembership,PermissionGrant
from app.modules.auth.router import router as auth_router
from app.modules.admin.router import router
from app.modules.applications.tests.test_applications import staff
from app.modules.reporting.tests.test_reporting import principal
load_models()

@pytest_asyncio.fixture
async def env():
    url=os.environ.get('OPORA_ADMIN_TEST_DATABASE_URL','')
    if not url:pytest.skip('Set dedicated OPORA_ADMIN_TEST_DATABASE_URL')
    if not url.endswith('/opora_admin_test'):raise RuntimeError('Dedicated admin database required')
    engine=create_async_engine(url);factory=async_sessionmaker(engine,expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'));await conn.run_sync(Base.metadata.drop_all);await conn.run_sync(Base.metadata.create_all)
    async with factory() as db:db.add(Foundation(id=get_settings().foundation_id,name='Вымышленный фонд'));await db.commit()
    app=FastAPI();install_error_handlers(app);app.include_router(auth_router);app.include_router(router)
    async def override():
        async with factory() as db:
            try:yield db
            except BaseException:await db.rollback();raise
    app.dependency_overrides[get_db]=override
    yield app,factory
    await engine.dispose()

@pytest.mark.asyncio
async def test_audit_projection_denies_exact_foreign_foundation_and_exposes_only_safe_metadata(env):
    app,factory=env;client=await staff(app,factory,('staff.manage',));owner=await principal(client,factory);foreign_id=uuid4();event_id=uuid4();foreign_actor=uuid4()
    try:
        async with factory() as db:
            db.add(Foundation(id=foreign_id,name='Чужой фонд'));await db.flush();db.add(User(id=foreign_actor,foundation_id=foreign_id,display_name='Чужое секретное имя'));await db.flush()
            db.add(AuditEvent(id=event_id,foundation_id=owner.foundation_id,actor_id=str(owner.user_id),command='staff.grant',entity_type='permission_grant',entity_id=str(uuid4()),changed_fields=['permission','scope',{'body':'private-body'},'secret@example.test'],request_id=str(uuid4())))
            db.add(AuditEvent(foundation_id=owner.foundation_id,actor_id=str(foreign_actor),command='report.confirm',entity_type='report',entity_id=str(uuid4()),changed_fields=['state']))
            db.add(AuditEvent(foundation_id=foreign_id,actor_id=str(foreign_actor),command='foreign.secret',entity_type='foreign',entity_id=str(uuid4()),changed_fields=['secret']));await db.commit()
        blocked=await client.get('/api/v1/coord/admin/audit',params={'foundation_id':str(foreign_id)});assert blocked.status_code==403 and blocked.json()['code']=='foundation_scope_denied'
        response=await client.get('/api/v1/coord/admin/audit');assert response.status_code==200,response.text
        value=response.json();assert set(value)=={'items','next_cursor','snapshot_at'} and len(value['items'])==2
        row=next(item for item in value['items'] if item['id']==str(event_id));assert set(row)=={'id','created_at','actor_id','actor_label','command','entity_type','entity_id','changed_fields','request_id'}
        assert row['changed_fields']==['permission','scope'] and row['actor_label']=='Координатор'
        assert 'foreign.secret' not in response.text and 'Чужое секретное имя' not in response.text and 'private-body' not in response.text and 'secret@example.test' not in response.text
        assert next(item for item in value['items'] if item['actor_id']==str(foreign_actor))['actor_label']=='Участник системы'
    finally:await client.aclose()

@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['ordinary','no_mfa','revoked','scoped_only'])
async def test_audit_requires_current_foundation_management_and_mfa(env,mode):
    app,factory=env;client=await staff(app,factory,('staff.manage',));stale=await principal(client,factory)
    try:
        async with factory() as db:
            member=await db.scalar(select(StaffMembership).where(StaffMembership.user_id==stale.user_id));grant=await db.scalar(select(PermissionGrant).where(PermissionGrant.membership_id==member.id))
            if mode=='ordinary':
                await db.delete(grant);await db.flush();await db.delete(member)
            elif mode=='no_mfa':(await db.get(Session,stale.session_id)).mfa_at=None
            elif mode=='revoked':grant.revoked_at=utcnow()
            else:grant.scope_type='group';grant.scope_id=uuid4()
            await db.commit()
        # Deliberately provide a previously authorized principal: the read guard
        # must revalidate the live session/membership/grants under its lock.
        app.dependency_overrides[get_principal]=lambda:stale
        response=await client.get('/api/v1/coord/admin/audit');assert response.status_code==403 and response.json()['code']=='permission_denied'
    finally:await client.aclose()

@pytest.mark.asyncio
async def test_audit_cursor_orders_equal_timestamps_and_binds_filters_to_a_snapshot(env):
    app,factory=env;client=await staff(app,factory,('staff.manage',));owner=await principal(client,factory);when=utcnow()-timedelta(days=1);ids=[uuid4() for _ in range(7)]
    try:
        async with factory() as db:
            for id in ids:db.add(AuditEvent(id=id,foundation_id=owner.foundation_id,actor_id=str(owner.user_id),command='report.confirm',entity_type='report',entity_id=str(id),created_at=when,changed_fields=['state']))
            db.add(AuditEvent(foundation_id=owner.foundation_id,actor_id=str(owner.user_id),command='staff.grant',entity_type='permission_grant',entity_id=str(uuid4()),created_at=when,changed_fields=['scope']));await db.commit()
        filters=dict(limit=3,command='report.confirm',from_at=(when-timedelta(hours=1)).isoformat(),until_at=(when+timedelta(days=2)).isoformat())
        first=(await client.get('/api/v1/coord/admin/audit',params=filters)).json();seen=[item['id'] for item in first['items']];cursor=first['next_cursor'];anchor=first['snapshot_at']
        async with factory() as db:db.add(AuditEvent(foundation_id=owner.foundation_id,actor_id=str(owner.user_id),command='report.confirm',entity_type='report',entity_id=str(uuid4()),changed_fields=['state']));await db.commit()
        assert (await client.get('/api/v1/coord/admin/audit',params={**filters,'cursor':cursor,'command':'staff.grant'})).status_code==422
        while cursor:
            page=(await client.get('/api/v1/coord/admin/audit',params={**filters,'cursor':cursor})).json();assert page['snapshot_at']==anchor;seen.extend(item['id'] for item in page['items']);cursor=page['next_cursor']
        assert seen==[str(id) for id in sorted(ids,reverse=True)] and len(set(seen))==7
        assert (await client.get('/api/v1/coord/admin/audit',params={'limit':101})).status_code==422
        assert (await client.get('/api/v1/coord/admin/audit',params={'cursor':'tampered'})).status_code==422
        assert (await client.get('/api/v1/coord/admin/audit',params={'from_at':'2026-10-01T00:00:00'})).status_code==422
    finally:await client.aclose()
