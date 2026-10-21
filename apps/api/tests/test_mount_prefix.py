"""Trusted strip-proxy contract: cookie scope, local URLs and private renderer path."""
import pytest
import httpx
from fastapi import FastAPI
from pydantic import ValidationError
from app.core.config import Settings,get_settings
from app.core.paths import normalize_mount_prefix,public_path
from app.core.platform import install_platform
from app.modules.auth.router import router as auth
from app.modules.assets.router import router as assets
from app.modules.recordings.capture import CaptureSettings

@pytest.mark.parametrize('value',['https://host/app','//host','/a//b','/../app','/app%2fother','/app?x=1','/app#x','/app\\other'])
def test_mount_prefix_rejects_untrusted_shapes(value):
    with pytest.raises(ValidationError):Settings(app_mount_prefix=value)

def test_prefix_paths_are_normalized_idempotent_and_provider_urls_unchanged(monkeypatch):
    settings=get_settings();monkeypatch.setattr(settings,'app_mount_prefix','/deti-marii')
    assert normalize_mount_prefix('/deti-marii/')=='/deti-marii'
    assert public_path('/api/v1/assets/id/upload')=='/deti-marii/api/v1/assets/id/upload'
    assert public_path('/deti-marii/api/v1/assets/id/upload')=='/deti-marii/api/v1/assets/id/upload'
    with pytest.raises(ValueError):public_path('https://provider.invalid/signed')

class StripProxy:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        assert scope['path'].startswith('/deti-marii/')
        scope={**scope,'path':scope['path'][len('/deti-marii'):],'raw_path':scope['path'][len('/deti-marii'):].encode()}
        await self.app(scope,receive,send)

@pytest.mark.asyncio
async def test_prefixed_proxy_normal_auth_cookie_csrf_upload_and_logout(monkeypatch):
    from app.cli import fixtures
    settings=get_settings();monkeypatch.setattr(settings,'app_mount_prefix','/deti-marii');monkeypatch.setattr(settings,'cookie_secure',True);monkeypatch.setattr(settings,'trusted_origins',['https://www.odschool.ru'])
    await fixtures();app=FastAPI();install_platform(app);app.include_router(auth);app.include_router(assets)
    assert app.root_path=='/deti-marii'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=StripProxy(app)),base_url='https://www.odschool.ru') as client:
        response=await client.get('/deti-marii/api/v1/auth/session');assert response.status_code==200
        cookie=response.headers['set-cookie'];assert 'Path=/deti-marii;' in cookie and 'Secure' in cookie and 'HttpOnly' in cookie
        session=response.json();headers={'Origin':'https://www.odschool.ru','X-CSRF-Token':session['csrf_token']}
        intent={'content_type':'image/png','expected_size':10,'checksum':'a'*64}
        denied=await client.post('/deti-marii/api/v1/assets/upload-intents',json=intent,headers={**headers,'Origin':'https://www.odschool.ru.evil.invalid'});assert denied.status_code==403
        upload=await client.post('/deti-marii/api/v1/assets/upload-intents',json=intent,headers=headers);assert upload.status_code==200,upload.text
        assert upload.json()['upload_url'].startswith('/deti-marii/api/v1/assets/')
        logout=await client.post('/deti-marii/api/v1/auth/logout',headers=headers);assert logout.status_code==200
        assert 'Path=/deti-marii;' in logout.headers['set-cookie'] and 'Max-Age=0' in logout.headers['set-cookie']

def test_capture_config_requires_exact_trusted_prefixed_entry(monkeypatch):
    settings=get_settings();monkeypatch.setattr(settings,'app_mount_prefix','/deti-marii')
    for name,value in {'OPORA_CAPTURE_ENABLED':'true','OPORA_ENVIRONMENT':'development','OPORA_CAPTURE_RENDERER_URL':'http://127.0.0.1:5174/deti-marii/recorder.html','OPORA_RTC_URL':'http://127.0.0.1:7880','OPORA_RTC_API_KEY':'synthetic','OPORA_RTC_API_SECRET':'synthetic-private-test-value'}.items():monkeypatch.setenv(name,value)
    configured=CaptureSettings.configured();assert configured and configured.mount_prefix=='/deti-marii'
    for path in ['/recorder.html','/deti-marii/other.html','/deti-marii/recorder.html?ticket=forbidden']:
        monkeypatch.setenv('OPORA_CAPTURE_RENDERER_URL','http://127.0.0.1:5174'+path);assert CaptureSettings.configured() is None


def test_same_origin_rtc_requires_dedicated_provider_path(monkeypatch):
    settings=get_settings();monkeypatch.setattr(settings,'app_mount_prefix','/deti-marii')
    for name,value in {'OPORA_CAPTURE_ENABLED':'true','OPORA_ENVIRONMENT':'staging','OPORA_CAPTURE_RENDERER_URL':'https://www.odschool.ru/deti-marii/recorder.html','OPORA_RTC_URL':'https://www.odschool.ru/deti-marii/rtc','OPORA_RTC_PUBLIC_URL':'wss://www.odschool.ru/','OPORA_RTC_API_KEY':'synthetic','OPORA_RTC_API_SECRET':'synthetic-private-test-value'}.items():monkeypatch.setenv(name,value)
    assert CaptureSettings.configured() is None
    monkeypatch.setenv('OPORA_RTC_PUBLIC_URL','wss://www.odschool.ru/deti-marii/rtc')
    assert CaptureSettings.configured() is not None
