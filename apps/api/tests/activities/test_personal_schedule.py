"""Personal schedule never uses the staff calendar permission or a global event list."""
from datetime import datetime,timedelta,timezone
from uuid import UUID
import pytest
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.models import RegistrationSession,Session,User
from app.modules.activities.calendar_models import EventOccurrence
from .test_p07 import context,headers
from .test_p09 import setup,invite_approve,user_headers


@pytest.mark.asyncio
async def test_own_schedule_window_states_pagination_and_foreign_scope(context):
    event,need,user1,user2,_=await setup(context,capacity=2)
    own=await invite_approve(context,need,user1)
    other=await invite_approve(context,need,user2)
    # An event crossing midnight belongs to both overlapping requested day windows.
    async with context.db() as db:
        row=await db.get(EventOccurrence,UUID(event['id']))
        row.starts_at=datetime(2034,3,31,20,30,tzinfo=timezone.utc) # 23:30 Moscow
        row.ends_at=datetime(2034,3,31,22,0,tzinfo=timezone.utc)
        foreign=User(foundation_id=context.other.id,display_name='Other foundation user');db.add(foreign);await db.flush()
        db.add(Session(foundation_id=context.other.id,user_id=foreign.id,token_hash=digest('foreign'),csrf_hash=digest('foreign-csrf'),csrf_cipher='unused',expires_at=utcnow()+timedelta(hours=1)))
        await db.commit()
    async def get(query,actor='self'):
        return await context.client.get('/api/v1/me/schedule?'+query,headers={'Cookie':'opora_session='+actor})
    for day in ['2034-03-31','2034-04-01']:
        result=await get(f'from={day}&to={day}&state=active')
        assert result.status_code==200,result.text
        assert [item['id'] for item in result.json()['items']]==[own['id']]
        assert result.json()['items'][0]['occurrence_status']=='scheduled'
    assert (await get('from=2034-03-30&to=2034-03-30')).json()['items']==[]
    assert (await get('from=2034-03-31&to=2034-04-01','foreign')).json()['items']==[]
    # A normal volunteer can read own dates but cannot query the staff/global calendar.
    assert (await context.client.get('/api/v1/event-occurrences?from=2034-03-31&to=2034-04-01',headers={'Cookie':'opora_session=self'})).status_code==403
    assert (await context.client.get(f"/api/v1/assignments/{other['id']}",headers={'Cookie':'opora_session=self'})).status_code==404
    cancelled=await context.client.post(f"/api/v1/assignments/{own['id']}/decline",headers=user_headers(),json={'expected_version':own['version'],'reason':'  Не смогу прийти: болезнь '})
    assert cancelled.status_code==200
    # The volunteer's reason reaches the coordinator through the assignment history.
    assert cancelled.json()['history'][-1]['reason']=='Не смогу прийти: болезнь'
    assert (await get('from=2034-03-31&to=2034-04-01&state=active')).json()['items']==[]
    inactive=(await get('from=2034-03-31&to=2034-04-01&state=cancelled')).json()['items']
    assert len(inactive)==1 and inactive[0]['status']=='declined'
    # The other volunteer receives only their own record, despite sharing the event.
    second=(await get('from=2034-03-31&to=2034-04-01','second')).json()['items']
    assert [item['id'] for item in second]==[other['id']]
    # Multiple cursor pages contain only own records and do not truncate the period.
    later=await context.client.post('/api/v1/coord/event-occurrences',headers=headers(),json={'title':'Другой выход','start_date':'2034-04-01','start_time':'16:00','timezone':'Europe/Moscow','duration_minutes':60,'location':'Другая мастерская','staffing_needs':[{'role_id':need['role_id'],'capacity_required':1}]})
    assert later.status_code==200,later.text
    later_own=await invite_approve(context,later.json()['staffing_needs'][0],user1)
    page=(await get('from=2034-03-31&to=2034-04-01&limit=1')).json()
    assert len(page['items'])==1 and page['next_cursor']
    final=(await get('from=2034-03-31&to=2034-04-01&limit=1&cursor='+page['next_cursor'])).json()
    assert len(final['items'])==1 and final['next_cursor'] is None
    assert {page['items'][0]['id'],final['items'][0]['id']}=={own['id'],later_own['id']}
    event_cancel=await context.client.post(f"/api/v1/coord/event-occurrences/{event['id']}/cancel",headers=headers(),json={'expected_version':event['version']})
    assert event_cancel.status_code==200,event_cancel.text
    second=(await get('from=2034-03-31&to=2034-04-01&state=cancelled','second')).json()['items']
    assert second[0]['occurrence_status']=='cancelled' and second[0]['status']=='cancelled'


@pytest.mark.asyncio
async def test_schedule_validates_range_timezone_and_requires_verified_user(context):
    event,need,user1,_,_=await setup(context)
    for query in ['from=2034-02-01&to=2034-01-01','from=2034-01-01&to=2036-01-01','from=bad&to=2034-01-01','from=2034-01-01&to=2034-01-01&timezone=Invalid/Zone','from=2034-01-01&to=2034-01-01&state=other']:
        response=await context.client.get('/api/v1/me/schedule?'+query,headers={'Cookie':'opora_session=self'})
        assert response.status_code==422,response.text
    async with context.db() as db:
        registration=RegistrationSession(foundation_id=context.foundation.id,expires_at=utcnow()+timedelta(hours=1));db.add(registration);await db.flush()
        db.add(Session(foundation_id=context.foundation.id,registration_id=registration.id,token_hash=digest('limited'),csrf_hash=digest('limited-csrf'),csrf_cipher='unused',expires_at=utcnow()+timedelta(hours=1)));await db.commit()
    denied=await context.client.get('/api/v1/me/schedule?from=2034-01-01&to=2034-01-01',headers={'Cookie':'opora_session=limited'})
    assert denied.status_code==403 and denied.json()['code']=='user_required'
