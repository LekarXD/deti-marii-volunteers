"""Private bytes and session scope survive the trusted /deti-marii strip proxy."""
import hashlib
import io
import json
from uuid import uuid4
import httpx
import pytest
from fastapi import FastAPI
from PIL import Image
from sqlalchemy import select
from app.cli import fixtures
from app.core.config import get_settings
from app.core.crypto import unseal
from app.core.db import SessionLocal
from app.core.models import OutboxMessage
from app.core.platform import install_platform
from app.modules.auth.router import router as auth
from app.modules.assets.router import router as assets
from test_mount_prefix import StripProxy


@pytest.mark.asyncio
async def test_prefixed_private_bytes_ignore_forwarded_prefix_and_revoke_on_logout(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, 'app_mount_prefix', '/deti-marii')
    monkeypatch.setattr(settings, 'cookie_secure', True)
    monkeypatch.setattr(settings, 'trusted_origins', ['https://www.odschool.ru'])
    await fixtures()
    app = FastAPI()
    install_platform(app)
    app.include_router(auth)
    app.include_router(assets)
    transport = httpx.ASGITransport(app=StripProxy(app))
    prefix = '/deti-marii/api/v1'
    async with httpx.AsyncClient(transport=transport, base_url='https://www.odschool.ru') as owner, httpx.AsyncClient(transport=transport, base_url='https://www.odschool.ru') as stranger:
        response = await owner.get(prefix + '/auth/session')
        assert response.status_code == 200
        assert 'Path=/deti-marii;' in response.headers['set-cookie']
        await stranger.get(prefix + '/auth/session')
        headers = {'Origin':'https://www.odschool.ru', 'X-CSRF-Token':response.json()['csrf_token'], 'X-Forwarded-Prefix':'/foreign-app'}
        # Uploads need a verified account; sign the owner in through the normal email challenge.
        challenge = await owner.post(prefix + '/auth/challenges', json={'email':f'owner-{uuid4().hex}@example.test'}, headers=headers)
        assert challenge.status_code == 200, challenge.text
        async with SessionLocal() as db:
            token = next(p['token'] for p in (json.loads(unseal(row.payload_cipher)) for row in (await db.scalars(select(OutboxMessage))).all()) if p.get('challenge_id') == challenge.json()['challenge_id'])
        verified = await owner.post(prefix + '/auth/challenges/verify', json={'challenge_id':challenge.json()['challenge_id'], 'token':token}, headers=headers)
        assert verified.status_code == 200, verified.text
        headers['X-CSRF-Token'] = verified.json()['csrf_token']
        buffer = io.BytesIO()
        Image.new('RGB', (2, 2), 'blue').save(buffer, format='PNG')
        data = buffer.getvalue()
        response = await owner.post(prefix + '/assets/upload-intents', json={'content_type':'image/png', 'expected_size':len(data), 'checksum':hashlib.sha256(data).hexdigest()}, headers=headers)
        assert response.status_code == 200, response.text
        upload = response.json()['upload_url']
        assert upload.startswith(prefix + '/assets/') and '/foreign-app/' not in upload
        response = await owner.patch(upload, content=data, headers={**headers, 'X-Upload-Offset':'0'})
        assert response.status_code == 200, response.text
        base = upload.removesuffix('/upload')
        response = await owner.post(base + '/complete-upload', headers=headers)
        assert response.status_code == 200 and response.json()['state'] == 'ready', response.text
        assert (await owner.get(base + '/content')).content == data
        assert (await stranger.get(base + '/content')).status_code == 404
        response = await owner.post(prefix + '/auth/logout', headers=headers)
        assert response.status_code == 200
        assert 'Path=/deti-marii;' in response.headers['set-cookie'] and 'Max-Age=0' in response.headers['set-cookie']
        assert (await owner.get(base + '/content')).status_code == 401
