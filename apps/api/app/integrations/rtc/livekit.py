"""Narrow port of OD livekit_auth/livekit_rooms at 38c92cd49b1b6c229ed473de991479ed261e4052.

Only stable JWT/Twirp mechanics are reused. Opora owns all room, user and resource IDs.
No call falls back to a fake token or reports a provider side effect as successful.
"""
import base64
import hashlib
import hmac
import json
import os
import time
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID
import httpx
from app.core.errors import ApiError

@dataclass(frozen=True)
class RevocationPolicy:
    require_strict: bool = False

@dataclass(frozen=True)
class ProviderCapabilities:
    configured: bool
    strict_token_revocation: bool
    active_participant_removal: bool
    board_configured: bool
    limitation: str | None

@dataclass(frozen=True)
class RtcSettings:
    url: str = ""
    public_url: str = ""
    api_key: str = ""
    api_secret: str = field(default="",repr=False)
    deployment: Literal["self_hosted", "cloud"] = "self_hosted"
    join_ttl_seconds: int = 120
    board_url: str = ""
    board_secret: str = field(default="",repr=False)
    @classmethod
    def from_env(cls):
        return cls(url=os.getenv("OPORA_RTC_URL", ""),public_url=os.getenv("OPORA_RTC_PUBLIC_URL", ""),api_key=os.getenv("OPORA_RTC_API_KEY", ""),api_secret=os.getenv("OPORA_RTC_API_SECRET", ""),deployment=os.getenv("OPORA_RTC_DEPLOYMENT","self_hosted"),board_url=os.getenv("OPORA_RTC_BOARD_URL",""),board_secret=os.getenv("OPORA_RTC_BOARD_SECRET",""))
    def capabilities(self):
        configured=bool(self.url and self.api_key and self.api_secret)
        return ProviderCapabilities(configured,configured and self.deployment=="cloud",configured,bool(self.board_url and self.board_secret),None if self.deployment=="cloud" else "Existing self-hosted tokens are not invalidated by removal; refreshed tokens can outlive the initial join TTL.")
    def assert_policy(self,policy:RevocationPolicy):
        caps=self.capabilities()
        if not caps.configured:raise ApiError(503,"rtc_unavailable","Видеосвязь ещё не настроена.",retryable=False)
        if self.deployment not in ("cloud","self_hosted"):raise ApiError(503,"rtc_invalid_configuration","Проверьте конфигурацию видеосвязи.")
        if policy.require_strict and not caps.strict_token_revocation:raise ApiError(503,"rtc_revocation_unsupported","Эта встреча требует немедленного отзыва медиадоступа. Настроенный сервер его не поддерживает.")
        for value in (self.url,self.public_url or self.url):
            parsed=urlsplit(value)
            if parsed.scheme not in ("http","https","ws","wss") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ApiError(503,"rtc_invalid_configuration","Проверьте конфигурацию видеосвязи.")
        if not 30<=self.join_ttl_seconds<=300:raise ApiError(503,"rtc_invalid_configuration","Проверьте срок действия медиадоступа.")

class ProviderError(Exception):
    def __init__(self,method,status=None,code="unavailable"):
        self.method,self.status,self.code=method,status,code
        super().__init__(f"rtc {method}: status={status} code={code}")
    @property
    def not_found(self):return self.status==404 or self.code=="not_found"

def room_name(foundation_id:UUID,session_id:UUID,generation:int):
    if generation<1:raise ValueError("invalid_generation")
    return f"opora-f{foundation_id.hex}-s{session_id.hex}-g{generation}"

def identity(user_id:UUID):return "opora-u"+user_id.hex

def _encode(settings,claims):
    import jwt
    return jwt.encode(claims,settings.api_secret,algorithm="HS256")

def join_token(settings:RtcSettings,*,room:str,participant_identity:str,name:str,host:bool,policy:RevocationPolicy,auth_session_id:UUID|None=None,now:int|None=None):
    settings.assert_policy(policy)
    issued=int(time.time() if now is None else now)
    sources=["microphone","camera","screen_share","screen_share_audio"] if host else []
    grant={"room":room,"roomJoin":True,"canSubscribe":True,"canPublish":bool(sources),"canPublishData":False,"canUpdateOwnMetadata":False}
    if sources:grant["canPublishSources"]=sources
    # Host moderation is a fresh authorized API call, never a browser roomAdmin grant.
    return _encode(settings,{"iss":settings.api_key,"sub":participant_identity,"name":name[:100],"nbf":issued-5,"iat":issued,"exp":issued+settings.join_ttl_seconds,"metadata":json.dumps({"role":"host" if host else "audience","auth_session_id":str(auth_session_id) if auth_session_id else None}),"video":grant})

def renderer_token(settings:RtcSettings,*,room:str,participant_identity:str,capture_grant_id:UUID,take_id:UUID,generation:int,policy:RevocationPolicy,now:int|None=None):
    """P18C private factory; caller authorizes the current capture grant before signing.

    Short-lived SDK room token is distinct from the header-only purpose ticket.
    No user identity, audience data, room management or media publishing privileges.
    """
    settings.assert_policy(policy)
    if generation<1 or not room or not participant_identity:raise ValueError('invalid_capture_scope')
    issued=int(time.time() if now is None else now)
    grant={'room':room,'roomJoin':True,'canSubscribe':True,'canPublish':False,'canPublishData':False,'canUpdateOwnMetadata':False,'hidden':True}
    metadata={'role':'recording_renderer','capture_grant_id':str(capture_grant_id),'take_id':str(take_id),'generation':generation}
    return _encode(settings,{'iss':settings.api_key,'sub':participant_identity,'nbf':issued-5,'iat':issued,'exp':issued+min(60,settings.join_ttl_seconds),'metadata':json.dumps(metadata),'video':grant})

def server_token(settings,grant,now=None):
    issued=int(time.time() if now is None else now)
    return _encode(settings,{"iss":settings.api_key,"sub":"opora-api","nbf":issued-5,"exp":issued+60,"video":grant})

def verify_webhook(settings,body:bytes,authorization:str|None):
    if not settings.api_secret or not settings.api_key:return False
    import jwt
    token=(authorization or "").removeprefix("Bearer ").strip()
    if not token or len(token)>8192:return False
    try:claims=jwt.decode(token,settings.api_secret,algorithms=["HS256"],issuer=settings.api_key,options={"require":["exp","iss","sha256"],"verify_aud":False},leeway=5)
    except (jwt.PyJWTError,ValueError,TypeError):return False
    claimed=claims.get("sha256")
    return isinstance(claimed,str) and hmac.compare_digest(claimed,base64.b64encode(hashlib.sha256(body).digest()).decode())

class LiveKitAdapter:
    def __init__(self,settings:RtcSettings|None=None,client:httpx.AsyncClient|None=None):
        self.settings=settings or RtcSettings.from_env();self.client=client
    async def call(self,method,body):
        self.settings.assert_policy(RevocationPolicy())
        grant={"roomCreate":True} if method in ("CreateRoom","DeleteRoom") else {"roomAdmin":True,"room":body.get("room","")}
        base=self.settings.url.rstrip("/").replace("wss://","https://",1).replace("ws://","http://",1)
        headers={"Authorization":"Bearer "+server_token(self.settings,grant),"Content-Type":"application/json"}
        own=None
        try:
            client=self.client
            if client is None:own=httpx.AsyncClient(timeout=httpx.Timeout(5,connect=3),follow_redirects=False);client=own
            response=await client.post(f"{base}/twirp/livekit.RoomService/{method}",headers=headers,json=body)
            try:result=response.json()
            except ValueError:raise ProviderError(method,response.status_code,"bad_json") from None
            if response.status_code>=400:
                code=result.get("code") if isinstance(result,dict) else None
                raise ProviderError(method,response.status_code,code if isinstance(code,str) and len(code)<50 else "provider_failed")
            if not isinstance(result,dict):raise ProviderError(method,response.status_code,"bad_shape")
            return result
        except httpx.HTTPError:raise ProviderError(method,None,"network_error") from None
        finally:
            if own:await own.aclose()
    async def create_room(self,room):
        result=await self.call("CreateRoom",{"name":room,"empty_timeout":600,"departure_timeout":300,"max_participants":100})
        if not result.get("sid"):raise ProviderError("CreateRoom",200,"missing_room_sid")
        return result["sid"]
    async def close_room(self,room):
        try:await self.call("DeleteRoom",{"room":room})
        except ProviderError as exc:
            if not exc.not_found:raise
    async def remove_participant(self,room,participant_identity,*,revoked_at:int,policy:RevocationPolicy):
        self.settings.assert_policy(policy)
        body={"room":room,"identity":participant_identity}
        if self.settings.capabilities().strict_token_revocation:body["revoke_token_ts"]=revoked_at
        try:await self.call("RemoveParticipant",body)
        except ProviderError as exc:
            if not exc.not_found:raise
    async def participants(self,room):
        result=await self.call("ListParticipants",{"room":room})
        rows=result.get("participants",[])
        if not isinstance(rows,list) or any(not isinstance(row,dict) for row in rows):raise ProviderError("ListParticipants",200,"bad_shape")
        # The raw response includes track information; no TURN/provider secrets are returned to clients.
        return rows
