"""Generated local WAV and controlled HTTP; no external ASR or microphone."""
import hashlib
import io
import wave
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import select
from app.core.auth import resolve_principal
from app.core.config import get_settings
from app.core.errors import ApiError
from app.core.models import MediaAsset,Session
from app.integrations.ai.models import AIRun,AIDailyUsage,AISettings
from app.integrations.ai.transcription import register_transcription_task,enqueue_transcription,transcription_readiness
from test_knowledge import setup,configured,process_ai

async def fixture_audio(factory,foundation,tmp_path,monkeypatch):
    monkeypatch.setattr(get_settings(),'asset_root',str(tmp_path))
    output=io.BytesIO()
    with wave.open(output,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(8000);wav.writeframes(b'\x00\x00'*8000)
    data=output.getvalue();key=uuid4().hex;(tmp_path/key).write_bytes(data)
    async with factory() as db:
        session=await db.scalar(select(Session).where(Session.foundation_id==foundation,Session.user_id.is_not(None)))
        principal=await resolve_principal(db,session)
        asset=MediaAsset(foundation_id=foundation,owner_user_id=principal.user_id,storage_key=key,content_type='audio/wav',expected_size=len(data),received_size=len(data),checksum=hashlib.sha256(data).hexdigest(),state='ready')
        db.add(asset);await db.flush();await db.commit()
        return principal,asset.id,data

@pytest.mark.asyncio
async def test_optional_asr_shared_budget_marker_and_source_rechecks(setup,monkeypatch,tmp_path):
    client,factory,foundation=setup
    configured(monkeypatch);monkeypatch.delenv('OPORA_AI_TRANSCRIPTION_MODEL',raising=False)
    principal,asset_id,data=await fixture_audio(factory,foundation,tmp_path,monkeypatch)
    task='test.asr.'+uuid4().hex
    phases=[];active=True;delivered=[]
    async def validate(db,principal,run,phase):
        phases.append(phase)
        if not active:raise ApiError(403,'intent_revoked','Отменено')
    async def complete(db,run,context):delivered.append(run.state)
    register_transcription_task(task,on_validate=validate,on_complete=complete)
    async with factory() as db:
        assert not (await transcription_readiness(db,foundation,task))['available']
        unavailable=await enqueue_transcription(db,principal,asset_id=asset_id,duration_seconds=1,task=task)
        assert unavailable.state=='unavailable'
        await db.commit()
    monkeypatch.setenv('OPORA_AI_TRANSCRIPTION_MODEL','fixture-asr')
    async with factory() as db:
        assert (await transcription_readiness(db,foundation,task))['available']
        run=await enqueue_transcription(db,principal,asset_id=asset_id,duration_seconds=1,task=task)
        run_id=run.id;await db.commit()
    calls=[]
    async def provider(request):
        assert request.url.path=='/v1/audio/transcriptions'
        assert b'fixture-asr' in request.content and data in request.content
        async with factory() as check:
            current=await check.get(AIRun,run_id)
            assert current.state=='calling' and current.reserved_tokens>0
        calls.append(request)
        return httpx.Response(200,json={'text':'Это распознанный текст.'})
    assert await process_ai(factory,foundation,httpx.MockTransport(provider))==run_id
    async with factory() as db:
        run=await db.get(AIRun,run_id)
        assert run.state=='succeeded' and run.output=={'text':'Это распознанный текст.'}
        assert run.charged_tokens==1100 and run.reserved_tokens==0
        daily=await db.scalar(select(AIDailyUsage).where(AIDailyUsage.foundation_id==foundation))
        assert daily.requests==1 and daily.charged_tokens==1100
        # A new request gets domain-revoked while the provider is in flight.
        second=await enqueue_transcription(db,principal,asset_id=asset_id,duration_seconds=1,task=task)
        second_id=second.id;await db.commit()
    async def revoke(request):
        nonlocal active
        active=False
        return httpx.Response(200,json={'text':'Never deliver revoked transcript'})
    await process_ai(factory,foundation,httpx.MockTransport(revoke))
    async with factory() as db:
        rejected=await db.get(AIRun,second_id)
        assert rejected.state=='cancelled' and rejected.output is None and rejected.charged_tokens==1100
        third=await enqueue_transcription(db,principal,asset_id=asset_id,duration_seconds=1,task=task)
        third_id=third.id;await db.commit()
    def forbidden(request):raise AssertionError('revoked source cannot reach ASR')
    await process_ai(factory,foundation,httpx.MockTransport(forbidden))
    async with factory() as db:
        rejected=await db.get(AIRun,third_id)
        assert rejected.state=='cancelled' and rejected.charged_tokens==0
    assert phases.count('before_io')==3 and phases.count('delivery')==2
    assert len(calls)==1 and delivered==['succeeded','cancelled','cancelled']
