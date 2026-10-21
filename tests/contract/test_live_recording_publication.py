"""Independent live-binding -> reviewed learning publication boundary.

Authentication and authoring use ordinary HTTP, with no principal overrides.
The completed-render row is an explicit media-worker output fixture: default CI
uses synthetic DB bytes; the optional local run imports hashed native MP4 bytes.
Neither mode claims to execute browser capture inside this PostgreSQL test.
"""
import hashlib
import os
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pyotp
import pytest
from sqlalchemy import func, select

from app.cli import fixtures
from app.core.auth import resolve_principal
from app.core.clock import utcnow
from app.core.crypto import digest, seal
from app.core.db import SessionLocal
from app.core.models import ContactChannel, Job, MediaAsset, MfaFactor, PermissionGrant, Session, StaffMembership, User
from app.main import create_app
from app.integrations.rtc.livekit import LiveKitAdapter, identity
from app.modules.assets.service import asset_path
from app.modules.learning.models import Lesson, LessonVersion
from app.modules.recordings.capture import CaptureSettings
from app.modules.recordings.models import RecordingProject, RecordingPublication, RecordingRenderVersion, RecordingTake
from app.modules.recordings.service import stable_hash
from app.modules.studio import service as studio
from app.modules.studio.models import StudioSession, Webinar
from test_platform import login


@pytest.mark.asyncio
async def test_live_take_requires_exact_review_and_lesson_review_before_publication(monkeypatch):
    seed = await fixtures()
    fid, uid = UUID(seed['foundation_id']), uuid4()
    secret = pyotp.random_base32()
    email = 'independent-live-' + uuid4().hex + '@example.test'
    async with SessionLocal() as db:
        db.add(User(id=uid, foundation_id=fid, display_name='Synthetic independent live host'))
        await db.flush()
        db.add(ContactChannel(user_id=uid, normalized_value=email, verified_at=utcnow()))
        member = StaffMembership(foundation_id=fid, user_id=uid)
        db.add(member)
        await db.flush()
        for permission in ('studio.manage', 'recordings.manage', 'recordings.review', 'recordings.publish',
                           'learning.read', 'learning.write', 'learning.publish'):
            db.add(PermissionGrant(membership_id=member.id, permission=permission))
        db.add(MfaFactor(user_id=uid, secret_cipher=seal(secret), confirmed_at=utcnow(), last_counter=-1))
        await db.commit()

    app = create_app()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as client:
        session, _ = await login(client, email)
        headers = {'Origin': 'http://testserver', 'X-CSRF-Token': session['csrf_token']}

        async def request(method, path, body=None, key=None):
            return await client.request(method, '/api/v1' + path, json=body,
                                        headers={**headers, 'Idempotency-Key': key or uuid4().hex})

        async def ok(method, path, body=None, key=None):
            response = await request(method, path, body, key)
            assert response.status_code in (200, 201), response.text
            return response.json()

        assured = await ok('POST', '/auth/mfa/verify', {'code': pyotp.TOTP(secret).now()})
        headers['X-CSRF-Token'] = assured['csrf_token']
        assert assured['is_staff'] and 'recordings.publish' in assured['permissions']

        track = await ok('POST', '/coord/learning/tracks', {'key': 'qa-live-' + uuid4().hex, 'title': 'Synthetic live publication'})
        lesson = await ok('POST', '/coord/learning/lessons', {'key': 'qa-live', 'title': 'Original synthetic lesson', 'track_id': track['id']})
        lid, tid = lesson['id'], track['id']
        lesson = await ok('PUT', f'/coord/learning/lessons/{lid}/draft', {
            'expected_version': lesson['draft']['version'], 'title': 'Original synthetic lesson', 'minutes': 1,
            'source': 'Independent QA fixture', 'blocks': [{'type': 'text', 'title': 'Original', 'text': 'Preserve original lesson text.'}],
        })
        lesson = await ok('POST', f'/coord/learning/lessons/{lid}/review', {'expected_version': lesson['draft']['version']})

        async def publication_body(current_lesson):
            current_track = await ok('GET', f'/coord/learning/tracks/{tid}')
            return {'expected_version': current_track['version'], 'lesson_ids': [lid],
                    'lesson_draft_versions': {lid: current_lesson['draft']['version']},
                    'lesson_publication_revisions': {lid: current_lesson['publication_revision']}}

        baseline = await ok('POST', f'/coord/learning/tracks/{tid}/publish', await publication_body(lesson))
        lesson = await ok('GET', f'/coord/learning/lessons/{lid}')
        old_primary = lesson['current_version_id']

        async with SessionLocal() as db:
            auth_session = await db.scalar(select(Session).where(Session.token_hash == digest(client.cookies.get('opora_session'))))
            principal = await resolve_principal(db, auth_session)
            webinar = Webinar(foundation_id=fid, host_user_id=uid, title='Synthetic current live room', starts_at=utcnow(), state='published')
            db.add(webinar)
            await db.flush()
            room, _ = await studio.create_session(db, principal, 'live_event', webinar.id)
            room.state = 'live'
            await db.commit()
            wid, sid = webinar.id, room.id
        project = await ok('POST', f'/webinars/{wid}/recording-project', {'studio_session_id': str(sid), 'expected_scene_revision': 0})
        assert project['mode'] == 'live' and project['studio_session_id'] == str(sid)
        project = await ok('PATCH', f"/recording-projects/{project['id']}", {'expected_version': project['version'], 'target_lesson_id': lid})
        take = await ok('POST', f"/recording-projects/{project['id']}/takes", {'expected_version': project['version'], 'expected_scene_revision': 0})
        host_identity = identity(uid)

        async def provider_participants(self, room_name):
            return [{'identity': host_identity, 'tracks': [{'sid': 'TR_QA_live_audio', 'source': 'MICROPHONE'}]}]

        monkeypatch.setattr(LiveKitAdapter, 'participants', provider_participants)
        monkeypatch.setattr(CaptureSettings, 'configured', classmethod(lambda cls, **kwargs: object()))
        take = await ok('POST', f"/recording-takes/{take['id']}/policy", {
            'expected_version': take['version'], 'expected_scene_revision': take['policy_scene_revision'], 'approved': True,
            'tracks': [{'identity': host_identity, 'track_id': 'TR_QA_live_audio', 'source': 'microphone', 'kind': 'audio', 'required': True}],
        })
        take = await ok('POST', f"/recording-takes/{take['id']}/start", {'expected_version': take['version']})
        assert take['state'] == 'starting' and take['capture_job_id']

        native = os.environ.get('OPORA_QA_REAL_RECORDING_FIXTURE')
        content = Path(native).read_bytes() if native else b'Explicit synthetic completed-render database fixture; not an encoded video.'
        checksum = hashlib.sha256(content).hexdigest()
        if native:
            assert checksum == os.environ['OPORA_QA_REAL_RECORDING_SHA256']
        duration_ms = int(os.environ['OPORA_QA_REAL_RECORDING_DURATION_MS']) if native else 1000
        rid = uuid4()
        manifest = {'fixture_kind': 'copied_native_live_mp4' if native else 'synthetic_completed_media_metadata',
                    'publication_boundary_only': True, 'output_sha256': checksum, 'take_id': take['id'], 'duration_ms': duration_ms}
        render_hash = stable_hash(manifest)
        async with SessionLocal() as db:
            completed = await db.get(RecordingTake, UUID(take['id']))
            completed.state, completed.capture_phase = 'captured', 'complete'
            job = await db.get(Job, completed.capture_job_id)
            job.state = 'succeeded'
            owner = await db.get(RecordingProject, completed.project_id)
            assert owner.mode == 'live' and owner.live_event_id == wid
            assert await db.scalar(select(func.count()).select_from(StudioSession).where(StudioSession.resource_id == wid)) == 1
            asset = MediaAsset(foundation_id=fid, owner_user_id=uid, purpose='recording.output', resource_type='recording_render',
                               resource_id=rid, storage_key=uuid4().hex, content_type='video/mp4', expected_size=len(content),
                               received_size=len(content), checksum=checksum, state='ready')
            db.add(asset)
            await db.flush()
            path = asset_path(asset)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            path.write_bytes(content)
            db.add(RecordingRenderVersion(id=rid, project_id=owner.id, take_id=completed.id, generation=completed.generation,
                                         state='preview_ready', manifest=manifest, render_hash=render_hash, asset_id=asset.id,
                                         content_hash=checksum, duration_ms=duration_ms, quality='verified'))
            # A finished webinar must still allow review/publication of its captured output.
            (await db.get(Webinar, wid)).state = 'ended'
            (await db.get(StudioSession, sid)).state = 'closed'
            await db.commit()

        preview = await client.get(f'/api/v1/assets/{asset.id}/content')
        assert preview.status_code == 200 and hashlib.sha256(preview.content).hexdigest() == checksum
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://testserver') as stranger:
            await stranger.get('/api/v1/auth/session')
            assert (await stranger.get(f'/api/v1/assets/{asset.id}/content')).status_code in (401, 403, 404)

        attachment = {'expected_version': lesson['draft']['version'], 'render_id': str(rid), 'render_hash': render_hash}
        blocked = await request('POST', f'/coord/learning/lessons/{lid}/recording', attachment)
        assert blocked.status_code == 409 and blocked.json()['code'] == 'recording_approval_required'
        wrong = await request('POST', f'/recording-renders/{rid}/approve', {'expected_version': 1, 'render_hash': 'f' * 64})
        assert wrong.status_code == 409
        await ok('POST', f'/recording-renders/{rid}/approve', {'expected_version': 1, 'render_hash': render_hash, 'reason': 'Independent exact-output review'})
        lesson = await ok('POST', f'/coord/learning/lessons/{lid}/recording', attachment)
        assert lesson['draft']['status'] == 'draft' and len(lesson['draft']['blocks']) == 2
        body = await publication_body(lesson)
        blocked = await request('POST', f'/coord/learning/tracks/{tid}/publish', body)
        assert blocked.status_code == 409 and blocked.json()['code'] == 'review_required'
        async with SessionLocal() as db:
            assert str((await db.get(Lesson, UUID(lid))).current_version_id) == old_primary
        lesson = await ok('POST', f'/coord/learning/lessons/{lid}/review', {'expected_version': lesson['draft']['version']})
        body = await publication_body(lesson)
        published = await ok('POST', f'/coord/learning/tracks/{tid}/publish', body, 'qa-live-publish-' + str(rid))
        assert published['current_release_id'] != baseline['current_release_id']
        async with SessionLocal() as db:
            current = await db.get(Lesson, UUID(lid))
            assert str(current.current_version_id) != old_primary and await db.get(LessonVersion, UUID(old_primary))
            ledger = (await db.scalars(select(RecordingPublication).where(RecordingPublication.render_id == rid))).all()
            assert len(ledger) == 1 and ledger[0].lesson_version_id == current.current_version_id and ledger[0].render_hash == render_hash
            grant = await db.scalar(select(PermissionGrant).join(StaffMembership).where(StaffMembership.user_id == uid, PermissionGrant.permission == 'learning.publish'))
            grant.revoked_at = utcnow()
            await db.commit()
        denied = await request('POST', f'/coord/learning/tracks/{tid}/publish', body, 'qa-live-publish-' + str(rid))
        assert denied.status_code == 403
