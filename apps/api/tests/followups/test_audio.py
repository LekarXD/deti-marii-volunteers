"""Real purpose-bound upload and durable local ASR flow; generated audio only."""
import hashlib
import io
import wave
from uuid import UUID,uuid4
from datetime import timedelta
import httpx
import pytest
from sqlalchemy import select,func
from app.core.clock import utcnow
from app.core.models import Job,MediaAsset,Session
from app.integrations.ai.models import AIRun,AIDailyUsage
from app.integrations.ai.service import execute_run
from app.integrations.ai.contracts import TASKS
from app.modules.followups import jobs,audio
from app.modules.followups.models import Reflection,ReflectionAudioUpload
from app.worker.registry import JobContext
from app.worker.queue import complete
from followups.test_followups import prepared,assigned,env,mutate


def recording(seconds=1):
    out=io.BytesIO()
    with wave.open(out,'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0\0'*int(seconds*16000))
    return out.getvalue()


def configured(monkeypatch):
    for key,value in {'OPORA_AI_ENABLED':'true','OPORA_AI_BASE_URL':'http://127.0.0.1:9/v1','OPORA_AI_API_KEY':'fictitious-local-fixture','OPORA_AI_TRANSCRIPTION_MODEL':'fixture-asr'}.items():monkeypatch.setenv(key,value)


async def uploaded(x,monkeypatch,data=None):
    configured(monkeypatch);data=recording() if data is None else data
    body={'content_type':'audio/wav','expected_size':len(data),'checksum':hashlib.sha256(data).hexdigest()};key=str(uuid4())
    response=await mutate(x.first,x.root+'/reflection/audio-intent',body,key=key)
    assert response.status_code==200,response.text
    source=response.json()
    replay=await mutate(x.first,x.root+'/reflection/audio-intent',body,key=key)
    assert replay.status_code==200 and replay.json()['asset_id']==source['asset_id']
    for offset in range(0,len(data),1024*1024):
        chunk=await x.first.patch(source['upload_url'],content=data[offset:offset+1024*1024],headers={'Content-Type':'application/octet-stream','X-Upload-Offset':str(offset)})
        assert chunk.status_code==200,chunk.text
    done=await x.first.post('/api/v1/assets/'+source['asset_id']+'/complete-upload')
    return source,done,data


async def process(x,kind,transport=None):
    async with x.sessions() as db:
        job=await db.scalar(select(Job).where(Job.foundation_id==x.foundation,Job.kind==kind,Job.state=='queued').order_by(Job.created_at).with_for_update())
        assert job is not None
        job.state='running';job.claim_token=uuid4();job.lease_until=utcnow()+timedelta(minutes=2);job.attempts+=1
        await db.commit();context=JobContext(job.id,job.claim_token,job.foundation_id,job.payload)
        if kind=='followups.audio':result=await audio.process_audio(db,context)
        else:
            result=await execute_run(db,context,transport=transport)
            run=await db.get(AIRun,UUID(job.payload['run_id']))
            await TASKS[run.task].on_complete(db,run,context)
        await complete(db,job.id,job.claim_token,result);await db.commit()
        return result


@pytest.mark.asyncio
async def test_voice_upload_real_decode_durable_asr_private_preview_and_explicit_text_save(prepared,monkeypatch):
    x=prepared;source,done,data=await uploaded(x,monkeypatch)
    assert done.status_code==200 and done.json()['state']=='processing',done.text
    assert (await x.first.get(x.root+'/reflection')).json()['text']==''
    assert (await x.second.get(x.root+'/reflection/audio/'+source['asset_id'])).status_code==404
    assert (await x.second.get('/api/v1/assets/'+source['asset_id']+'/status')).status_code==404
    queued=await process(x,'followups.audio');assert queued['state']=='queued'
    calls=[]
    async def local_provider(request):
        calls.append(request)
        assert request.url.path=='/v1/audio/transcriptions' and data in request.content
        async with x.sessions() as check:
            run=await check.get(AIRun,UUID(queued['run_id']));assert run.state=='calling' and run.reserved_tokens>0
        return httpx.Response(200,json={'text':'Текст для личного предпросмотра.'})
    assert (await process(x,'ai.generate',httpx.MockTransport(local_provider)))['state']=='succeeded'
    view=(await x.first.get(x.root+'/reflection/audio/'+source['asset_id'])).json()
    assert view['state']=='ready' and view['duration_seconds']==1 and view['transcript']=='Текст для личного предпросмотра.'
    assert (await x.first.get(x.root+'/reflection')).json()['text']==''
    assert (await x.admin.get('/api/v1/coord/reflections')).json()['items']==[]
    assert (await x.admin.get('/api/v1/assets/'+source['asset_id']+'/content')).status_code==404
    saved=await mutate(x.first,x.root+'/reflection',{'expected_version':0,'text':'Исправленный волонтёром текст.'},'PUT')
    assert saved.status_code==200 and saved.json()['text']=='Исправленный волонтёром текст.'
    async with x.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(ReflectionAudioUpload))==1
        daily=await db.scalar(select(AIDailyUsage));assert daily.requests==1 and daily.charged_tokens==1100
    assert len(calls)==1


@pytest.mark.asyncio
async def test_cancel_before_call_prevents_asr(prepared,monkeypatch):
    x=prepared;source,done,_=await uploaded(x,monkeypatch);assert done.status_code==200
    queued=await process(x,'followups.audio')
    view=(await x.first.get(x.root+'/reflection/audio/'+source['asset_id'])).json()
    cancelled=await mutate(x.first,x.root+'/reflection/audio/'+source['asset_id']+'/cancel',{'expected_version':view['version']})
    assert cancelled.status_code==200 and cancelled.json()['state']=='cancelled',cancelled.text
    def never(request):raise AssertionError('Cancelled recording cannot reach ASR')
    assert (await process(x,'ai.generate',httpx.MockTransport(never)))['state']=='cancelled'
    async with x.sessions() as db:
        run=await db.get(AIRun,UUID(queued['run_id']));assert run.output is None and run.charged_tokens==0
    assert (await x.first.get('/api/v1/assets/'+source['asset_id']+'/content')).status_code==409


@pytest.mark.asyncio
async def test_unknown_call_stays_durable_until_explicit_retry_and_late_cancel_discards_output(prepared,monkeypatch):
    x=prepared;source,done,_=await uploaded(x,monkeypatch);assert done.status_code==200
    await process(x,'followups.audio');calls=[]
    def uncertain(request):calls.append(request);raise httpx.ReadTimeout('controlled local timeout',request=request)
    assert (await process(x,'ai.generate',httpx.MockTransport(uncertain)))['state']=='unknown'
    view=(await x.first.get(x.root+'/reflection/audio/'+source['asset_id'])).json()
    assert view['state']=='unknown' and view['can_retry'] is True and view['transcript'] is None
    async with x.sessions() as db:
        assert await db.scalar(select(func.count()).select_from(Job).where(Job.kind=='ai.generate',Job.state=='queued'))==0
    retry=await mutate(x.first,x.root+'/reflection/audio/'+source['asset_id']+'/retry',{'expected_version':view['version']})
    assert retry.status_code==200,retry.text
    await process(x,'followups.audio')
    async def cancelled_in_flight(request):
        current=(await x.first.get(x.root+'/reflection/audio/'+source['asset_id'])).json()
        cancelled=await mutate(x.first,x.root+'/reflection/audio/'+source['asset_id']+'/cancel',{'expected_version':current['version']})
        assert cancelled.status_code==200,cancelled.text
        async with x.sessions() as check:
            intent=await check.get(ReflectionAudioUpload,UUID(source['asset_id']));run=await check.get(AIRun,intent.run_id)
            assert run.state=='calling' and run.reserved_tokens>0
        return httpx.Response(200,json={'text':'Нельзя показать этот результат'})
    assert (await process(x,'ai.generate',httpx.MockTransport(cancelled_in_flight)))['state']=='cancelled'
    view=(await x.first.get(x.root+'/reflection/audio/'+source['asset_id'])).json()
    assert view['state']=='cancelled' and view['transcript'] is None and view['can_retry'] is False
    async with x.sessions() as db:
        assert all(run.output is None and run.reserved_tokens==0 for run in (await db.scalars(select(AIRun))).all())
        assert (await db.scalar(select(AIDailyUsage))).requests==2
    assert len(calls)==1


@pytest.mark.asyncio
async def test_invalid_codec_duration_and_session_revocation_have_no_transcript(prepared,monkeypatch):
    x=prepared
    source,done,_=await uploaded(x,monkeypatch,recording(180.1))
    assert done.status_code==422
    async with x.sessions() as db:assert await db.scalar(select(func.count()).select_from(AIRun))==0
    source,done,_=await uploaded(x,monkeypatch);assert done.status_code==200
    queued=await process(x,'followups.audio')
    async with x.sessions() as db:
        row=await db.get(ReflectionAudioUpload,UUID(source['asset_id']));session=await db.get(Session,row.request_session_id);session.revoked_at=utcnow();await db.commit()
    def never(request):raise AssertionError('Revoked session cannot reach ASR')
    assert (await process(x,'ai.generate',httpx.MockTransport(never)))['state']=='cancelled'
    async with x.sessions() as db:
        run=await db.get(AIRun,UUID(queued['run_id']));assert run.output is None and run.charged_tokens==0
    assert (await x.first.get(x.root+'/reflection/audio/'+source['asset_id'])).status_code==401
