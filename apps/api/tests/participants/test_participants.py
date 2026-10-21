"""Real PostgreSQL tests. Own disposable database only; no SQLite ACL substitutes."""
import os
from datetime import date, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import get_principal, issue_session
from app.core.clock import utcnow
from app.core.db import Base, get_db
from app.core.errors import ApiError
from app.core.models import Foundation, PermissionGrant, StaffMembership, User
from app.modules.participants.models import GroupMembership, Participant, ParticipantGroup, ParticipantPrivateNote
from app.modules.participants.router import router

DSN=os.environ.get("OPORA_PARTICIPANTS_TEST_DATABASE_URL")
pytestmark=pytest.mark.skipif(not DSN, reason="Set OPORA_PARTICIPANTS_TEST_DATABASE_URL to dedicated PostgreSQL16 test DB")


@pytest_asyncio.fixture
async def env(tmp_path):
    assert DSN and DSN.rsplit('/',1)[-1] == 'opora_participants_test', 'Refuse non-dedicated database'
    engine=create_async_engine(DSN)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    sessions=async_sessionmaker(engine,expire_on_commit=False)
    app=FastAPI()
    app.include_router(router)
    from app.modules.assets.router import router as assets_router
    app.include_router(assets_router)
    from app.core.config import get_settings
    original_asset_root=get_settings().asset_root
    get_settings().asset_root=str(tmp_path)
    @app.exception_handler(ApiError)
    async def handle(request:Request, error:ApiError):
        return JSONResponse(status_code=error.status_code,content={"code":error.code,"message":error.message})
    async def db_override():
        async with sessions() as db:
            try: yield db
            except BaseException:
                await db.rollback()
                raise
    app.dependency_overrides[get_db]=db_override
    foundation_id=uuid4()
    async with sessions() as db:
        db.add(Foundation(id=foundation_id,name='Test foundation'))
        await db.flush()
        admin=User(foundation_id=foundation_id,display_name='Coordinator')
        leader=User(foundation_id=foundation_id,display_name='Leader')
        volunteer=User(foundation_id=foundation_id,display_name='Volunteer')
        db.add_all([admin,leader,volunteer]);await db.flush()
        am=StaffMembership(foundation_id=foundation_id,user_id=admin.id)
        lm=StaffMembership(foundation_id=foundation_id,user_id=leader.id)
        db.add_all([am,lm]);await db.flush()
        for perm in ('participants.read','participants.write','participants.private_notes','groups.read','groups.write'):
            db.add(PermissionGrant(membership_id=am.id,permission=perm))
        await db.commit()
        users={'admin':admin.id,'leader':leader.id,'volunteer':volunteer.id}
        leader_membership_id=lm.id
    clients={}
    # Use genuine opaque-cookie sessions and current DB grants on every request.
    from starlette.responses import Response
    for role,user_id in users.items():
        async with sessions() as db:
            response=Response()
            # issue_session uses configured foundation; fixtures use same setting below.
            from app.core.config import get_settings
            settings=get_settings(); previous=settings.foundation_id;settings.foundation_id=foundation_id
            try: _,csrf=await issue_session(db,response,user_id=user_id,mfa_at=utcnow() if role!='volunteer' else None)
            finally: settings.foundation_id=previous
            await db.commit()
            cookie=response.headers['set-cookie'].split(';',1)[0].split('=',1)[1]
        clients[role]=AsyncClient(transport=ASGITransport(app=app),base_url='http://testserver',cookies={'opora_session':cookie},headers={'Origin':'http://testserver','X-CSRF-Token':csrf})
    yield sessions,clients,foundation_id,users,leader_membership_id
    for client in clients.values():await client.aclose()
    get_settings().asset_root=original_asset_root
    await engine.dispose()


async def mutate(client,path,body,method='POST',key=None):
    return await client.request(method,path,json=body,headers={'Idempotency-Key':key or str(uuid4())})


async def setup_people(env):
    _,clients,_,users,_=env
    c=clients['admin']
    a=(await mutate(c,'/api/v1/coord/participants',{'display_name':'Alice','support':'Offer a quiet space'})).json()
    b=(await mutate(c,'/api/v1/coord/participants',{'display_name':'Boris'})).json()
    g1=(await mutate(c,'/api/v1/coord/groups',{'title':'Group one','leader_id':str(users['leader'])})).json()
    g2=(await mutate(c,'/api/v1/coord/groups',{'title':'Group two'})).json()
    for group,participant in ((g1,a),(g2,b)):
        result=await mutate(c,f"/api/v1/coord/groups/{group['id']}/memberships",{'participant_id':participant['id'],'valid_from':'2020-01-01','expected_version':group['version']})
        assert result.status_code==200,result.text
        group['version']=result.json()['group_version']
    return a,b,g1,g2


@pytest.mark.asyncio
async def test_private_fields_scoped_leader_and_staff_revocation(env):
    sessions,clients,foundation,users,lm_id=env
    a,b,g1,g2=await setup_people(env)
    assert (await mutate(clients['admin'],f"/api/v1/coord/participants/{a['id']}/private-notes",{'text':'SECRET PRIVATE NOTE'})).status_code==200
    # leader sees only own current group and cannot access separate private endpoint.
    result=await clients['leader'].get('/api/v1/coord/participants')
    assert [p['display_name'] for p in result.json()['items']]==['Alice']
    assert 'SECRET' not in result.text and 'private' not in result.text
    assert (await clients['leader'].get(f"/api/v1/coord/participants/{b['id']}")).status_code==404
    assert (await clients['leader'].get(f"/api/v1/coord/participants/{a['id']}/private-notes")).status_code==403
    assert (await clients['leader'].get(f"/api/v1/coord/groups/{g2['id']}")).status_code==404
    assert 'SECRET' not in (await clients['admin'].get(f"/api/v1/coord/groups/{g1['id']}")).text
    assert (await clients['admin'].get('/api/v1/coord/participants?query=SECRET')).json()['items']==[]
    async with sessions() as db:
        membership=await db.get(StaffMembership,lm_id);membership.revoked_at=utcnow();await db.commit()
    assert (await clients['leader'].get('/api/v1/coord/participants')).status_code==403
    assert (await clients['leader'].get(f"/api/v1/coord/participants/{a['id']}")).status_code==404


@pytest.mark.asyncio
async def test_interval_overlap_history_and_optimistic_lock(env):
    _,clients,_,_,_=env
    a,b,g1,g2=await setup_people(env);c=clients['admin']
    same={'participant_id':a['id'],'valid_from':'2021-01-01','expected_version':g1['version']}
    assert (await mutate(c,f"/api/v1/coord/groups/{g1['id']}/memberships",same)).status_code==409
    original=(await c.get(f"/api/v1/coord/groups/{g1['id']}?at=2020-01-02")).json()['members'][0]
    ended=await mutate(c,f"/api/v1/coord/groups/{g1['id']}/memberships/{original['id']}",{'valid_until':'2022-01-01','expected_version':g1['version']},'PATCH')
    assert ended.status_code==200,ended.text
    adjacent=await mutate(c,f"/api/v1/coord/groups/{g1['id']}/memberships",{'participant_id':a['id'],'valid_from':'2022-01-01','expected_version':ended.json()['group_version']})
    assert adjacent.status_code==200,adjacent.text
    old=(await c.get(f"/api/v1/coord/groups/{g1['id']}?at=2021-01-01")).json()['members']
    new=(await c.get(f"/api/v1/coord/groups/{g1['id']}?at=2022-01-01")).json()['members']
    assert len(old)==len(new)==1 and old[0]['id']!=new[0]['id']
    stale=await mutate(c,f"/api/v1/coord/participants/{a['id']}",{'display_name':'Changed','expected_version':99},'PATCH')
    assert stale.status_code==409


@pytest.mark.asyncio
async def test_volunteer_default_deny_and_idempotency(env):
    _,clients,_,_,_=env
    a,b,g1,g2=await setup_people(env);v=clients['volunteer'];c=clients['admin']
    assert (await v.get('/api/v1/coord/participants')).status_code==403
    assert (await v.get(f"/api/v1/coord/participants/{a['id']}/photo")).status_code==404
    assignment=str(uuid4())
    assert (await v.get(f'/api/v1/me/assignments/{assignment}/participants')).status_code==403
    assert (await v.get(f"/api/v1/me/assignments/{assignment}/participants/{a['id']}/photo")).status_code==403
    key=str(uuid4());body={'display_name':'Idempotent participant'}
    first=await mutate(c,'/api/v1/coord/participants',body,key=key)
    retry=await mutate(c,'/api/v1/coord/participants',body,key=key)
    assert first.status_code==retry.status_code==200 and first.json()['id']==retry.json()['id']
    conflict=await mutate(c,'/api/v1/coord/participants',{'display_name':'Other payload'},key=key)
    assert conflict.status_code==409


@pytest.mark.asyncio
async def test_photo_quarantine_preserves_previous_and_revoked_owner_denied(env):
    import hashlib
    import io
    from PIL import Image
    sessions,clients,_,users,_=env
    c=clients['admin']
    image=io.BytesIO();Image.new('RGB',(3,3),(200,100,0)).save(image,format='PNG');data=image.getvalue()
    intent=await mutate(c,'/api/v1/assets/upload-intents',{'content_type':'image/png','expected_size':len(data),'checksum':hashlib.sha256(data).hexdigest()})
    assert intent.status_code==200,intent.text
    asset=intent.json()['id']
    uploading=await c.patch(f'/api/v1/assets/{asset}/upload',content=data,headers={'X-Upload-Offset':'0','Content-Type':'application/octet-stream'})
    assert uploading.status_code==200,uploading.text
    assert (await mutate(c,f'/api/v1/assets/{asset}/complete-upload',{})).status_code==200
    person=(await mutate(c,'/api/v1/coord/participants',{'display_name':'Photo person','photo_asset_id':asset})).json()
    photo=await c.get(f"/api/v1/coord/participants/{person['id']}/photo")
    assert photo.status_code==200 and photo.content==data and 'no-store' in photo.headers['cache-control']
    bad=(await mutate(c,'/api/v1/assets/upload-intents',{'content_type':'image/png','expected_size':9,'checksum':hashlib.sha256(b'not image').hexdigest()})).json()['id']
    await c.patch(f'/api/v1/assets/{bad}/upload',content=b'not image',headers={'X-Upload-Offset':'0','Content-Type':'application/octet-stream'})
    assert (await mutate(c,f'/api/v1/assets/{bad}/complete-upload',{})).status_code==422
    failed=await mutate(c,f"/api/v1/coord/participants/{person['id']}",{'display_name':'Photo person','photo_asset_id':bad,'expected_version':person['version']},'PATCH')
    assert failed.status_code==409
    assert (await c.get(f"/api/v1/coord/participants/{person['id']}")).json()['photo_asset_id']==asset
    async with sessions() as db:
        staff=await db.scalar(select(StaffMembership).where(StaffMembership.user_id==users['admin']))
        staff.revoked_at=utcnow();await db.commit()
    assert (await c.get(f"/api/v1/coord/participants/{person['id']}/photo")).status_code==404
    # Upload ownership cannot bypass the participant's current access after attachment.
    assert (await c.get(f'/api/v1/assets/{asset}/content')).status_code==404


@pytest.mark.asyncio
async def test_cross_foundation_is_never_visible_and_scoped_leader_cannot_reassign(env):
    sessions,clients,_,users,_=env
    a,b,g1,g2=await setup_people(env)
    async with sessions() as db:
        other=Foundation(name='Another foundation');db.add(other);await db.flush()
        person=Participant(foundation_id=other.id,display_name='Foreign participant')
        db.add(person);await db.commit();foreign_id=person.id
    assert (await clients['admin'].get(f'/api/v1/coord/participants/{foreign_id}')).status_code==404
    attempt=await mutate(clients['leader'],f"/api/v1/coord/groups/{g1['id']}",{'title':'Group one','leader_id':str(users['admin']),'expected_version':g1['version']},'PATCH')
    assert attempt.status_code==403
