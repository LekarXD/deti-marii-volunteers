"""Decode generated local fixtures only: no microphone or external ASR access."""
import io
import subprocess
import wave
import pytest
from app.modules.followups import audio_media


def wav(seconds=1):
    target=io.BytesIO()
    with wave.open(target,'wb') as output:
        output.setnchannels(1);output.setsampwidth(2);output.setframerate(16000)
        output.writeframes(b'\0\0'*int(seconds*16000))
    return target.getvalue()


def test_real_decoder_accepts_actual_audio_and_enforces_three_minutes():
    assert audio_media.audio_duration(wav(),'audio/wav')==1
    assert audio_media.audio_duration(wav(180),'audio/wav')==180
    with pytest.raises(ValueError):audio_media.audio_duration(wav(180.1),'audio/wav')
    with pytest.raises(ValueError):audio_media.audio_duration(b'not audio','audio/wav')
    with pytest.raises(ValueError):audio_media.audio_duration(wav(),'audio/ogg')
    with pytest.raises(ValueError):audio_media.audio_duration(b'\0'*(audio_media.MAX_BYTES+1),'audio/wav')


def test_decoder_has_no_inherited_secrets_network_protocols_or_unbounded_decode(monkeypatch):
    captured={}
    def run(command,**kwargs):
        captured.update(command=command,**kwargs)
        return subprocess.CompletedProcess(command,0,b'\0\0'*16000)
    monkeypatch.setattr(audio_media.subprocess,'run',run)
    assert audio_media.audio_duration(wav(),'audio/wav')==1
    command=captured['command']
    assert command[command.index('-protocol_whitelist')+1]=='pipe'
    assert command[command.index('-t')+1]=='181'
    assert captured['timeout']==20 and set(captured['env'])=={'PATH','LANG'}
    assert captured['start_new_session'] is True


def test_decoder_timeout_fails_closed(monkeypatch):
    def run(*args,**kwargs):raise subprocess.TimeoutExpired('ffmpeg',20)
    monkeypatch.setattr(audio_media.subprocess,'run',run)
    assert audio_media.validate_audio(wav(),'audio/wav') is False
