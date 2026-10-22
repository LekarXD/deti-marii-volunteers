"""P10B uses genuine P09 invite/approve/confirm commands and opaque-cookie sessions."""
from datetime import date
from types import SimpleNamespace
from uuid import UUID
import hashlib
import io

from PIL import Image
import pytest
import pytest_asyncio
from sqlalchemy import select, text

from app.core.clock import utcnow
from app.core.models import PermissionGrant, Session, StaffMembership, User
from app.modules.activities.assignment_service import ActivityAssignmentAccess
from app.modules.activities.router import router as activities_router
from app.modules.participants.access import get_assignment_access
from app.modules.participants.models import GroupMembership, Participant, ParticipantBriefing
from .test_participants import env, mutate


@pytest_asyncio.fixture
async def assigned(env):
    sessions, clients, foundation, users, _ = env
    # The P10A app still uses real get_principal/get_db. Only the concrete P09 adapter
    # is injected, exactly as A0 does in app.main; no ownership/auth override is used.
    app = clients['admin']._transport.app
    app.include_router(activities_router, prefix='/api/v1')
    app.dependency_overrides[get_assignment_access] = ActivityAssignmentAccess
    async with sessions() as db:
        admin_membership = await db.scalar(select(StaffMembership).where(StaffMembership.user_id == users['admin']))
        for permission in ('roles.manage', 'schedule.manage', 'schedule.read', 'assignments.manage', 'assets.manage'):
            db.add(PermissionGrant(membership_id=admin_membership.id, permission=permission))
        # This volunteer also has active staff and upload ownership. Neither grants
        # participant data or bypasses current assignment ownership/state.
        dual = StaffMembership(foundation_id=foundation, user_id=users['volunteer'])
        db.add(dual); await db.flush()
        db.add(PermissionGrant(membership_id=dual.id, permission='assignments.manage'))
        for session in (await db.scalars(select(Session).where(Session.user_id == users['volunteer']))).all():
            session.mfa_at = utcnow()
        await db.commit()
    admin=clients['admin']; first=clients['volunteer']; second=clients['leader']
    async def create(path, body, client=admin):
        response=await mutate(client, '/api/v1'+path, body)
        assert response.status_code==200,response.text
        return response.json()
    group_a=await create('/coord/groups', {'title':'Первая группа'})
    group_b=await create('/coord/groups', {'title':'Вторая группа'})
    a=await create('/coord/participants', {'display_name':'Участник первой группы','about':'Любит рисовать','communication':'Дайте время ответить','support':'Предложите тихое место','interests':'Краски','communication_tags':['Давать время ответить'],'support_tags':['Тихий угол при перегрузке'],'interests_tags':['Рисование']})
    b=await create('/coord/participants', {'display_name':'Участник второй группы','communication':'Короткие понятные просьбы'})
    ended=await create('/coord/participants', {'display_name':'Период завершён в день занятия'})
    future=await create('/coord/participants', {'display_name':'Начинает на следующий день'})
    starts=await create('/coord/participants', {'display_name':'Начинает в день занятия'})
    await create(f"/coord/participants/{a['id']}/private-notes", {'text':'PRIVATE NOTE A: never in a volunteer projection'})
    async with sessions() as db:
        membership=GroupMembership(foundation_id=foundation,group_id=UUID(group_a['id']),participant_id=UUID(a['id']),valid_from=date(2028,1,2),valid_until=date(2028,1,4))
        db.add_all([membership,
            GroupMembership(foundation_id=foundation,group_id=UUID(group_a['id']),participant_id=UUID(ended['id']),valid_from=date(2020,1,1),valid_until=date(2028,1,3)),
            GroupMembership(foundation_id=foundation,group_id=UUID(group_a['id']),participant_id=UUID(future['id']),valid_from=date(2028,1,4)),
            GroupMembership(foundation_id=foundation,group_id=UUID(group_b['id']),participant_id=UUID(b['id']),valid_from=date(2020,1,1)),
            GroupMembership(foundation_id=foundation,group_id=UUID(group_a['id']),participant_id=UUID(starts['id']),valid_from=date(2028,1,3),valid_until=date(2028,1,4))])
        await db.commit()
    image=io.BytesIO(); Image.new('RGB',(4,4),(30,130,100)).save(image,format='PNG'); image_data=image.getvalue()
    asset=await create('/assets/upload-intents',{'content_type':'image/png','expected_size':len(image_data),'checksum':hashlib.sha256(image_data).hexdigest()},first)
    uploaded=await first.patch(f"/api/v1/assets/{asset['id']}/upload",content=image_data,headers={'X-Upload-Offset':'0','Content-Type':'application/octet-stream'})
    assert uploaded.status_code==200,uploaded.text
    await create(f"/assets/{asset['id']}/complete-upload",{},first)
    attached=await mutate(admin,f"/api/v1/coord/participants/{a['id']}",{'display_name':a['display_name'],'about':a['about'],'communication':a['communication'],'support':a['support'],'interests':a['interests'],'communication_tags':a['communication_tags'],'support_tags':a['support_tags'],'interests_tags':a['interests_tags'],'photo_asset_id':asset['id'],'expected_version':a['version']},'PATCH')
    assert attached.status_code==200,attached.text
    a=attached.json()
    role=await create('/coord/roles',{'title':'Помощник ведущей','task':'Поддержать участников','preparation_defaults':[]})
    async def event(group, day):
        # Local Jan 3 in Auckland is Jan 2 UTC. The captured roster must use the
        # occurrence timezone and start-inclusive/end-exclusive membership dates.
        return await create('/coord/event-occurrences',{'title':'Творческое занятие','group_id':group['id'],'start_date':day,'start_time':'00:30','timezone':'Pacific/Auckland','duration_minutes':90,'location':'Мастерская','staffing_needs':[{'role_id':role['id'],'capacity_required':1,'preparation_requirements':[]}]})
    event_a=await event(group_a,'2028-01-03');event_b=await event(group_b,'2028-01-04')
    async def invite(event,user):
        need=event['staffing_needs'][0]
        item=await create(f"/coord/staffing-needs/{need['id']}/invitations",{'expected_version':need['version'],'user_id':str(user)})
        return await create(f"/coord/assignments/{item['id']}/approve",{'expected_version':item['version'],'reason':'Условия согласованы.'})
    assignment_a=await invite(event_a,users['volunteer']); assignment_b=await invite(event_b,users['leader'])
    async def confirm(client,item):
        return await create(f"/assignments/{item['id']}/confirm",{'expected_version':item['version']},client)
    yield SimpleNamespace(sessions=sessions,clients=clients,admin=admin,first=first,second=second,foundation=foundation,users=users,
        a=a,b=b,ended=ended,future=future,starts=starts,group_a=group_a,group_b=group_b,membership_id=membership.id,
        image_data=image_data,asset=asset,event_a=event_a,event_b=event_b,assignment_a=assignment_a,assignment_b=assignment_b,
        create=create,confirm=confirm)


def paths(item,participant):
    root=f"/api/v1/me/assignments/{item['id']}"
    return root+'/participants',root+'/group-briefing',root+f"/participants/{participant['id']}/photo"


async def assert_closed(client,item,participant,status):
    for path in paths(item,participant):
        response=await client.get(path)
        assert response.status_code==status,(path,response.text)


@pytest.mark.asyncio
async def test_real_confirmed_assignment_safe_photo_and_frozen_local_date_roster(assigned):
    x=assigned
    await assert_closed(x.first,x.assignment_a,x.a,403) # approved is not confirmed
    confirmed=await x.confirm(x.first,x.assignment_a)
    await x.confirm(x.second,x.assignment_b)
    listing,briefing,photo=paths(confirmed,x.a)
    result=await x.first.get(listing)
    assert result.status_code==200,result.text
    assert {item['id'] for item in result.json()['items']}=={x.a['id'],x.starts['id']}
    assert 'no-store' in result.headers['cache-control']
    assert 'PRIVATE NOTE' not in result.text and 'private_note' not in result.text and 'author_id' not in result.text
    group=await x.first.get(briefing)
    assert group.status_code==200 and group.json()['groups']==[{'id':x.group_a['id'],'title':'Первая группа'}]
    memo=next(item for item in group.json()['items'] if item['id']==x.a['id'])
    assert (memo['communication_tags'],memo['support_tags'],memo['interests_tags'])==(['Давать время ответить'],['Тихий угол при перегрузке'],['Рисование'])
    assert 'PRIVATE NOTE' not in group.text and 'Вторая группа' not in group.text
    image=await x.first.get(photo)
    assert image.status_code==200 and image.content==x.image_data and 'no-store' in image.headers['cache-control']
    await assert_closed(x.second,confirmed,x.a,404)
    await assert_closed(x.admin,confirmed,x.a,404) # staff is not assignment ownership
    wrong=await x.first.get(f"/api/v1/me/assignments/{confirmed['id']}/participants/{x.b['id']}/photo")
    assert wrong.status_code==403
    assert (await x.first.get(f"/api/v1/coord/participants/{x.a['id']}")).status_code==404
    assert (await x.first.get(f"/api/v1/assets/{x.asset['id']}/content")).status_code==404 # upload ownership cannot bypass attachment ACL
    # Change group history after confirmation through the real membership commands.
    shortened=await mutate(x.admin,f"/api/v1/coord/groups/{x.group_a['id']}/memberships/{x.membership_id}",{'valid_until':'2028-01-03','expected_version':1},'PATCH')
    assert shortened.status_code==200,shortened.text
    late=await x.create('/coord/participants',{'display_name':'Добавлен после подтверждения'})
    await x.create(f"/coord/groups/{x.group_a['id']}/memberships",{'participant_id':late['id'],'valid_from':'2020-01-01','expected_version':shortened.json()['group_version']})
    current=await x.admin.get(f"/api/v1/coord/groups/{x.group_a['id']}?at=2028-01-03")
    assert {member['participant_id'] for member in current.json()['members']}=={late['id'],x.starts['id']}
    frozen=await x.first.get(listing)
    assert {item['id'] for item in frozen.json()['items']}=={x.a['id'],x.starts['id']}
    assert (await x.first.get(photo)).status_code==200
    # Unconfirm through real cancellation; the current JSON and file path close together.
    cancelled=await x.create(f"/assignments/{confirmed['id']}/cancel",{'expected_version':confirmed['version']},x.first)
    await assert_closed(x.first,cancelled,x.a,403)
    assert (await x.first.get(f"/api/v1/assets/{x.asset['id']}/content")).status_code==404


@pytest.mark.asyncio
async def test_ward_card_lists_upcoming_group_sessions_with_their_volunteers(assigned):
    x=assigned
    upcoming=await x.admin.get(f"/api/v1/coord/participants/{x.a['id']}/occurrences")
    assert upcoming.status_code==200,upcoming.text
    [session]=upcoming.json()['items']
    assert (session['id'],session['group_title'],session['timezone'])==(x.event_a['id'],'Первая группа','Pacific/Auckland')
    assert [v['display_name'] for v in session['volunteers']]==['Volunteer']
    # The membership must cover the session's local date (start inclusive, end exclusive).
    for outside in (x.future,x.ended):
        assert (await x.admin.get(f"/api/v1/coord/participants/{outside['id']}/occurrences")).json()['items']==[]
    assert [s['id'] for s in (await x.admin.get(f"/api/v1/coord/participants/{x.starts['id']}/occurrences")).json()['items']]==[x.event_a['id']]
    assert [s['id'] for s in (await x.admin.get(f"/api/v1/coord/participants/{x.b['id']}/occurrences")).json()['items']]==[x.event_b['id']]
    await x.create(f"/coord/event-occurrences/{x.event_a['id']}/cancel",{'expected_version':x.event_a['version']})
    assert (await x.admin.get(f"/api/v1/coord/participants/{x.a['id']}/occurrences")).json()['items']==[]


@pytest.mark.asyncio
async def test_event_cancel_and_account_revocation_close_every_projection(assigned):
    x=assigned
    confirmed=await x.confirm(x.first,x.assignment_a)
    assert (await x.first.get(paths(confirmed,x.a)[2])).status_code==200
    cancelled=await x.create(f"/coord/event-occurrences/{x.event_a['id']}/cancel",{'expected_version':x.event_a['version']})
    await assert_closed(x.first,confirmed,x.a,403)
    # A separate valid volunteer/group remains independent.
    other=await x.confirm(x.second,x.assignment_b)
    assert (await x.second.get(paths(other,x.b)[0])).json()['items'][0]['id']==x.b['id']
    async with x.sessions() as db:
        user=await db.get(User,x.users['leader']);user.account_state='paused';await db.commit()
    await assert_closed(x.second,other,x.b,401)


@pytest.mark.asyncio
async def test_compound_foreign_keys_reject_cross_foundation_photo_and_group_staff(env):
    from uuid import uuid4
    from sqlalchemy.exc import IntegrityError
    from app.core.models import Foundation, MediaAsset
    from app.modules.participants.models import ParticipantGroup
    sessions, _, foundation, _, _ = env
    async with sessions() as db:
        other = Foundation(name='Another foundation for scope checks');db.add(other);await db.flush()
        user = User(foundation_id=other.id,display_name='Other foundation staff');db.add(user);await db.flush()
        asset = MediaAsset(foundation_id=other.id,owner_user_id=user.id,storage_key=uuid4().hex,content_type='image/png',expected_size=1,checksum='0'*64,state='ready')
        db.add(asset);await db.commit()
    invalid = [Participant(foundation_id=foundation,display_name='Wrong photo scope',photo_asset_id=asset.id),
               ParticipantGroup(foundation_id=foundation,title='Wrong leader scope',leader_id=user.id),
               ParticipantGroup(foundation_id=foundation,title='Wrong coordinator scope',coordinator_id=user.id)]
    for row in invalid:
        async with sessions() as db:
            db.add(row)
            with pytest.raises(IntegrityError):await db.flush()
            await db.rollback()
