import smtplib
import pytest
from app.core.config import get_settings
from app.integrations.delivery.email import deliver_email, readiness

@pytest.mark.asyncio
async def test_unconfigured_provider_never_reports_delivery(monkeypatch):
    settings=get_settings()
    monkeypatch.setattr(settings,'dev_inbox',False)
    monkeypatch.setattr(settings,'smtp_host',None)
    monkeypatch.setattr(smtplib,'SMTP',lambda *a,**k:pytest.fail('No network without provider configuration'))
    result=await deliver_email({'purpose':'login','to':'invented@example.test','challenge_id':'fake','token':'not-a-real-token'})
    assert result.state=='unavailable'
    assert readiness()['state']=='unavailable'

@pytest.mark.asyncio
async def test_smtp_unknown_outcome_is_not_claimed_delivered(monkeypatch):
    settings=get_settings()
    for key,value in {'dev_inbox':False,'smtp_host':'smtp.example.test','smtp_from':'opora@example.test','smtp_starttls':False}.items():
        monkeypatch.setattr(settings,key,value)
    class UnknownSMTP:
        def __init__(self,*a,**k): pass
        def ehlo(self): pass
        def send_message(self,email): raise smtplib.SMTPServerDisconnected('simulated lost DATA response')
        def close(self): pass
    monkeypatch.setattr(smtplib,'SMTP',UnknownSMTP)
    assert (await deliver_email({'purpose':'login','to':'invented@example.test','challenge_id':'fake','token':'not-a-real-token'})).state=='unknown'

@pytest.mark.asyncio
async def test_development_inbox_is_explicit_and_never_calls_smtp(monkeypatch):
    monkeypatch.setattr(get_settings(),'dev_inbox',True)
    monkeypatch.setattr(smtplib,'SMTP',lambda *a,**k:pytest.fail('Development inbox must never send SMTP'))
    assert (await deliver_email({'purpose':'login'})).state=='dev_inbox'
    assert readiness()['state']=='development_only'
