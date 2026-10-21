import asyncio
import json
from dataclasses import dataclass
from urllib.parse import urlsplit
import httpx
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict
from .contracts import TaskSpec

class ProviderConfig(BaseSettings):
    model_config=SettingsConfigDict(env_prefix='OPORA_AI_',extra='ignore')
    base_url: str = ''
    api_key: str = ''
    model: str = ''
    enabled: bool = False
    transcription_model: str = ''
    def model_for(self,spec):
        return self.transcription_model if spec.provider_mode=='transcription' else self.model
    def configured_for(self,spec):
        return bool(self.base_url and self.api_key and self.model_for(spec))
    def configured(self):
        return bool(self.base_url and self.api_key and self.model)

@dataclass
class ProviderResult:
    state: str
    error_code: str | None = None
    output: dict | None = None
    tokens: int | None = None
    request_id: str | None = None

async def request_json(spec:TaskSpec,data:dict,config:ProviderConfig,max_tokens:int,timeout:int,transport=None):
    if not config.configured():
        return ProviderResult('unavailable','provider_unconfigured')
    parsed=urlsplit(config.base_url)
    if parsed.scheme!='https' and not (parsed.scheme=='http' and parsed.hostname in {'localhost','127.0.0.1','::1'}):
        return ProviderResult('unavailable','provider_url_invalid')
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        return ProviderResult('unavailable','provider_url_invalid')
    schema=spec.output_model.model_json_schema()
    payload={'model':config.model,'messages':[{'role':'system','content':spec.system_prompt+'\nJSON contract: '+json.dumps(schema,ensure_ascii=False)},{'role':'user','content':json.dumps(data,ensure_ascii=False)}], 'max_tokens':max_tokens, 'temperature':0,'response_format':{'type':'json_object'}}
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout,connect=min(5,timeout)),transport=transport,follow_redirects=False,trust_env=False) as client:
                async with client.stream('POST',config.base_url.rstrip('/')+'/chat/completions',headers={'Authorization':'Bearer '+config.api_key,'Accept':'application/json'},json=payload) as response:
                    if response.status_code!=200:
                        code='provider_rate_limited' if response.status_code==429 else 'provider_rejected' if response.status_code<500 else 'provider_unavailable'
                        return ProviderResult('unavailable',code)
                    raw=bytearray()
                    async for chunk in response.aiter_bytes():
                        raw.extend(chunk)
                        if len(raw)>256000:
                            return ProviderResult('failed','provider_response_too_large')
                    result=json.loads(raw)
                    content=result['choices'][0]['message']['content']
                    validated=spec.output_model.model_validate_json(content)
                    usage=result.get('usage',{}).get('total_tokens')
                    tokens=usage if type(usage) is int and 0<=usage<=10000000 else None
                    return ProviderResult('succeeded',output=validated.model_dump(mode='json'),tokens=tokens,request_id=str(result.get('id',''))[:200] or None)
    except (TimeoutError,httpx.TimeoutException):
        return ProviderResult('unknown','provider_timeout')
    except httpx.RequestError:
        return ProviderResult('unknown','provider_network')
    except (ValueError,KeyError,IndexError,TypeError,ValidationError):
        return ProviderResult('failed','provider_invalid_json')
