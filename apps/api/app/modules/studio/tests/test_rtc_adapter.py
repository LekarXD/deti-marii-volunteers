import base64
import hashlib
from uuid import uuid4
import httpx
import pytest
from app.core.errors import ApiError
from app.integrations.rtc.livekit import RtcSettings,RevocationPolicy,LiveKitAdapter,join_token,verify_webhook,room_name,identity,ProviderError

def configured(deployment='self_hosted'):
    return RtcSettings(url='https://rtc.example.test',api_key='test-key',api_secret='fixture-secret-at-least-32-bytes-long',deployment=deployment)

def test_unavailable_and_strict_revocation_fail_before_signing():
    with pytest.raises(ApiError) as missing:join_token(RtcSettings(),room='room',participant_identity='person',name='Person',host=True,policy=RevocationPolicy())
    assert missing.value.code=='rtc_unavailable'
    with pytest.raises(ApiError) as strict:join_token(configured(),room='room',participant_identity='person',name='Person',host=True,policy=RevocationPolicy(True))
    assert strict.value.code=='rtc_revocation_unsupported'
    assert not configured().capabilities().strict_token_revocation
    assert configured('cloud').capabilities().strict_token_revocation

def test_signed_real_grants_no_browser_admin_or_egress_and_webhook_hash():
    import jwt,time
    settings=configured();now=int(time.time())
    token=join_token(settings,room='opora-room',participant_identity='opora-person',name='Name',host=True,policy=RevocationPolicy(),now=now)
    claims=jwt.decode(token,settings.api_secret,algorithms=['HS256'],issuer=settings.api_key)
    assert claims['exp']-now==120 and claims['video']['room']=='opora-room'
    assert not claims['video'].get('roomAdmin') and not claims['video'].get('roomRecord') and not claims['video']['canPublishData']
    audience=jwt.decode(join_token(settings,room='opora-room',participant_identity='viewer',name='Viewer',host=False,policy=RevocationPolicy()),settings.api_secret,algorithms=['HS256'])
    assert not audience['video']['canPublish'] and 'canPublishSources' not in audience['video']
    body=b'{"event":"participant_joined"}'
    webhook=jwt.encode({'iss':settings.api_key,'exp':now+60,'sha256':base64.b64encode(hashlib.sha256(body).digest()).decode()},settings.api_secret,algorithm='HS256')
    assert verify_webhook(settings,body,webhook) and not verify_webhook(settings,body+b' ',webhook)

@pytest.mark.asyncio
async def test_cloud_revoke_has_cutoff_selfhosted_cannot_claim_old_token_invalid():
    seen=[]
    import jwt
    token=join_token(configured(),room='room',participant_identity='user',name='User',host=False,policy=RevocationPolicy())
    def handler(request):
        import json
        seen.append(json.loads(request.content));return httpx.Response(200,json={})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cloud=LiveKitAdapter(configured('cloud'),client)
        await cloud.remove_participant('room','user',revoked_at=123,policy=RevocationPolicy(True))
        assert seen[-1]['revoke_token_ts']==123
        selfhost=LiveKitAdapter(configured(),client)
        with pytest.raises(ApiError):await selfhost.remove_participant('room','user',revoked_at=124,policy=RevocationPolicy(True))
        await selfhost.remove_participant('room','user',revoked_at=124,policy=RevocationPolicy())
        assert 'revoke_token_ts' not in seen[-1]
    # Previously issued valid JWT remains cryptographically valid after RemoveParticipant:
    # explicit capability prevents a strict policy from ever issuing it on this provider.
    assert jwt.decode(token,configured().api_secret,algorithms=['HS256'])['sub']=='user'

def test_resource_namespace_has_no_school_identity():
    foundation,session,user=uuid4(),uuid4(),uuid4()
    assert room_name(foundation,session,1).startswith('opora-f') and identity(user)=='opora-u'+user.hex

def test_renderer_factory_is_hidden_subscribe_only_and_exact_capture_scope():
    import json,jwt
    from uuid import uuid4
    from app.integrations.rtc.livekit import renderer_token
    settings=RtcSettings(url='https://rtc.example.test',api_key='fixture',api_secret='a-private-fixture-secret-with-enough-bytes')
    grant,take=uuid4(),uuid4();token=renderer_token(settings,room='opora-private-room',participant_identity='opora-renderer-'+grant.hex,capture_grant_id=grant,take_id=take,generation=3,policy=RevocationPolicy(False))
    claims=jwt.decode(token,settings.api_secret,algorithms=['HS256'])
    assert claims['exp']-claims['iat']<=60
    assert json.loads(claims['metadata'])=={'role':'recording_renderer','capture_grant_id':str(grant),'take_id':str(take),'generation':3}
    assert claims['video']=={'room':'opora-private-room','roomJoin':True,'canSubscribe':True,'canPublish':False,'canPublishData':False,'canUpdateOwnMetadata':False,'hidden':True}
    with pytest.raises(ApiError):renderer_token(settings,room='opora-private-room',participant_identity='renderer',capture_grant_id=grant,take_id=take,generation=3,policy=RevocationPolicy(True))

@pytest.mark.asyncio
async def test_provider_error_cannot_echo_raw_secret_or_url_into_logs():
    def handler(request):return httpx.Response(503,json={'code':'wss://secret-pass@rtc/private','message':'opaque-secret-token'})
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ProviderError) as failure:await LiveKitAdapter(configured(),client).participants('room')
        assert failure.value.code=='provider_failed'
        assert 'secret' not in str(failure.value) and 'rtc/private' not in str(failure.value)
