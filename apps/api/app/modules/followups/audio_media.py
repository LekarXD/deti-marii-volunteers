"""Bounded local decode, with no network/file protocols or shell interpolation."""
import os
import shutil
import subprocess

MAX_BYTES=10*1024*1024
MAX_SECONDS=180
CONTENT_TYPES={'audio/webm':'matroska','audio/ogg':'ogg','audio/mp4':'mov','audio/wav':'wav'}

def audio_duration(data:bytes,content_type:str)->int:
    if not isinstance(data,bytes) or not 0<len(data)<=MAX_BYTES or content_type not in CONTENT_TYPES:
        raise ValueError('invalid_audio')
    signatures={'audio/webm':data.startswith(b'\x1aE\xdf\xa3'),'audio/ogg':data.startswith(b'OggS'),'audio/mp4':len(data)>12 and data[4:8]==b'ftyp','audio/wav':len(data)>12 and data[:4]==b'RIFF' and data[8:12]==b'WAVE'}
    if not signatures[content_type]:raise ValueError('audio_container_invalid')
    executable=shutil.which('ffmpeg')
    if not executable:raise ValueError('audio_decoder_unavailable')
    # Decode at most 181 seconds. PCM output is capped below 6MB independently
    # of an attacker-controlled container duration/sample rate/compression ratio.
    try:
        result=subprocess.run([executable,'-nostdin','-hide_banner','-loglevel','error',
            '-threads','1','-max_alloc','16777216','-protocol_whitelist','pipe','-f',CONTENT_TYPES[content_type],'-i','pipe:0',
            '-map','0:a:0','-vn','-t','181','-ac','1','-ar','16000','-f','s16le','pipe:1'],
            input=data,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=20,check=False,env={'PATH':os.defpath,'LANG':'C'},start_new_session=True)
    except (OSError,subprocess.TimeoutExpired) as exc:raise ValueError('audio_decode_failed') from exc
    size=len(result.stdout)
    if result.returncode or not 0<size<=MAX_SECONDS*16000*2:
        raise ValueError('audio_duration_invalid')
    return max(1,(size+31999)//32000)

def validate_audio(data:bytes,content_type:str)->bool:
    try:audio_duration(data,content_type);return True
    except ValueError:return False
