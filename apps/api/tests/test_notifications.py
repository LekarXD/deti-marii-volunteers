import asyncio
import hashlib
import hmac
import json
import time
from datetime import timedelta
from uuid import UUID,uuid4
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func,select
from app.cli import fixtures
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.crypto import digest
from app.core.db import SessionLocal
from app.core.models import AuthChallenge,Job,OutboxMessage,User
from app.core.platform import install_platform
from app.modules.auth.router import router as auth_router
from app.modules.notifications.router import router as notification_router
from app.modules.notifications.models import DeliveryAttempt,NotificationDelivery
from app.modules.notifications.delivery import process_email,process_internal
from app.modules.messaging.models import Message
from app.worker.queue import enqueue_outbox
from test_messaging import actor

@pytest.fixture
def app():
    app=FastAPI()
    install_platform(app)
    app.include_router(auth_router)
    app.include_router(notification_router)
    return app

@pytest.mark.asyncio
async def test_template_preview_rechecks_optout_and_confirmed_send_replays_once(app):
    seed=await fixtures()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as staff,httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as candidate:
        ss,sh=await actor(staff,'coordinator@example.test',True)
        cs,ch=await actor(candidate,f'notification-{uuid4().hex}@example.test')
        invalid=await staff.post('/api/v1/coord/notification-templates',json={'key':'bad-'+uuid4().hex,'channel':'in_app','subject':'Привет','body':'{volunteer_name.__class__}'},headers=sh)
        assert invalid.status_code==422
        sh['Idempotency-Key']=uuid4().hex
        created=await staff.post('/api/v1/coord/notification-templates',json={'key':'fixture-'+uuid4().hex,'channel':'in_app','subject':'Подготовка','body':'Здравствуйте, {volunteer_name}. Внутренний тест фонда.'},headers=sh)
        assert created.status_code==200,created.text
        template=created.json()
        sh['Idempotency-Key']=uuid4().hex
        published=await staff.post(f"/api/v1/coord/notification-templates/{template['id']}/publish",json={'expected_version':template['version']},headers=sh)
        assert published.status_code==200,published.text
        version=published.json()['published_version_id']
        body={'template_version_id':version,'recipient_user_ids':[cs['user_id']]}
        preview=await staff.post('/api/v1/coord/notifications/audience-preview',json=body,headers=sh)
        assert preview.status_code==200,preview.text
        assert preview.json()['eligible_count']==1
        disabled=await candidate.put('/api/v1/me/notification-preferences',json={'expected_version':0,'no_contact':True,'email_enabled':False,'in_app_enabled':True},headers=ch)
        assert disabled.status_code==200,disabled.text
        sh['Idempotency-Key']=uuid4().hex
        changed=await staff.post('/api/v1/coord/notifications/send',json={'preview_id':preview.json()['id'],'preview_hash':preview.json()['preview_hash'],'confirmed':True},headers=sh)
        assert changed.status_code==409 and changed.json()['code']=='audience_changed'
        disabled_preview=await staff.post('/api/v1/coord/notifications/audience-preview',json=body,headers=sh)
        assert disabled_preview.json()['eligible_count']==0
        ch['Idempotency-Key']=uuid4().hex
        enabled=await candidate.put('/api/v1/me/notification-preferences',json={'expected_version':1,'no_contact':False,'email_enabled':False,'in_app_enabled':True},headers=ch)
        assert enabled.status_code==200
        preview=(await staff.post('/api/v1/coord/notifications/audience-preview',json=body,headers=sh)).json()
        sh['Idempotency-Key']=uuid4().hex
        command={'preview_id':preview['id'],'preview_hash':preview['preview_hash'],'confirmed':True}
        sent=await staff.post('/api/v1/coord/notifications/send',json=command,headers=sh)
        assert sent.status_code==200,sent.text
        replay=await staff.post('/api/v1/coord/notifications/send',json=command,headers=sh)
        assert sent.json()==replay.json() and sent.json()['state']=='queued'
        async with SessionLocal() as db:
            delivery=await db.get(NotificationDelivery,UUID(sent.json()['delivery_ids'][0]))
            outbox=await db.get(OutboxMessage,delivery.outbox_id)
            job=await db.get(Job,outbox.job_id)
            from app.core.crypto import unseal
            payload=json.loads(unseal(outbox.payload_cipher))
            assert await process_internal(db,job,outbox,payload)=='delivered'
            assert await db.scalar(select(func.count()).select_from(Message).where(Message.source_outbox_id==outbox.id))==1
            await db.commit()

@pytest.mark.asyncio
async def test_actual_loopback_smtp_acceptance_and_crash_marker_prevents_resend(monkeypatch):
    seed=await fixtures()
    captured=[]
    async def smtp(reader,writer):
        async def reply(value):
            writer.write(value)
            await writer.drain()
        try:
            await reply(b'220 loopback fixture SMTP\r\n')
            while line:=await reader.readline():
                command=line.upper()
                if command.startswith(b'EHLO') or command.startswith(b'HELO'):
                    await reply(b'250 loopback-fixture\r\n')
                elif command.startswith(b'MAIL') or command.startswith(b'RCPT'):
                    await reply(b'250 OK\r\n')
                elif command.startswith(b'DATA'):
                    await reply(b'354 End with dot\r\n')
                    data=[]
                    while (part:=await reader.readline()) not in (b'.\r\n',b''):
                        data.append(part)
                    captured.append(b''.join(data))
                    await reply(b'250 accepted-by-local-fixture\r\n')
                elif command.startswith(b'QUIT'):
                    await reply(b'221 bye\r\n')
                    break
                else:
                    await reply(b'250 OK\r\n')
        finally:
            writer.close()
    server=await asyncio.start_server(smtp,'127.0.0.1',0)
    port=server.sockets[0].getsockname()[1]
    settings=get_settings()
    for key,value in {'dev_inbox':False,'smtp_host':'127.0.0.1','smtp_port':port,'smtp_starttls':False,'smtp_from':'opora@fixture.example.test'}.items():monkeypatch.setattr(settings,key,value)
    try:
        async with SessionLocal() as db:
            token='fixture-'+uuid4().hex
            challenge=AuthChallenge(foundation_id=UUID(seed['foundation_id']),normalized_contact='invented@fixture.example.test',token_hash=digest(token),purpose='login',expires_at=utcnow()+timedelta(minutes=15))
            db.add(challenge)
            await db.flush()
            payload={'purpose':'login','to':'invented@fixture.example.test','challenge_id':str(challenge.id),'token':token}
            outbox=enqueue_outbox(db,UUID(seed['foundation_id']),'email',payload)
            await db.flush()
            job=await db.get(Job,outbox.job_id)
            job.state='running';job.claim_token=uuid4();job.lease_until=utcnow()+timedelta(seconds=60);job.attempts=1
            await db.commit()
            outcome=await process_email(db,job,outbox,payload)
            assert outcome.state=='accepted'
            await db.commit()
            assert len(captured)==1 and b'Message-ID:' in captured[0]
            assert (await process_email(db,job,outbox,payload)).state=='accepted'
            assert len(captured)==1
            accepted=await db.scalar(select(NotificationDelivery).where(NotificationDelivery.outbox_id==outbox.id))
            accepted.state='delivered';accepted.last_webhook_at=int(time.time())
            await db.commit()
            assert (await process_email(db,job,outbox,payload)).state=='delivered'
            assert len(captured)==1
            other=enqueue_outbox(db,UUID(seed['foundation_id']),'email',payload)
            await db.flush()
            delivery=NotificationDelivery(foundation_id=UUID(seed['foundation_id']),outbox_id=other.id,channel='email',state='calling')
            db.add(delivery)
            await db.flush()
            db.add(DeliveryAttempt(delivery_id=delivery.id,attempt_number=1,state='calling'))
            other_job=await db.get(Job,other.job_id)
            await db.commit()
            assert (await process_email(db,other_job,other,payload)).state=='unknown'
            await db.commit()
            assert len(captured)==1
    finally:
        server.close()
        await server.wait_closed()

@pytest.mark.asyncio
async def test_webhook_signature_timestamp_and_event_replay(app,monkeypatch):
    seed=await fixtures()
    secret='fixture-webhook-only-secret-never-production'
    monkeypatch.setattr(get_settings(),'email_webhook_secret',secret)
    message_id=f'<{uuid4()}@fixture.example.test>'
    async with SessionLocal() as db:
        outbox=enqueue_outbox(db,UUID(seed['foundation_id']),'email',{'purpose':'notification'})
        await db.flush()
        delivery=NotificationDelivery(foundation_id=UUID(seed['foundation_id']),outbox_id=outbox.id,channel='email',provider_message_id=message_id,state='accepted')
        db.add(delivery)
        await db.commit()
    event={'event_id':uuid4().hex,'message_id':message_id,'state':'delivered'}
    raw=json.dumps(event,separators=(',',':')).encode()
    timestamp=str(int(time.time()))
    signature=hmac.new(secret.encode(),timestamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    headers={'Content-Type':'application/json','X-Webhook-Timestamp':timestamp,'X-Webhook-Signature':signature}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
        invalid=await client.post('/api/v1/integrations/email/webhook',content=raw,headers={**headers,'X-Webhook-Signature':'0'*64})
        assert invalid.status_code==401
        result=await client.post('/api/v1/integrations/email/webhook',content=raw,headers=headers)
        assert result.status_code==200 and result.json()['status']=='applied'
        assert (await client.post('/api/v1/integrations/email/webhook',content=raw,headers=headers)).json()['status']=='replayed'
        stale={**headers,'X-Webhook-Timestamp':str(int(timestamp)-1000)}
        assert (await client.post('/api/v1/integrations/email/webhook',content=raw,headers=stale)).status_code==401
