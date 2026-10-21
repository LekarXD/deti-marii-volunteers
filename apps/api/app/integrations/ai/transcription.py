"""Optional ASR using the shared provider settings, budgets and durable runs."""
import asyncio
import hashlib
import math
from uuid import UUID
from urllib.parse import urlsplit
import httpx
from pydantic import BaseModel, ConfigDict, Field
from app.core.errors import ApiError
from .contracts import TASKS, register_task
from .provider import ProviderConfig, ProviderResult

MAX_AUDIO_BYTES=10*1024*1024
MAX_AUDIO_SECONDS=180
CONTENT_TYPES={'audio/wav':'wav','audio/x-wav':'wav','audio/webm':'webm','audio/mp4':'m4a','audio/ogg':'ogg','audio/mpeg':'mp3'}

class TranscriptionOutput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    text:str=Field(min_length=1,max_length=24000)

def register_transcription_task(task,*,on_validate,on_complete):
    if not callable(on_validate) or not callable(on_complete):raise ValueError('transcription_domain_hooks_required')
    async def complete(db,run,context):
        try:
            await context.fence(db)
            await on_complete(db,run,context)
        except ApiError as error:
            run.state,run.error_code,run.output='cancelled',error.code,None
    existing=TASKS.get(task)
    if existing:
        if existing.provider_mode!='transcription' or existing.on_validate is not on_validate:raise ValueError('duplicate_ai_task')
        return
    register_task(task,'transcription.v1','Transcribe only the supplied audio.',TranscriptionOutput,{'asset_id','duration_seconds'},max_input_bytes=1000,on_complete=complete,on_validate=on_validate,provider_mode='transcription')

async def transcription_readiness(db,foundation_id,task):
    from .service import settings
    spec=TASKS.get(task)
    policy=await settings(db,foundation_id)
    available=bool(spec and spec.provider_mode=='transcription' and ProviderConfig().configured_for(spec) and policy.enabled)
    return {'available':available,'reason':None if available else 'Голосовой ввод пока недоступен: сервис распознавания не настроен. Можно написать текст.'}

async def enqueue_transcription(db,principal,*,asset_id,duration_seconds,task):
    from .service import enqueue_ai_run
    spec=TASKS.get(task)
    if not spec or spec.provider_mode!='transcription':raise ApiError(503,'transcription_unconfigured','Распознавание пока недоступно. Можно написать текст.')
    if not isinstance(duration_seconds,(int,float)) or isinstance(duration_seconds,bool) or not math.isfinite(duration_seconds) or not 0<duration_seconds<=MAX_AUDIO_SECONDS:
        raise ApiError(422,'audio_duration_invalid','Запись должна быть не длиннее трёх минут')
    from app.modules.assets.service import require_asset
    asset=await require_asset(db,principal,asset_id,ready=False)
    if asset.owner_user_id!=principal.user_id or not principal.user_id or asset.content_type not in CONTENT_TYPES or not 0<asset.expected_size<=MAX_AUDIO_BYTES or asset.state not in {'processing','ready'}:
        raise ApiError(422,'audio_source_invalid','Проверьте формат и размер записи')
    return await enqueue_ai_run(db,principal,task,{'asset_id':str(asset.id),'duration_seconds':float(duration_seconds)},source_refs=[f'asset:{asset.id}:{asset.checksum}'],max_output_tokens=4000)

async def validated_audio(db,principal,run,phase):
    spec=TASKS[run.task]
    await spec.on_validate(db,principal,run,phase)
    from app.modules.assets.service import require_asset,asset_path
    asset=await require_asset(db,principal,UUID(run.input_data['asset_id']),ready=False)
    await db.refresh(asset)
    if asset.owner_user_id!=principal.user_id or not principal.user_id or asset.state not in {'processing','ready'} or asset.content_type not in CONTENT_TYPES or not 0<asset.expected_size<=MAX_AUDIO_BYTES or run.source_refs!=[f'asset:{asset.id}:{asset.checksum}']:
        raise ApiError(409,'audio_source_changed','Запись изменилась или недоступна')
    duration=run.input_data.get('duration_seconds')
    if type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=MAX_AUDIO_SECONDS:raise ApiError(422,'audio_duration_invalid','Запись слишком длинная')
    def read():
        with asset_path(asset).open('rb') as file:data=file.read(MAX_AUDIO_BYTES+1)
        if len(data)!=asset.expected_size or len(data)>MAX_AUDIO_BYTES or hashlib.sha256(data).hexdigest()!=asset.checksum:raise ValueError('source_changed')
        return data
    try:data=await asyncio.to_thread(read)
    except (OSError,ValueError):raise ApiError(409,'audio_source_changed','Запись изменилась или недоступна')
    return data,asset.content_type,CONTENT_TYPES[asset.content_type]

async def request_transcription(audio,config,timeout,transport=None):
    """Only called after the shared budget and durable calling marker commit."""
    parsed=urlsplit(config.base_url)
    if (parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in {'localhost','127.0.0.1','::1'})) or parsed.username or parsed.password or parsed.query or parsed.fragment:
        return ProviderResult('unavailable','provider_url_invalid')
    data,content_type,extension=audio
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout,connect=min(5,timeout)),transport=transport,follow_redirects=False,trust_env=False) as client:
                async with client.stream('POST',config.base_url.rstrip('/')+'/audio/transcriptions',headers={'Authorization':'Bearer '+config.api_key,'Accept':'application/json'},data={'model':config.transcription_model,'response_format':'json','language':'ru'},files={'file':('recording.'+extension,data,content_type)}) as response:
                    if response.status_code!=200:
                        return ProviderResult('unavailable','provider_rate_limited' if response.status_code==429 else 'provider_rejected' if response.status_code<500 else 'provider_unavailable')
                    raw=bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw)>128000:return ProviderResult('failed','provider_response_too_large')
                    import json
                    value=json.loads(raw)
                    output=TranscriptionOutput.model_validate({'text':value['text'].strip()})
                    return ProviderResult('succeeded',output=output.model_dump(),request_id=str(value.get('id',''))[:200] or None)
    except (TimeoutError,httpx.TimeoutException):return ProviderResult('unknown','provider_timeout')
    except httpx.RequestError:return ProviderResult('unknown','provider_network')
    except (ValueError,KeyError,TypeError,AttributeError):return ProviderResult('failed','provider_invalid_json')
