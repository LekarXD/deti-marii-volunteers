import json
from uuid import UUID,uuid4
import httpx
import pytest
from sqlalchemy import select
from app.cli import fixtures
from app.core.db import SessionLocal
from app.core.crypto import unseal
from app.core.models import ContactChannel,OutboxMessage,Session
from test_notifications import app
from test_messaging import actor

async def proof(challenge_id):
    async with SessionLocal() as db:
        rows=(await db.scalars(select(OutboxMessage).order_by(OutboxMessage.created_at.desc()).limit(50))).all()
        return next(p for p in (json.loads(unseal(r.payload_cipher)) for r in rows) if p.get('challenge_id')==challenge_id)['token']

@pytest.mark.asyncio
async def test_contact_change_binds_identity_rotates_sessions_and_refuses_collision(app):
    await fixtures()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as owner,httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as other:
        old_email=f'contact-owner-{uuid4().hex}@example.test'
        second_email=f'contact-other-{uuid4().hex}@example.test'
        one,headers=await actor(owner,old_email)
        two,other_headers=await actor(other,second_email)
        new_email=f'replacement-{uuid4().hex}@example.test'
        requested=await owner.post('/api/v1/auth/contact-change',json={'email':new_email},headers=headers)
        assert requested.status_code==200,requested.text
        challenge_id=requested.json()['challenge_id']
        token=await proof(challenge_id)
        stolen=await other.post('/api/v1/auth/contact-change/verify',json={'challenge_id':challenge_id,'token':token},headers=other_headers)
        assert stolen.status_code==400
        changed=await owner.post('/api/v1/auth/contact-change/verify',json={'challenge_id':challenge_id,'token':token},headers=headers)
        assert changed.status_code==200,changed.text
        assert changed.json()['user_id']==one['user_id'] and changed.json()['csrf_token']!=one['csrf_token']
        headers['X-CSRF-Token']=changed.json()['csrf_token']
        replay=await owner.post('/api/v1/auth/contact-change/verify',json={'challenge_id':challenge_id,'token':token},headers=headers)
        assert replay.status_code==400
        collision=await owner.post('/api/v1/auth/contact-change',json={'email':second_email},headers=headers)
        assert collision.status_code==200
        collision_id=collision.json()['challenge_id']
        refused=await owner.post('/api/v1/auth/contact-change/verify',json={'challenge_id':collision_id,'token':await proof(collision_id)},headers=headers)
        assert refused.status_code==409 and refused.json()['code']=='contact_unavailable'
        async with SessionLocal() as db:
            assert await db.scalar(select(ContactChannel.user_id).where(ContactChannel.normalized_value==new_email))==UUID(one['user_id'])
            assert await db.scalar(select(ContactChannel.user_id).where(ContactChannel.normalized_value==second_email))==UUID(two['user_id'])
            sessions=(await db.scalars(select(Session).where(Session.user_id==UUID(one['user_id'])))).all()
            assert len([s for s in sessions if s.revoked_at is None])==1
