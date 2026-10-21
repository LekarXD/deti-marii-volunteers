"""Explicit opt-in native recorder configuration, commands and media validation."""
import asyncio
import json
import os
import shutil
from pathlib import Path
from urllib.parse import urlsplit
from dataclasses import dataclass
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.integrations.rtc.livekit import RtcSettings,LiveKitAdapter,identity
from app.modules.studio.models import StudioSession
from app.worker.queue import enqueue_job
from .models import StudioCaptureSession
from . import service

@dataclass(frozen=True)
class CaptureSettings:
    url:str
    chrome:str
    node:str
    ffmpeg:str
    ffprobe:str
    development:bool
    @classmethod
    def configured(cls):
        if os.getenv('OPORA_CAPTURE_ENABLED')!='true':return None
        url=os.getenv('OPORA_CAPTURE_RENDERER_URL','');parts=urlsplit(url)
        development=os.getenv('OPORA_ENVIRONMENT','development')=='development'
        if parts.username or parts.password or parts.query or parts.fragment or parts.path!='/recorder.html' or (parts.scheme!='https' and not (development and parts.scheme=='http' and parts.hostname in ('localhost','127.0.0.1','::1'))):return None
        paths=[os.getenv('OPORA_CAPTURE_CHROME_PATH',''),shutil.which('node'),shutil.which('ffmpeg'),shutil.which('ffprobe')]
        if not all(path and Path(path).is_file() for path in paths) or not RtcSettings.from_env().capabilities().configured:return None
        return cls(url,*paths,development)

async def approve_policy(db,p,row,owner,body):
    if row.state!='created':raise ApiError(409,'recording_policy_locked','Политику можно согласовать до начала дубля')
    capture=await db.get(StudioCaptureSession,row.capture_session_id)
    session=await db.get(StudioSession,capture.studio_session_id,populate_existing=True)
    if not session or session.generation!=row.generation or session.scene_revision!=body.expected_scene_revision:raise ApiError(409,'scene_revision_conflict','Кадр изменился',current_version=session.scene_revision if session else None)
    if owner.mode!='solo' or session.scene['presenter_identity']!=identity(p.user_id):raise ApiError(409,'recording_policy_unavailable','Для этой студии требуется отдельное согласование участников')
    tracks=[item.model_dump() for item in body.tracks]
    keys={(t['identity'],t['track_id'],t['source'],t['kind']) for t in tracks}
    if len(keys)!=len(tracks) or any(t['identity']!=identity(p.user_id) for t in tracks):raise ApiError(422,'recording_policy_tracks_invalid','Выберите только собственные источники записи')
    if body.approved:
        from app.integrations.rtc.livekit import ProviderError
        try:participants=await LiveKitAdapter().participants(session.room_name)
        except ProviderError:raise ApiError(503,'recording_provider_unavailable','Не удалось проверить источники записи') from None
        source_map={'CAMERA':('camera','video'),1:('camera','video'),'MICROPHONE':('microphone','audio'),2:('microphone','audio'),'SCREEN_SHARE':('screen','video'),3:('screen','video'),'SCREEN_SHARE_AUDIO':('screen_audio','audio'),4:('screen_audio','audio')}
        actual=set()
        for participant in participants:
            if participant.get('identity','').startswith('opora-renderer-'):continue
            if participant.get('identity')!=identity(p.user_id):raise ApiError(409,'recording_unknown_participant','В комнате появился другой участник; проверьте приватность')
            for track in participant.get('tracks',[]):
                source=source_map.get(track.get('source'))
                if not source:raise ApiError(409,'recording_unknown_track','Неизвестный источник записи')
                actual.add((participant['identity'],track.get('sid'),*source))
        if keys!=actual:raise ApiError(409,'recording_policy_tracks_changed','Источники изменились; проверьте список ещё раз')
    owner.privacy_state='approved' if body.approved else 'blocked';owner.version+=1
    await service.snapshot(db,owner,row,session,privacy_state=owner.privacy_state,allowed_tracks=tracks if body.approved else [])
    row.version+=1
    return row

async def start_capture(db,row,owner):
    if CaptureSettings.configured() is None:raise ApiError(503,'recording_capture_unavailable','Захват медиа не настроен')
    if row.state!='created':raise ApiError(409,'recording_take_not_created','Этот дубль уже запускался')
    if row.projection['capture_plan']['privacy_state']!='approved' or owner.privacy_state!='approved':raise ApiError(409,'recording_policy_not_approved','Проверьте и согласуйте источники записи')
    job=enqueue_job(db,owner.foundation_id,'recording.capture',{'take_id':str(row.id),'generation':row.generation},max_attempts=3)
    await db.flush();row.capture_job_id=job.id;row.capture_phase='queued';row.state='starting';row.version+=1

async def stop_capture(db,row):
    if row.state not in ('starting','capturing'):raise ApiError(409,'recording_capture_not_active','Запись сейчас не идёт')
    row.state='stopping';row.version+=1

async def media_command(*arguments,timeout=90):
    process=await asyncio.create_subprocess_exec(*arguments,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
    try:
        output,_=await asyncio.wait_for(process.communicate(),timeout)
        if process.returncode or len(output)>1024*1024:raise ValueError('media_validation_failed')
        return output
    finally:
        if process.returncode is None:process.kill();await process.wait()

async def encode_and_validate(settings,source,output,expected_duration_ms):
    await media_command(settings.ffmpeg,'-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',str(source),'-map','0:v:0','-map','0:a:0','-c:v','libx264','-preset','fast','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart','-threads','2','-y',str(output),timeout=180)
    probe=json.loads(await media_command(settings.ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(output)))
    streams=probe.get('streams',[]);video=[s for s in streams if s.get('codec_type')=='video'];audio=[s for s in streams if s.get('codec_type')=='audio']
    duration=round(float(probe.get('format',{}).get('duration','0'))*1000)
    if len(video)!=1 or len(audio)!=1 or video[0].get('codec_name')!='h264' or (video[0].get('width'),video[0].get('height'))!=(1920,1080) or audio[0].get('codec_name')!='aac' or not 300<=duration<=1202000 or abs(duration-expected_duration_ms)>2000:raise ValueError('media_profile_mismatch')
    await media_command(settings.ffmpeg,'-nostdin','-v','error','-xerror','-i',str(output),'-f','null','-',timeout=120)
    return {'profile':'opora-stage/1','width':1920,'height':1080,'video_codec':'h264','audio_codec':'aac','duration_ms':duration,'full_decode':True}
