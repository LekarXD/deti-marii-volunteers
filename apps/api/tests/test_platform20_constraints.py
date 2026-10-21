"""Migration20 PostgreSQL authority/append-only/exclusion proofs; no external services."""
from datetime import date,datetime,timedelta,timezone,time
from uuid import uuid4
import pytest
import pytest_asyncio
from sqlalchemy import MetaData,insert,update,delete,text
from sqlalchemy.exc import IntegrityError
from app.core.db import SessionLocal
from app.core.models import Foundation,User,Session
from app.core.model_loader import load_models
from app.modules.activities.models import Opportunity,VolunteerRole,VolunteerRoleVersion
from app.modules.activities.calendar_models import EventSeries,EventOccurrence,StaffingNeed
from app.modules.activities.assignment_models import Assignment,Attendance,AttendanceEvent

@pytest_asyncio.fixture
async def scope():
    load_models()
    async with SessionLocal() as db:
        f=Foundation(name='Synthetic migration20 fixture');other=Foundation(name='Synthetic other foundation');db.add_all([f,other]);await db.flush()
        user=User(foundation_id=f.id);outsider=User(foundation_id=other.id);db.add_all([user,outsider]);await db.flush()
        login=Session(foundation_id=f.id,user_id=user.id,token_hash=uuid4().hex*2,csrf_hash='x'*64,csrf_cipher='synthetic',expires_at=datetime.now(timezone.utc)+timedelta(hours=1));db.add(login)
        opp=Opportunity(foundation_id=f.id,title='Synthetic migration scope',updated_by='fixture');db.add(opp);await db.flush()
        metadata=MetaData()
        tables=['dobro_settings','dobro_activity_links','dobro_transfers','dobro_profiles','dobro_enrollments','dobro_enrollment_events','dobro_series_opportunities','signal_rule_settings','telegram_link_tokens','telegram_bindings']
        connection=await db.connection();await connection.run_sync(lambda conn:metadata.reflect(conn,only=tables))
        yield db,metadata.tables,f,user,other,outsider,login,opp
        await db.rollback()

async def denied(db,statement,code):
    with pytest.raises(IntegrityError) as failure:
        async with db.begin_nested():await db.execute(statement)
    assert failure.value.orig.sqlstate==code

def link(f,opp,start=date(2026,10,1),end=date(2026,10,31)):
    return dict(id=uuid4(),foundation_id=f.id,opportunity_id=opp.id,url='https://dobro.ru/event/1',kind='one_off',title='Synthetic link',valid_from=start,valid_until=end,version=1,actor_id='fixture',created_at=datetime.now(timezone.utc))

@pytest.mark.asyncio
async def test_dobro_periods_are_inclusive_nonoverlapping_and_links_protected(scope):
    db,t,f,user,other,outsider,login,opp=scope;table=t['dobro_activity_links'];first=link(f,opp)
    await db.execute(insert(table).values(**first))
    await denied(db,insert(table).values(**link(f,opp,date(2026,10,31),date(2026,11,30))),'23P01')
    await db.execute(insert(table).values(**link(f,opp,date(2026,11,1),date(2026,11,30))))
    await denied(db,update(table).where(table.c.id==first['id']).values(title='Rewritten'),'23514')
    await denied(db,delete(table).where(table.c.id==first['id']),'23514')

@pytest.mark.asyncio
async def test_dobro_transfer_and_enrollment_history_are_scoped_append_only(scope):
    db,t,f,user,other,outsider,login,opp=scope;activity=link(f,opp);await db.execute(insert(t['dobro_activity_links']).values(**activity))
    transfer=dict(id=uuid4(),foundation_id=f.id,user_id=outsider.id,activity_id=activity['id'],period=date(2026,10,1),minutes_due_snapshot=60,hours_delta=1,snapshot_hash='a'*64,snapshot={},actor_id='fixture',note='',entered_at=datetime.now(timezone.utc))
    await denied(db,insert(t['dobro_transfers']).values(**transfer),'23503')
    transfer['user_id']=user.id;await db.execute(insert(t['dobro_transfers']).values(**transfer))
    await denied(db,update(t['dobro_transfers']).where(t['dobro_transfers'].c.id==transfer['id']).values(hours_delta=2),'23514')
    enrollment=uuid4();await db.execute(insert(t['dobro_enrollments']).values(id=enrollment,foundation_id=f.id,user_id=user.id,activity_id=activity['id'],state='applied',version=1,updated_at=datetime.now(timezone.utc)))
    await db.execute(insert(t['dobro_enrollment_events']).values(id=uuid4(),enrollment_id=enrollment,version=1,state='applied',actor_id='fixture',reason='',created_at=datetime.now(timezone.utc)))
    await denied(db,delete(t['dobro_enrollment_events']).where(t['dobro_enrollment_events'].c.enrollment_id==enrollment),'23514')

@pytest.mark.asyncio
async def test_telegram_token_binds_same_session_owner_and_private_active_identity(scope):
    db,t,f,user,other,outsider,login,opp=scope
    token=dict(id=uuid4(),foundation_id=other.id,user_id=outsider.id,session_id=login.id,token_hash=uuid4().hex*2,token_cipher='synthetic-encrypted-fixture',purpose='telegram_bind',expires_at=datetime.now(timezone.utc)+timedelta(minutes=10),created_at=datetime.now(timezone.utc))
    await denied(db,insert(t['telegram_link_tokens']).values(**token),'23514')
    token.update(foundation_id=f.id,user_id=user.id);await db.execute(insert(t['telegram_link_tokens']).values(**token))
    binding=dict(id=uuid4(),foundation_id=f.id,user_id=user.id,telegram_user_id=123456,chat_id=123456,version=1,verified_at=datetime.now(timezone.utc))
    await db.execute(insert(t['telegram_bindings']).values(**binding))
    await denied(db,insert(t['telegram_bindings']).values(**{**binding,'id':uuid4()}),'23505')
    await denied(db,update(t['telegram_bindings']).where(t['telegram_bindings'].c.id==binding['id']).values(chat_id=-123),'23514')

@pytest.mark.asyncio
async def test_signal_rule_owner_cannot_cross_foundation(scope):
    db,t,f,user,other,outsider,login,opp=scope
    values=dict(foundation_id=f.id,owner_user_id=outsider.id,thresholds={'miss':2,'quiet':21,'learn':14,'app':3,'shift':7},version=1,next_run_at=datetime.now(timezone.utc),last_result={})
    await denied(db,insert(t['signal_rule_settings']).values(**values),'23503')
    await db.execute(insert(t['signal_rule_settings']).values(**{**values,'owner_user_id':user.id}))

@pytest.mark.asyncio
async def test_series_mapping_cannot_change_after_real_attendance_ledger_fact(scope):
    db,t,f,user,other,outsider,login,opp=scope;now=datetime.now(timezone.utc)
    series=EventSeries(foundation_id=f.id,anchor_date=now.date(),origin_time=time(12),start_date=now.date(),start_time=time(12),duration_minutes=60,recurrence={},title='Synthetic series',updated_by='fixture');db.add(series)
    role=VolunteerRole(foundation_id=f.id,title='Synthetic role',normalized_title=uuid4().hex,updated_by='fixture');db.add(role);await db.flush()
    version=VolunteerRoleVersion(role_id=role.id,version=1,snapshot={},actor_id='fixture');db.add(version);await db.flush()
    occurrence=EventOccurrence(id=uuid4(),foundation_id=f.id,series_id=series.id,origin_local_date=now.date(),origin_local_time=time(12),starts_at=now,ends_at=now+timedelta(hours=1),timezone='Europe/Moscow',title='Synthetic occurrence',series_version=1,updated_by='fixture');db.add(occurrence);await db.flush()
    need=StaffingNeed(foundation_id=f.id,occurrence_id=occurrence.id,role_id=role.id,role_version_id=version.id,capacity_required=1);db.add(need);await db.flush()
    assignment=Assignment(foundation_id=f.id,user_id=user.id,occurrence_id=occurrence.id,staffing_need_id=need.id,conditions_version=1,conditions_snapshot={});db.add(assignment);await db.flush()
    attendance=Attendance(foundation_id=f.id,assignment_id=assignment.id,outcome='attended',minutes=60);db.add(attendance);await db.flush()
    mapping=t['dobro_series_opportunities'];await db.execute(insert(mapping).values(series_id=series.id,foundation_id=f.id,opportunity_id=opp.id,version=1,actor_id='fixture'))
    db.add(AttendanceEvent(foundation_id=f.id,attendance_id=attendance.id,assignment_id=assignment.id,user_id=user.id,version=1,old_minutes=0,new_minutes=60,reason='Synthetic fact',actor_id='fixture'));await db.flush()
    await denied(db,update(mapping).where(mapping.c.series_id==series.id).values(version=2),'23514')
    await denied(db,delete(mapping).where(mapping.c.series_id==series.id),'23514')
    # The ledger trigger takes the same foundation key as editable-link commands.
    async with SessionLocal() as observer:
        available=await observer.scalar(text('SELECT pg_try_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'dobro:{f.id}'})
        assert available is False
        await observer.rollback()
    activity=link(f,opp,now.date()-timedelta(days=1),now.date()+timedelta(days=2))
    await db.execute(insert(t['dobro_activity_links']).values(**activity))
    await denied(db,update(t['dobro_activity_links']).where(t['dobro_activity_links'].c.id==activity['id']).values(version=2,url='https://dobro.ru/event/2'),'23514')


@pytest.mark.asyncio
async def test_unused_link_edits_require_version_then_lock_after_enrollment(scope):
    db,t,f,user,other,outsider,login,opp=scope;table=t['dobro_activity_links'];activity=link(f,opp)
    await db.execute(insert(table).values(**activity))
    await db.execute(update(table).where(table.c.id==activity['id']).values(version=2,url='https://dobro.ru/event/2'))
    await db.execute(insert(t['dobro_enrollments']).values(id=uuid4(),foundation_id=f.id,user_id=user.id,activity_id=activity['id'],state='applied',version=1,updated_at=datetime.now(timezone.utc)))
    await denied(db,update(table).where(table.c.id==activity['id']).values(version=3,url='https://dobro.ru/event/3'),'23514')
    await denied(db,delete(table).where(table.c.id==activity['id']),'23514')

@pytest.mark.asyncio
async def test_enabled_dobro_reminders_require_same_foundation_owner(scope):
    db,t,f,user,other,outsider,login,opp=scope;table=t['dobro_settings']
    values=dict(foundation_id=f.id,organization_url='',registration_url='',verified=False,monthly_day=5,hard_deadline_days=60,risk_days=7,whole_hours=True,rules_confirmed=False,reminder_template='Synthetic template',version=1,updated_by='fixture')
    await db.execute(insert(table).values(**values))
    await denied(db,update(table).where(table.c.foundation_id==f.id).values(reminders_enabled=True),'23514')
    await denied(db,update(table).where(table.c.foundation_id==f.id).values(reminders_enabled=True,reminder_owner_user_id=outsider.id),'23503')
    await db.execute(update(table).where(table.c.foundation_id==f.id).values(reminders_enabled=True,reminder_owner_user_id=user.id))
