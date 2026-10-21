"""Run against a disposable PostgreSQL database; each test uses its own schema."""
import asyncio
import os
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.db import Base
from app.core.auth import Principal
from app.core.models import Foundation, User, Session, StaffMembership, PermissionGrant, ResourceReservation
from app.core.errors import ApiError
from app.modules.applications.models import Application,FormVersion,ApplicationRevision
from app.modules.interviews.models import InterviewBooking, InterviewResult, InterviewPrivateNote, AvailabilitySeries
from app.modules.interviews import router as handlers
from app.modules.interviews.schemas import WindowInput, BookingInput, MoveInput, PauseCommand, CompleteInput
from app.modules.interviews.recurrence import expand, local_instant
from app.modules.crm.models import FollowUpTask,FollowUpSource,CrmVolunteer
from app.modules.interviews import service

@pytest.fixture
async def world():
    url=os.environ.get('OPORA_TEST_DATABASE_URL')
    if not url: pytest.skip('OPORA_TEST_DATABASE_URL must point to disposable PostgreSQL')
    engine=create_async_engine(url)
    schema='interviews_'+uuid4().hex
    async with engine.begin() as c:
        await c.execute(text('CREATE EXTENSION IF NOT EXISTS btree_gist'))
        await c.execute(text(f'CREATE SCHEMA "{schema}"'))
    await engine.dispose()
    engine=create_async_engine(url,connect_args={'options':f'-csearch_path={schema}'})
    factory=async_sessionmaker(engine,expire_on_commit=False)
    async with engine.begin() as c: await c.run_sync(Base.metadata.create_all)
    async with factory() as db:
        foundation=Foundation(name='Interview tests');db.add(foundation);await db.flush()
        form=FormVersion(foundation_id=foundation.id,version=1,content={});db.add(form);await db.flush()
        coordinator=User(foundation_id=foundation.id,display_name='Test coordinator');db.add(coordinator);await db.flush()
        membership=StaffMembership(foundation_id=foundation.id,user_id=coordinator.id);db.add(membership);await db.flush()
        db.add(PermissionGrant(membership_id=membership.id,permission='interviews.manage'))
        people=[]
        for i in range(3):
            user=User(foundation_id=foundation.id,display_name=f'Candidate {i}');db.add(user);await db.flush()
            app=Application(foundation_id=foundation.id,user_id=user.id,submission_state='submitted');db.add(app);await db.flush()
            revision=ApplicationRevision(application_id=app.id,form_version_id=form.id,number=1,answers={'firstName':f'Candidate {i}','lastName':'Fixture'},author_id=str(user.id));db.add(revision);await db.flush();app.submitted_revision_id=revision.id
            people.append((user,app))
        def session(user,staff=False):
            row=Session(foundation_id=foundation.id,user_id=user.id,token_hash=uuid4().hex,csrf_hash=uuid4().hex,csrf_cipher='test',expires_at=datetime.now(timezone.utc)+timedelta(days=1),mfa_at=datetime.now(timezone.utc) if staff else None)
            db.add(row);return row
        staff_session=session(coordinator,True);sessions=[session(u) for u,a in people];await db.flush()
        staff=Principal(coordinator.id,None,foundation.id,staff_session.id,True,str(coordinator.id),frozenset({'interviews.manage'}),(('interviews.manage','foundation',None),))
        candidates=[Principal(u.id,None,foundation.id,s.id,False,str(u.id)) for (u,a),s in zip(people,sessions)]
        await db.commit()
    yield SimpleNamespace(factory=factory,staff=staff,candidates=candidates,applications=[a for u,a in people],foundation=foundation)
    await engine.dispose()
    cleanup=create_async_engine(url)
    async with cleanup.begin() as c: await c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    await cleanup.dispose()

async def create_window(w,day=None,**overrides):
    day=day or date.today()+timedelta(days=10)
    payload=dict(local_start_date=day,start_minute=600,end_minute=720,venue='Test online',recurrence='once',duration_minutes=30,buffer_after_minutes=10)
    payload.update(overrides)
    async with w.factory() as db:return await handlers.create_window(WindowInput(**payload),db,w.staff,uuid4().hex)

async def slots(w,day):
    async with w.factory() as db:
        result=await service.materialize(db,w.staff,day,day);await db.commit();return result

async def book(w,p,slot,key=None):
    async with w.factory() as db:return await handlers.book(BookingInput(slot_id=slot['id'],slot_version=slot['version']),db,p,key or uuid4().hex)

@pytest.mark.asyncio
async def test_race_idempotency_failed_move_pause_and_private_result(world):
    w=world;day=date.today()+timedelta(days=10)
    window=await create_window(w,day);choices=await slots(w,day)
    outcomes=await asyncio.gather(*(book(w,p,choices[0]) for p in w.candidates[:2]),return_exceptions=True)
    assert sum(isinstance(x,dict) for x in outcomes)==1
    loser=next(x for x in outcomes if isinstance(x,ApiError));assert loser.status_code==409
    winner=next(i for i,x in enumerate(outcomes) if isinstance(x,dict));p=w.candidates[winner];booking=outcomes[winner]
    second=await book(w,w.candidates[2],choices[1],key='replay')
    assert await book(w,w.candidates[2],choices[1],key='replay')==second
    with pytest.raises(ApiError) as different:await book(w,w.candidates[2],choices[2],key='replay')
    assert different.value.code=='idempotency_payload_conflict'
    async with w.factory() as db:
        with pytest.raises(ApiError):await handlers.move(booking['id'],MoveInput(slot_id=choices[1]['id'],slot_version=choices[1]['version'],expected_version=1),db,p,uuid4().hex)
    async with w.factory() as db:
        unchanged=await db.get(InterviewBooking,booking['id']);assert str(unchanged.slot_id)==booking['slot_id'] and unchanged.version==1
        with pytest.raises(ApiError) as foreign:await service.get_booking(db,w.candidates[2],booking['id'],lock=True)
        assert foreign.value.status_code==404
    async with w.factory() as db:await handlers.pause_window(window['id'],PauseCommand(expected_version=1,active=False),db,w.staff,uuid4().hex)
    assert await slots(w,day)==[]
    async with w.factory() as db:
        preserved=await db.get(InterviewBooking,booking['id']);assert preserved.status=='booked'
        # Finishing fixture moves the persisted interval into the past, never the wall clock.
        preserved.starts_at=datetime.now(timezone.utc)-timedelta(hours=2);preserved.ends_at=datetime.now(timezone.utc)-timedelta(hours=1);preserved.busy_until=preserved.ends_at
        await db.commit()
    async with w.factory() as db:
        await handlers.complete(booking['id'],CompleteInput(expected_version=1,outcome='Next step',public_agreement='Public agreement',private_note='Private sensitive note'),db,w.staff,uuid4().hex)
    async with w.factory() as db:
        row=await service.get_booking(db,p,booking['id']);self_view=await service.booking_view(db,row);staff_view=await service.booking_view(db,row,True)
        assert 'private_note' not in self_view and 'Private sensitive note' not in str(self_view)
        assert staff_view['private_note']=='Private sensitive note'
        assert self_view['result']['public_agreement']=='Public agreement'

@pytest.mark.asyncio
async def test_global_reservations_conflict_rolls_back_booking_and_unpause_version(world):
    w=world;day=date.today()+timedelta(days=13);window=await create_window(w,day);choices=await slots(w,day)
    p=w.candidates[0]
    async with w.factory() as db:
        db.add(ResourceReservation(foundation_id=p.foundation_id,user_id=p.user_id,owner_key='user:'+str(p.user_id),source_type='assignment',source_id=uuid4(),starts_at=datetime.fromisoformat(choices[0]['starts_at']),busy_until=datetime.fromisoformat(choices[0]['ends_at']),active=True));await db.commit()
    with pytest.raises(ApiError) as conflict:await book(w,p,choices[0])
    assert conflict.value.status_code==409
    async with w.factory() as db:assert not await db.scalar(select(InterviewBooking.id).where(InterviewBooking.user_id==p.user_id))
    async with w.factory() as db:await handlers.pause_window(window['id'],PauseCommand(expected_version=1,active=False),db,w.staff,uuid4().hex)
    async with w.factory() as db:
        with pytest.raises(ApiError) as stale:await handlers.pause_window(window['id'],PauseCommand(expected_version=1,active=True),db,w.staff,uuid4().hex)
        assert stale.value.code=='version_conflict'


def test_multiweek_exceptions_buffer_and_dst():
    s=SimpleNamespace(local_start_date=date(2026,10,19),last_date=None,recurrence='weekly',interval_weeks=2,weekdays=[0,2],start_minute=600,end_minute=720,timezone='Europe/Moscow',duration_minutes=30,buffer_after_minutes=10)
    slots=list(expand(s,date(2026,10,19),date(2026,11,4),[SimpleNamespace(origin_date=date(2026,10,21),kind='skip')]))
    assert len(slots)==9
    assert {x[0] for x in slots}=={date(2026,10,19),date(2026,11,2),date(2026,11,4)}
    assert (slots[1][2]-slots[0][2]).total_seconds()==40*60
    assert local_instant(date(2026,3,29),150,'Europe/Berlin') is None
    assert local_instant(date(2026,10,25),150,'Europe/Berlin').hour==0

@pytest.mark.asyncio
async def test_edit_exception_rejects_affected_booking_and_zone_boundaries(world):
    from app.modules.interviews.schemas import ExceptionCommand,WindowUpdate
    w=world;day=date.today()+timedelta(days=18)
    window=await create_window(w,day,start_minute=30,end_minute=90,duration_minutes=30,buffer_after_minutes=0)
    # 00:30 Moscow belongs to the previous Berlin local day.
    async with w.factory() as db:
        berlin=await service.materialize(db,w.staff,day-timedelta(days=1),day-timedelta(days=1),'Europe/Berlin');await db.commit()
        assert len(berlin)==2
    choices=await slots(w,day);booking=await book(w,w.candidates[0],choices[0])
    async with w.factory() as db:
        with pytest.raises(ApiError) as affected:
            await handlers.exception(window['id'],ExceptionCommand(expected_version=1,origin_date=day,kind='skip'),db,w.staff,uuid4().hex)
        assert affected.value.code=='affected_bookings'
    async with w.factory() as db:
        preserved=await db.get(InterviewBooking,booking['id']);series=await db.get(AvailabilitySeries,window['id'])
        assert preserved.status=='booked' and series.version==1
    body=WindowUpdate(**{k:v for k,v in window.items() if k not in {'id','version','coordinator_id','exceptions'}},expected_version=1)
    body.venue='New room'
    async with w.factory() as db:
        with pytest.raises(ApiError) as affected:
            await handlers.edit_window(window['id'],body,db,w.staff,uuid4().hex)
        assert affected.value.code=='affected_bookings'
    # A separate open slot can be selected and changes retain one stable booking ID.
    async with w.factory() as db:
        moved=await handlers.move(booking['id'],MoveInput(slot_id=choices[1]['id'],slot_version=choices[1]['version'],expected_version=1),db,w.candidates[0],uuid4().hex)
        assert moved['id']==booking['id'] and moved['version']==2 and moved['slot_id']==choices[1]['id']

@pytest.mark.asyncio
async def test_revoked_staff_cannot_replay_or_change_availability(world):
    from sqlalchemy import update
    w=world;day=date.today()+timedelta(days=19)
    async with w.factory() as db:
        body=WindowInput(local_start_date=day,start_minute=600,end_minute=660,venue='Room')
        result=await handlers.create_window(body,db,w.staff,'staff-replay')
    async with w.factory() as db:
        await db.execute(update(PermissionGrant).values(revoked_at=datetime.now(timezone.utc)));await db.commit()
    async with w.factory() as db:
        with pytest.raises(ApiError) as denied:await handlers.create_window(body,db,w.staff,'staff-replay')
        assert denied.value.status_code==403

@pytest.mark.asyncio
async def test_result_follow_up_create_change_clear_no_contact_and_receipt_replay(world):
    from sqlalchemy import func
    w=world;day=date.today()+timedelta(days=25)
    await create_window(w,day);choice=(await slots(w,day))[0]
    booking=await book(w,w.candidates[0],choice)
    async with w.factory() as db:
        row=await db.get(InterviewBooking,booking['id']);row.starts_at=datetime.now(timezone.utc)-timedelta(hours=2);row.ends_at=row.starts_at+timedelta(minutes=30);row.busy_until=row.ends_at
        await db.commit()
    async def complete(version,due,key=None):
        async with w.factory() as db:return await handlers.complete(booking['id'],CompleteInput(expected_version=version,outcome='Follow up',public_agreement='Agreement',private_note='Private only',next_contact_date=due),db,w.staff,key or uuid4().hex)
    first_date=date.today()+timedelta(days=3)
    first=await complete(1,first_date,'complete-once')
    replay=await complete(1,first_date,'complete-once');assert replay==first
    async with w.factory() as db:
        result=await db.scalar(select(InterviewResult).where(InterviewResult.booking_id==booking['id']))
        result_id=result.id
        tasks=(await db.scalars(select(FollowUpTask).where(FollowUpTask.source_id==result_id))).all()
        assert len(tasks)==1 and tasks[0].state=='open' and tasks[0].due_on==first_date
        assert tasks[0].assigned_user_id==w.staff.user_id and tasks[0].source_revision==2
        assert (await db.scalar(select(CrmVolunteer).where(CrmVolunteer.application_id==w.applications[0].id))).relationship_state=='unverified'
    moved_date=first_date+timedelta(days=2)
    changed=await complete(2,moved_date);assert changed['version']==3
    async with w.factory() as db:
        tasks=(await db.scalars(select(FollowUpTask).where(FollowUpTask.source_id==result_id).order_by(FollowUpTask.source_revision))).all()
        assert [t.state for t in tasks]==['cancelled','open'] and tasks[1].due_on==moved_date
    cleared=await complete(3,None);assert cleared['version']==4
    async with w.factory() as db:
        assert not await db.scalar(select(FollowUpTask.id).where(FollowUpTask.source_id==result_id,FollowUpTask.state=='open'))
        source=await db.scalar(select(FollowUpSource).where(FollowUpSource.source_id==result_id));assert source.current_revision==4 and source.task_id is None
        volunteer=await db.scalar(select(CrmVolunteer).where(CrmVolunteer.application_id==w.applications[0].id));volunteer.no_contact=True;await db.commit()
    suppressed=await complete(4,moved_date);assert suppressed['version']==5
    async with w.factory() as db:
        assert await db.scalar(select(func.count()).select_from(FollowUpTask).where(FollowUpTask.source_id==result_id))==2
        source=await db.scalar(select(FollowUpSource).where(FollowUpSource.source_id==result_id));assert source.current_revision==5 and source.task_id is None
        public=await service.booking_view(db,await db.get(InterviewBooking,booking['id']))
        assert 'Private only' not in str(public) and 'volunteer_id' not in str(public) and 'assigned_user_id' not in str(public)
    with pytest.raises(ApiError) as stale:await complete(3,first_date)
    assert stale.value.code=='version_conflict'
    async with w.factory() as db:
        source=await db.scalar(select(FollowUpSource).where(FollowUpSource.source_id==result_id));source.current_revision=99;await db.commit()
    with pytest.raises(ApiError) as fenced:await complete(5,first_date)
    assert fenced.value.code=='stale_follow_up_source'
    async with w.factory() as db:
        unchanged=await db.get(InterviewBooking,booking['id']);result=await db.scalar(select(InterviewResult).where(InterviewResult.id==result_id))
        assert unchanged.version==5 and result.next_contact_date==moved_date
