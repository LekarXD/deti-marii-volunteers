"""Real PostgreSQL payload/query-budget evidence in an isolated random schema."""
from contextlib import contextmanager
from datetime import date,datetime,time,timedelta,timezone
import os
import re
from types import SimpleNamespace
from uuid import UUID,uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from sqlalchemy import event,select,text,update
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker,create_async_engine

from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.db import Base,get_db
from app.core.errors import ApiError,install_error_handlers
from app.core.models import Foundation,User,Session,StaffMembership,PermissionGrant
from app.core.model_loader import load_models
from app.modules.activities import calendar_service as service
from app.modules.activities.assignment_models import Assignment
from app.modules.activities.calendar_models import EventSeries,EventOccurrence,OccurrenceOverride,StaffingNeed
from app.modules.activities.models import VolunteerRole,VolunteerRoleVersion
from app.modules.activities.router import router


@pytest_asyncio.fixture
async def calendar_data():
    dsn=os.getenv('OPORA_ACTIVITIES_PERF_TEST_DATABASE_URL')
    if not dsn:pytest.skip('Set OPORA_ACTIVITIES_PERF_TEST_DATABASE_URL to the dedicated local database')
    url=make_url(dsn)
    assert url.database=='opora_activities_perf_test' and url.host=='127.0.0.1' and url.port is not None and 0<url.port<65536,'Refuse any other database or server'
    schema='calendar_perf_'+uuid4().hex
    assert re.fullmatch(r'calendar_perf_[a-f0-9]{32}',schema)
    load_models()
    engine=create_async_engine(dsn,execution_options={'schema_translate_map':{None:schema}})
    async with engine.begin() as conn:
        await conn.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
        await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        await conn.run_sync(Base.metadata.create_all)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    try:
        async with factory() as db:
            foundations=[Foundation(name='Fictitious calendar'),Foundation(name='Foreign fictitious calendar')]
            db.add_all(foundations);await db.flush()
            own,foreign=[row.id for row in foundations]
            coordinator=User(foundation_id=own,display_name='Local calendar coordinator')
            db.add(coordinator);await db.flush()
            membership=StaffMembership(foundation_id=own,user_id=coordinator.id)
            db.add(membership);await db.flush()
            grant=PermissionGrant(membership_id=membership.id,permission='schedule.manage')
            read_grant=PermissionGrant(membership_id=membership.id,permission='schedule.read')
            db.add_all([grant,read_grant,Session(foundation_id=own,user_id=coordinator.id,token_hash=digest(schema),csrf_hash=digest('fixture'),csrf_cipher='unused',mfa_at=utcnow(),expires_at=utcnow()+timedelta(hours=1))])
            event_ids=[];foreign_ids=[];need_ids={}
            for foundation,count in ((own,60),(foreign,3)):
                users=[User(foundation_id=foundation,display_name=f'Fictitious volunteer {i}') for i in range(18)]
                db.add_all(users);await db.flush()
                series=EventSeries(foundation_id=foundation,anchor_date=date(2028,1,1),origin_time=time(12),start_date=date(2028,1,1),start_time=time(12),duration_minutes=60,recurrence={'frequency':'once'},title='Original series',location='Local room',updated_by='fixture')
                db.add(series);await db.flush()
                roles=[];revisions=[]
                for n in range(3):
                    role=VolunteerRole(foundation_id=foundation,title=f'Current role {n}',normalized_title=f'current role {n}',version=2,archived_at=utcnow() if n==0 else None,updated_by='fixture')
                    db.add(role);await db.flush();roles.append(role)
                    old=VolunteerRoleVersion(role_id=role.id,version=1,snapshot={'title':f'Frozen role {n}'},actor_id='fixture')
                    new=VolunteerRoleVersion(role_id=role.id,version=2,snapshot={'title':role.title},actor_id='fixture')
                    db.add_all([old,new]);await db.flush();revisions.append((old,new))
                for n in range(count):
                    # Effective dates moved beyond the exhausted once-series. The
                    # read route therefore has no unrelated materialization growth.
                    start=datetime(2032,1,1,10,tzinfo=timezone.utc)+timedelta(days=n)
                    item=EventOccurrence(id=UUID(int=(n+1 if foundation==own else 1000+n)),foundation_id=foundation,series_id=series.id,origin_local_date=date(2028,1,1)+timedelta(days=n),origin_local_time=time(12),starts_at=start,ends_at=start+timedelta(hours=1),timezone='Europe/Moscow',title=f'Occurrence {n}',location='Moved room',status=('scheduled','cancelled','completed')[n%3],series_version=2,version=n+1,updated_by='fixture')
                    db.add(item);await db.flush()
                    (event_ids if foundation==own else foreign_ids).append(item.id)
                    if n%2==0:db.add(OccurrenceOverride(occurrence_id=item.id,fields={'location':'Moved room'},updated_by='fixture'))
                    for r in range(3):
                        need=StaffingNeed(occurrence_id=item.id,foundation_id=foundation,role_id=roles[r].id,role_version_id=revisions[r][n%2].id,capacity_required=r,version=n+1,preparation_requirements=[{'key':f'prep{r}','title':f'Frozen preparation {n}/{r}','level':'mandatory' if r==0 else 'recommended'}],approval_policy='self_confirmation' if r==2 else 'coordinator')
                        db.add(need);await db.flush();need_ids[(item.id,r)]=need.id
                        for u,status in enumerate(('invited','confirmed','confirmed','declined','cancelled','expired')):
                            db.add(Assignment(foundation_id=foundation,user_id=users[r*6+u].id,occurrence_id=item.id,staffing_need_id=need.id,status=status,confirmed_at=utcnow() if status=='confirmed' else None,conditions_version=1,conditions_snapshot={}))
                await db.flush()
            await db.commit()
        app=FastAPI();app.include_router(router,prefix='/api/v1');install_error_handlers(app)
        async def override():
            async with factory() as db:
                try:yield db
                except BaseException:await db.rollback();raise
        app.dependency_overrides[get_db]=override
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://testserver',cookies={'opora_session':schema}) as client:
            yield SimpleNamespace(db=factory,engine=engine,foundation=own,foreign=foreign,event_ids=event_ids,foreign_ids=foreign_ids,need_ids=need_ids,client=client,manage_grant=grant.id,read_grant=read_grant.id)
    finally:
        async with engine.begin() as conn:await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await engine.dispose()


@contextmanager
def select_queries(engine):
    statements=[]
    def record(conn,cursor,statement,parameters,context,executemany):
        if statement.lstrip().upper().startswith('SELECT'):statements.append(statement)
    event.listen(engine.sync_engine,'before_cursor_execute',record)
    try:yield statements
    finally:event.remove(engine.sync_engine,'before_cursor_execute',record)


async def rows(x,limit):
    async with x.db() as db:return list((await db.scalars(select(EventOccurrence).where(EventOccurrence.foundation_id==x.foundation).order_by(EventOccurrence.id).limit(limit))).all())


@pytest.mark.asyncio
async def test_bulk_payload_matches_single_views_with_constant_query_budget(calendar_data):
    x=calendar_data
    for size in (3,60):
        items=await rows(x,size)
        async with x.db() as db:
            with select_queries(x.engine) as bulk_queries:
                bulk=await service.occurrence_views(db,x.foundation,items)
        async with x.db() as db:
            with select_queries(x.engine) as single_queries:
                single=[await service.occurrence_view(db,item) for item in items]
        assert [row.model_dump(mode='json') for row in bulk]==[row.model_dump(mode='json') for row in single]
        assert len(bulk_queries)==4
        assert len(single_queries)==size*8
        assert [row.id for row in bulk]==[item.id for item in items]
        for n,row in enumerate(bulk):
            assert row.has_override==(n%2==0)
            assert row.allowed_actions==(['edit','copy','cancel'],['edit','copy','restore'],['copy'])[n%3]
            assert [need.id for need in row.staffing_needs]==sorted(need.id for need in row.staffing_needs)
            for need in row.staffing_needs:
                r=next(r for r in range(3) if x.need_ids[(row.id,r)]==need.id)
                assert need.role_title==(f'Frozen role {r}' if n%2==0 else f'Current role {r}')
                assert (need.required,need.invited,need.confirmed,need.missing)==(r,1,2,max(0,r-2))
                assert need.preparation_requirements[0].title==f'Frozen preparation {n}/{r}'
    async with x.db() as db:
        with select_queries(x.engine) as empty_queries:assert await service.occurrence_views(db,x.foundation,[])==[]
        assert empty_queries==[]
        foreign=list((await db.scalars(select(EventOccurrence).where(EventOccurrence.foundation_id==x.foreign))).all())
        with pytest.raises(ApiError) as error:await service.occurrence_views(db,x.foundation,foreign)
        assert error.value.status_code==404


@pytest.mark.asyncio
async def test_range_pagination_query_budget_and_current_authorization(calendar_data):
    x=calendar_data;path='/api/v1/event-occurrences?from=2032-01-01&to=2032-03-31&timezone=Europe/Moscow'
    for limit in (3,60):
        with select_queries(x.engine) as queries:response=await x.client.get(path+f'&limit={limit}')
        assert response.status_code==200,response.text
        result=response.json();assert len(result['items'])==limit
        assert [UUID(row['id']) for row in result['items']]==x.event_ids[:limit]
        assert not set(x.foreign_ids)&{UUID(row['id']) for row in result['items']}
        assert result['next_cursor']==(str(x.event_ids[2]) if limit==3 else None)
        assert len(queries)==11
    next_page=await x.client.get(path+f'&limit=3&cursor={x.event_ids[2]}')
    assert [UUID(row['id']) for row in next_page.json()['items']]==x.event_ids[3:6]
    async with x.db() as db:
        await db.execute(update(Assignment).where(Assignment.staffing_need_id==x.need_ids[(x.event_ids[0],0)],Assignment.status=='invited').values(status='confirmed',confirmed_at=utcnow()))
        await db.execute(update(PermissionGrant).where(PermissionGrant.id==x.manage_grant).values(revoked_at=utcnow()))
        await db.commit()
    current=await x.client.get(path+'&limit=3');assert current.status_code==200,current.text
    assert all(row['allowed_actions']==[] for row in current.json()['items'])
    changed=next(need for need in current.json()['items'][0]['staffing_needs'] if need['id']==str(x.need_ids[(x.event_ids[0],0)]))
    assert (changed['invited'],changed['confirmed'],changed['missing'])==(0,3,0)
    async with x.db() as db:
        await db.execute(update(PermissionGrant).where(PermissionGrant.id==x.read_grant).values(revoked_at=utcnow()));await db.commit()
    assert (await x.client.get(path+'&limit=3')).status_code==403
