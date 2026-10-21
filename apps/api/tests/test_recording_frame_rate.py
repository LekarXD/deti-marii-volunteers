"""Reject the measured Linux1000fps duplication artifact and preserve full audio."""
import json
from types import SimpleNamespace
import pytest
from app.modules.recordings import capture


def profile(rate='25/1',frames='231'):
    return {'format':{'duration':'9.24'},'streams':[{'codec_type':'video','codec_name':'h264','width':1920,'height':1080,'r_frame_rate':rate,'avg_frame_rate':rate,'nb_frames':frames},{'codec_type':'audio','codec_name':'aac','duration':'9.219'}]}


@pytest.mark.asyncio
async def test_sparse_input_export_preserves_audio_and_checks_bounded_frames(monkeypatch,tmp_path):
    calls=[]
    async def command(*arguments,**options):
        calls.append((arguments,options))
        return json.dumps(profile()).encode() if arguments[0]=='ffprobe' else b''
    monkeypatch.setattr(capture,'media_command',command)
    result=await capture.encode_and_validate(SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe'),tmp_path/'source.webm',tmp_path/'output.mp4',9219)
    assert result['duration_ms']==9240 and result['frame_rate']==25 and result['video_frames']==231 and result['full_decode']
    # The entire audio duration survives; the fix may not use a truncation shortcut.
    assert '-shortest' not in calls[0][0]
    assert calls[0][1]['timeout']==180 and calls[-1][1]['timeout']==120


@pytest.mark.asyncio
@pytest.mark.parametrize(('rate','frames'),[('1000/1','6642'),('25/1','10000'),('25/1','0'),('25/1','N/A'),('0/0','231'),('N/A','231'),('26/1','231')])
async def test_measured_frame_explosion_and_invalid_probe_never_pass_validation(monkeypatch,tmp_path,rate,frames):
    calls=[]
    async def command(*arguments,**options):
        calls.append(arguments)
        return json.dumps(profile(rate,frames)).encode() if arguments[0]=='ffprobe' else b''
    monkeypatch.setattr(capture,'media_command',command)
    with pytest.raises(capture.MediaValidationError,match='media_frame_rate_mismatch'):
        await capture.encode_and_validate(SimpleNamespace(ffmpeg='ffmpeg',ffprobe='ffprobe'),tmp_path/'source.webm',tmp_path/'output.mp4',9219)
    assert len(calls)==2  # Rejected before reporting full-decode/verified success.
