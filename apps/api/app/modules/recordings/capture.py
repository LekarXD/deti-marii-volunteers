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

class MediaValidationError(ValueError):
    def __init__(self,code,diagnostics=None):
        super().__init__(code);self.code=code;self.diagnostics=diagnostics

@dataclass(frozen=True)
class CaptureSettings:
    url:str
    chrome:str
    node:str
    ffmpeg:str
    ffprobe:str
    development:bool
    @classmethod
    def configured(cls,*,require_executables=False):
        if os.getenv('OPORA_CAPTURE_ENABLED')!='true':return None
        url=os.getenv('OPORA_CAPTURE_RENDERER_URL','')
        try:
            parts=urlsplit(url);parts.port
        except ValueError:return None
        development=os.getenv('OPORA_ENVIRONMENT','development')=='development'
        if not parts.hostname or parts.username or parts.password or parts.query or parts.fragment or parts.path!='/recorder.html' or (parts.scheme!='https' and not (development and parts.scheme=='http' and parts.hostname in ('localhost','127.0.0.1','::1'))):return None
        paths=[os.getenv('OPORA_CAPTURE_CHROME_PATH',''),shutil.which('node') or 'node',shutil.which('ffmpeg') or 'ffmpeg',shutil.which('ffprobe') or 'ffprobe']
        rtc=RtcSettings.from_env()
        if not rtc.capabilities().configured:return None
        if require_executables and not all(path and Path(path).is_file() for path in paths):return None
        from app.integrations.rtc.livekit import RevocationPolicy
        try:rtc.assert_policy(RevocationPolicy())
        except ApiError:return None
        if not development and any(urlsplit(value).scheme not in ('https','wss') for value in (rtc.url,rtc.public_url or rtc.url)):return None
        return cls(url,*paths,development)

async def approve_policy(db,p,row,owner,body):
    if (body.approved and row.state!='created') or (not body.approved and row.state not in ('created','starting','capturing','stopping')):raise ApiError(409,'recording_policy_locked','Политику можно согласовать до начала дубля')
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
        actual=set();active_audio=set()
        for participant in participants:
            if participant.get('identity','').startswith('opora-renderer-'):
                from .renderer import internal_participant_authorizer
                if await internal_participant_authorizer(db,session,participant):continue
                raise ApiError(409,'recording_unknown_participant','Неизвестный участник записи')
            if participant.get('identity')!=identity(p.user_id):raise ApiError(409,'recording_unknown_participant','В комнате появился другой участник; проверьте приватность')
            for track in participant.get('tracks',[]):
                source=source_map.get(track.get('source'))
                if not source:raise ApiError(409,'recording_unknown_track','Неизвестный источник записи')
                actual.add((participant['identity'],track.get('sid'),*source))
                if source[1]=='audio' and not track.get('muted',False):active_audio.add(track.get('sid'))
        if keys!=actual:raise ApiError(409,'recording_policy_tracks_changed','Источники изменились; проверьте список ещё раз')
        if not any(track['kind']=='audio' and track['required'] and track['track_id'] in active_audio for track in tracks):raise ApiError(409,'recording_audio_required','Подключите и согласуйте активный микрофон или звук')
    owner.privacy_state='approved' if body.approved else 'blocked';owner.version+=1
    await service.snapshot(db,owner,row,session,privacy_state=owner.privacy_state,allowed_tracks=tracks if body.approved else [])
    row.version+=1
    return row

async def start_capture(db,row,owner):
    if CaptureSettings.configured() is None:raise ApiError(503,'recording_capture_unavailable','Захват медиа не настроен')
    if row.state!='created':raise ApiError(409,'recording_take_not_created','Этот дубль уже запускался')
    if row.projection['capture_plan']['privacy_state']!='approved' or owner.privacy_state!='approved':raise ApiError(409,'recording_policy_not_approved','Проверьте и согласуйте источники записи')
    if not any(track['kind']=='audio' for track in row.projection['capture_plan']['allowed_tracks']):raise ApiError(409,'recording_audio_required','Подключите собственный микрофон или согласованный звук')
    job=enqueue_job(db,owner.foundation_id,'recording.capture',{'take_id':str(row.id),'generation':row.generation},max_attempts=3)
    await db.flush();row.capture_job_id=job.id;row.capture_phase='queued';row.state='starting';row.version+=1

async def stop_capture(db,row):
    if row.state not in ('starting','capturing'):raise ApiError(409,'recording_capture_not_active','Запись сейчас не идёт')
    row.state='stopping';row.version+=1

async def media_command(*arguments,timeout=90):
    process=await asyncio.create_subprocess_exec(*arguments,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
    try:
        output,_=await asyncio.wait_for(process.communicate(),timeout)
        if process.returncode or len(output)>1024*1024:raise MediaValidationError('media_command_failed')
        return output
    except TimeoutError:raise MediaValidationError('media_command_timeout') from None
    finally:
        if process.returncode is None:process.kill();await process.wait()

async def encode_and_validate(settings,source,output,expected_duration_ms):
    await media_command(settings.ffmpeg,'-nostdin','-v','error','-protocol_whitelist','file,pipe','-i',str(source),'-map','0:v:0','-map','0:a:0','-c:v','libx264','-preset','fast','-pix_fmt','yuv420p','-c:a','aac','-movflags','+faststart','-threads','2','-y',str(output),timeout=180)
    probe=json.loads(await media_command(settings.ffprobe,'-v','error','-show_streams','-show_format','-of','json',str(output)))
    streams=probe.get('streams',[]);video=[s for s in streams if s.get('codec_type')=='video'];audio=[s for s in streams if s.get('codec_type')=='audio']
    duration=round(float(probe.get('format',{}).get('duration','0'))*1000)
    if len(video)!=1 or len(audio)!=1 or video[0].get('codec_name')!='h264' or (video[0].get('width'),video[0].get('height'))!=(1920,1080) or audio[0].get('codec_name')!='aac' or not 300<=duration<=1202000 or abs(duration-expected_duration_ms)>2000:raise MediaValidationError('media_profile_mismatch',{'duration_ms':duration,'expected_duration_ms':expected_duration_ms,'video':[{'codec':stream.get('codec_name'),'width':stream.get('width'),'height':stream.get('height')} for stream in video],'audio':[{'codec':stream.get('codec_name')} for stream in audio]})
    await media_command(settings.ffmpeg,'-nostdin','-v','error','-xerror','-i',str(output),'-f','null','-',timeout=120)
    return {'profile':'opora-stage/1','width':1920,'height':1080,'video_codec':'h264','audio_codec':'aac','duration_ms':duration,'full_decode':True}

async def verify_provider_scope(db,row,owner):
    """Independent provider evidence: never rely only on what an unsubscribed renderer reports."""
    capture=await db.get(StudioCaptureSession,row.capture_session_id)
    studio=await db.get(StudioSession,capture.studio_session_id)
    from .renderer import internal_participant_authorizer
    participants=await LiveKitAdapter().participants(studio.room_name)
    wanted={(t['identity'],t['track_id'],t['source'],t['kind']) for t in row.projection['capture_plan']['allowed_tracks']}
    actual=set();source_map={'CAMERA':('camera','video'),1:('camera','video'),'MICROPHONE':('microphone','audio'),2:('microphone','audio'),'SCREEN_SHARE':('screen','video'),3:('screen','video'),'SCREEN_SHARE_AUDIO':('screen_audio','audio'),4:('screen_audio','audio')}
    for participant in participants:
        if participant.get('identity','').startswith('opora-renderer-'):
            if await internal_participant_authorizer(db,studio,participant):continue
            raise ValueError('capture_unknown_participant')
        if participant.get('identity')!=identity(owner.owner_user_id):raise ValueError('capture_unknown_participant')
        for track in participant.get('tracks',[]):
            source=source_map.get(track.get('source'))
            if not source:raise ValueError('capture_unknown_track')
            actual.add((participant['identity'],track.get('sid'),*source))
    if actual!=wanted:raise ValueError('capture_provider_tracks_changed')
