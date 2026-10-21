"""Explicit localhost provider smoke; no browser/device/media permissions.

Not part of the default API suite. Invoke with a private random local fixture file.
"""
import argparse,asyncio,json,time
from pathlib import Path
from urllib.parse import urlencode,urlsplit
from uuid import uuid4
import websockets
from app.integrations.rtc.livekit import RtcSettings,RevocationPolicy,LiveKitAdapter,join_token,room_name,identity

async def run(path):
    fixture=json.loads(Path(path).read_text())
    if urlsplit(fixture['url']).hostname not in ('127.0.0.1','localhost','::1'):raise RuntimeError('Only explicit loopback fixtures are accepted')
    settings=RtcSettings(**fixture);adapter=LiveKitAdapter(settings);room=room_name(uuid4(),uuid4(),1)
    host=identity(uuid4());viewer=identity(uuid4());policy=RevocationPolicy(False)
    host_token=join_token(settings,room=room,participant_identity=host,name='Fixture host',host=True,policy=policy,auth_session_id=uuid4())
    viewer_token=join_token(settings,room=room,participant_identity=viewer,name='Fixture viewer',host=False,policy=policy,auth_session_id=uuid4())
    def url(token):return settings.public_url.rstrip('/')+'/rtc?'+urlencode({'access_token':token,'sdk':'js','version':'2.22.3','protocol':'17','client_protocol':'1','auto_subscribe':'0'})
    sockets=[];evidence={}
    try:
        await adapter.create_room(room)
        for token in (host_token,viewer_token):
            socket=await websockets.connect(url(token),proxy=None,open_timeout=5);sockets.append(socket)
            response=await asyncio.wait_for(socket.recv(),5)
            if not isinstance(response,(bytes,str)) or not response:raise RuntimeError('Missing provider join acknowledgement')
        participants=await adapter.participants(room)
        if {p['identity'] for p in participants}!={host,viewer}:raise RuntimeError('Provider participant set mismatch')
        evidence['real_websocket_participants']=len(participants)
        await adapter.remove_participant(room,viewer,revoked_at=int(time.time()),policy=policy)
        await asyncio.wait_for(sockets[-1].wait_closed(),5)
        # Crucial self-hosted boundary: the PREVIOUS token remains accepted after removal.
        reconnect=await websockets.connect(url(viewer_token),proxy=None,open_timeout=5);sockets.append(reconnect)
        if not await asyncio.wait_for(reconnect.recv(),5):raise RuntimeError('Missing reconnect acknowledgement')
        evidence['previously_issued_token_reconnect_accepted']=True
        evidence['strict_revocation_capability']=settings.capabilities().strict_token_revocation
        evidence['provider_version']='1.13.9'
        evidence['physical_media_requested']=False
        return evidence
    finally:
        for socket in sockets:await socket.close()
        await adapter.close_room(room)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--fixture',required=True);args=parser.parse_args()
    print(json.dumps(asyncio.run(run(args.fixture)),ensure_ascii=False))
