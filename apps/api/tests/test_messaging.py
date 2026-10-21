import asyncio
import hashlib
import io
from uuid import UUID, uuid4
import httpx
import pyotp
import pytest
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import func, select
from app.cli import fixtures
from app.core.clock import utcnow
from app.core.crypto import unseal
from app.core.db import SessionLocal
from app.core.models import MfaFactor, OutboxMessage
from app.core.platform import install_platform
from app.modules.auth.router import router as auth_router
from app.modules.assets.router import router as asset_router
from app.modules.messaging.router import router as messaging_router
from app.modules.messaging.models import Message
from app.modules.messaging.consumers import enqueue_notice, deliver_internal
from test_platform import login

@pytest.fixture
def app():
    app=FastAPI()
    install_platform(app)
    for router in (auth_router,asset_router,messaging_router):
        app.include_router(router)
    return app

async def actor(client,email,staff=False):
    session,_=await login(client,email)
    headers={'Origin':'http://testserver','X-CSRF-Token':session['csrf_token'],'Idempotency-Key':uuid4().hex}
    if staff:
        async with SessionLocal() as db:
            factor=await db.scalar(select(MfaFactor).where(MfaFactor.user_id==UUID(session['user_id'])))
            factor.last_counter=-1
            secret=unseal(factor.secret_cipher)
            await db.commit()
        response=await client.post('/api/v1/auth/mfa/verify',json={'code':pyotp.TOTP(secret).now()},headers=headers)
        assert response.status_code==200,response.text
        session=response.json()
        headers['X-CSRF-Token']=session['csrf_token']
    return session,headers

@pytest.mark.asyncio
async def test_two_real_sessions_send_sync_unread_replay_and_member_revoke(app):
    await fixtures()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as staff,httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as candidate,httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as stranger:
        ss,sh=await actor(staff,'coordinator@example.test',True)
        cs,ch=await actor(candidate,f'messaging-{uuid4().hex}@example.test')
        await actor(stranger,f'outsider-{uuid4().hex}@example.test')
        created=await staff.post('/api/v1/conversations',json={'title':'Тестовая группа','member_ids':[cs['user_id']]},headers=sh)
        assert created.status_code==200,created.text
        conversation=created.json()
        cid=conversation['id']
        assert (await stranger.get(f'/api/v1/conversations/{cid}')).status_code==404
        assert (await stranger.get(f'/api/v1/conversations/{cid}/sync')).status_code==404
        sent=await candidate.post(f'/api/v1/conversations/{cid}/messages',json={'text':'Готовлюсь к встрече'},headers=ch)
        assert sent.status_code==200,sent.text
        replay=await candidate.post(f'/api/v1/conversations/{cid}/messages',json={'text':'Готовлюсь к встрече'},headers=ch)
        assert replay.json()['id']==sent.json()['id']
        conflict=await candidate.post(f'/api/v1/conversations/{cid}/messages',json={'text':'Другой текст'},headers=ch)
        assert conflict.status_code==409
        sync=(await staff.get(f'/api/v1/conversations/{cid}/sync?after_seq=0')).json()
        assert sync['conversation']['unread_count']==1 and len(sync['messages'])==1
        read=await staff.put(f'/api/v1/conversations/{cid}/read-cursor',json={'last_read_seq':sent.json()['seq']},headers=sh)
        assert read.json()['unread_count']==0
        stale=await staff.put(f'/api/v1/conversations/{cid}/read-cursor',json={'last_read_seq':0},headers=sh)
        assert stale.json()['last_read_seq']==sent.json()['seq']
        current=(await staff.get(f'/api/v1/conversations/{cid}')).json()
        sh['Idempotency-Key']=uuid4().hex
        revoked=await staff.post(f'/api/v1/conversations/{cid}/members/revoke',json={'user_id':cs['user_id'],'expected_version':current['version']},headers=sh)
        assert revoked.status_code==200,revoked.text
        # A known receipt is not an authorization credential after membership is revoked.
        assert (await candidate.post(f'/api/v1/conversations/{cid}/messages',json={'text':'Готовлюсь к встрече'},headers=ch)).status_code==404
        assert (await candidate.get(f'/api/v1/conversations/{cid}/messages')).status_code==404

@pytest.mark.asyncio
async def test_attachment_permission_link_and_photo_clearance(app):
    await fixtures()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as staff,httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as candidate:
        ss,sh=await actor(staff,'coordinator@example.test',True)
        cs,ch=await actor(candidate,f'photo-{uuid4().hex}@example.test')
        response=await candidate.post('/api/v1/conversations/direct',json={'recipient_id':ss['user_id']},headers=ch)
        assert response.status_code==200,response.text
        cid=response.json()['id']
        image=io.BytesIO()
        Image.new('RGB',(3,3),'green').save(image,format='PNG')
        data=image.getvalue()
        response=await candidate.post('/api/v1/assets/upload-intents',json={'content_type':'image/png','expected_size':len(data),'checksum':hashlib.sha256(data).hexdigest()},headers=ch)
        aid=response.json()['id']
        await candidate.patch(f'/api/v1/assets/{aid}/upload',content=data,headers={**ch,'X-Upload-Offset':'0'})
        await candidate.post(f'/api/v1/assets/{aid}/complete-upload',headers=ch)
        ch['Idempotency-Key']=uuid4().hex
        blocked=await candidate.post(f'/api/v1/conversations/{cid}/messages',json={'text':'Изображение','asset_ids':[aid]},headers=ch)
        assert blocked.status_code==422,blocked.text
        ch['Idempotency-Key']=uuid4().hex
        sent=await candidate.post(f'/api/v1/conversations/{cid}/messages',json={'text':'Изображение без людей','asset_ids':[aid],'photo_policy':'no_people'},headers=ch)
        assert sent.status_code==200,sent.text
        assert (await staff.get(f'/api/v1/conversations/assets/{aid}/content')).content==data
        assert (await candidate.get(f'/api/v1/assets/{aid}/content')).status_code==404
        messages=(await staff.get(f'/api/v1/conversations/{cid}/messages?limit=1')).json()
        assert messages['items'][0]['assets'][0]['id']==aid

@pytest.mark.asyncio
async def test_internal_outbox_consumer_is_atomic_deduplicated_and_readonly(app):
    seed=await fixtures()
    recipient=UUID(seed['identities']['candidate-two@example.test']['user_id'])
    async with SessionLocal() as db:
        outbox=enqueue_notice(db,UUID(seed['foundation_id']),recipient,'Проверка','Настоящее внутреннее уведомление')
        await db.flush()
        state=await deliver_internal(db,outbox,{'recipient_id':str(recipient),'subject':'Проверка','text':'Настоящее внутреннее уведомление'})
        assert state=='delivered'
        assert await deliver_internal(db,outbox,{'recipient_id':str(recipient),'text':'duplicate'})=='delivered'
        assert await db.scalar(select(func.count()).select_from(Message).where(Message.source_outbox_id==outbox.id))==1
        await db.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
        session,headers=await actor(client,'candidate-two@example.test')
        page=(await client.get('/api/v1/conversations')).json()
        inbox=next(c for c in page['items'] if c['kind']=='system')
        assert inbox['allowed_actions']==[] and inbox['external_delivery']=='unavailable'
        assert (await client.post(f"/api/v1/conversations/{inbox['id']}/messages",json={'text':'reply'},headers=headers)).status_code==403

@pytest.mark.asyncio
async def test_cancelled_or_replaced_booking_version_never_delivers_stale_notice():
    from datetime import timedelta
    from app.modules.applications.models import Application
    from app.modules.interviews.models import AvailabilitySeries,InterviewSlot,InterviewBooking
    from app.worker.queue import enqueue_outbox
    seed=await fixtures()
    foundation=UUID(seed['foundation_id'])
    user=UUID(seed['identities']['candidate-one@example.test']['user_id'])
    coordinator=UUID(seed['identities']['coordinator@example.test']['user_id'])
    now=utcnow()+timedelta(days=90)
    async with SessionLocal() as db:
        application=await db.scalar(select(Application).where(Application.user_id==user))
        if application is None:
            application=Application(foundation_id=foundation,user_id=user)
            db.add(application)
            await db.flush()
        series=AvailabilitySeries(foundation_id=foundation,coordinator_id=coordinator,local_start_date=now.date(),start_minute=600,end_minute=660,venue='Учебная площадка')
        db.add(series)
        await db.flush()
        slot=InterviewSlot(foundation_id=foundation,series_id=series.id,coordinator_id=coordinator,origin_date=now.date(),origin_minute=600,starts_at=now,ends_at=now+timedelta(minutes=30),busy_until=now+timedelta(minutes=40))
        db.add(slot)
        await db.flush()
        booking=InterviewBooking(foundation_id=foundation,application_id=application.id,user_id=user,candidate_key='user:'+str(user),slot_id=slot.id,coordinator_id=coordinator,starts_at=now,ends_at=slot.ends_at,busy_until=slot.busy_until,venue='Учебная площадка',status='cancelled',version=2)
        db.add(booking)
        await db.flush()
        stale={'event':'interview.booked','booking_id':str(booking.id),'booking_version':1,'user_id':str(user)}
        outbox=enqueue_outbox(db,foundation,'internal',stale)
        await db.flush()
        assert await deliver_internal(db,outbox,stale)=='suppressed_stale'
        assert await db.scalar(select(func.count()).select_from(Message).where(Message.source_outbox_id==outbox.id))==0
        latest={'event':'interview.cancelled','booking_id':str(booking.id),'booking_version':2,'user_id':str(coordinator)}
        # The envelope owner can be stale; current booking identity is authoritative.
        assert await deliver_internal(db,outbox,latest)=='delivered'
        message=await db.scalar(select(Message).where(Message.source_outbox_id==outbox.id))
        from app.modules.messaging.models import ConversationMember
        recipient=await db.scalar(select(ConversationMember.user_id).where(ConversationMember.conversation_id==message.conversation_id))
        assert recipient==user
        await db.rollback()

@pytest.mark.asyncio
async def test_two_concurrent_outbox_consumers_persist_one_message():
    seed=await fixtures()
    recipient=UUID(seed['identities']['candidate-two@example.test']['user_id'])
    payload={'recipient_id':str(recipient),'subject':'Конкурентная проверка','text':'Один факт'}
    async with SessionLocal() as db:
        outbox=enqueue_notice(db,UUID(seed['foundation_id']),recipient,payload['subject'],payload['text'])
        await db.flush()
        oid=outbox.id
        await db.commit()
    async def consume():
        async with SessionLocal() as db:
            message=await db.get(OutboxMessage,oid)
            state=await deliver_internal(db,message,payload)
            await db.commit()
            return state
    assert await asyncio.gather(consume(),consume())==['delivered','delivered']
    async with SessionLocal() as db:
        assert await db.scalar(select(func.count()).select_from(Message).where(Message.source_outbox_id==oid))==1

@pytest.mark.asyncio
async def test_no_contact_prevents_even_queued_in_app_notice():
    from app.modules.crm.models import CrmVolunteer
    seed=await fixtures()
    recipient=UUID(seed['identities']['candidate-two@example.test']['user_id'])
    async with SessionLocal() as db:
        record=await db.scalar(select(CrmVolunteer).where(CrmVolunteer.user_id==recipient,CrmVolunteer.merged_into_id.is_(None)))
        if record is None:
            record=CrmVolunteer(foundation_id=UUID(seed['foundation_id']),user_id=recipient,display_name='Opt-out fixture',no_contact=True)
            db.add(record)
        else:
            record.no_contact=True
        outbox=enqueue_notice(db,UUID(seed['foundation_id']),recipient,'Старое приглашение','Не должно появиться')
        await db.flush()
        assert await deliver_internal(db,outbox,{'recipient_id':str(recipient),'subject':'Старое приглашение','text':'Не должно появиться'})=='suppressed_no_contact'
        assert await db.scalar(select(func.count()).select_from(Message).where(Message.source_outbox_id==outbox.id))==0
        await db.rollback()
