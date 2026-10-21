"""Actual local WebSocket/Yjs connections; introspection HTTP transport is controlled."""
import asyncio
from uuid import uuid4
import pytest
from pycrdt import Map,create_update_message
from websockets.exceptions import InvalidStatus
from app.integrations.rtc.sidecar.channel import message_allowed,well_formed
from app.integrations.rtc.sidecar.auth import verify_board_token
from helpers import YClient,board_token,live_server,make_settings,wait_until
ROOM='opora-f'+uuid4().hex+'-s'+uuid4().hex+'-g1'

def url(server,token):return f'{server.ws}/board/{ROOM}?token={token}'
def contents(client):return dict(client.doc.get('elements',type=Map).items())

def test_protocol_rejects_viewer_updates_and_malformed_lengths():
    assert not message_allowed(b'\x00\x02\x01\x00',can_draw=False)
    assert message_allowed(b'\x00\x00\x01\x00',can_draw=False)
    assert not well_formed(b'\x00\x02'+b'\xff'*20)

def test_real_drawer_viewer_sync_cannot_escalate_and_persists(tmp_path):
    async def scenario(server):
        async with YClient(url(server,board_token(ROOM,can_draw=True))) as host,YClient(url(server,board_token(ROOM,can_draw=False))) as viewer:
            host.doc['elements']=Map();host.doc.get('elements',type=Map)['host-shape']='rectangle'
            assert await wait_until(lambda:contents(viewer).get('host-shape')=='rectangle')
            viewer.doc.get('elements',type=Map)['forged']='not-authorized'
            host.doc.get('elements',type=Map)['barrier']='host'
            assert await wait_until(lambda:contents(viewer).get('barrier')=='host')
            await asyncio.sleep(.1);assert 'forged' not in contents(host)
    settings=make_settings(tmp_path)
    with live_server(settings) as server:asyncio.run(scenario(server))
    async def read(server):
        async with YClient(url(server,board_token(ROOM,can_draw=False))) as viewer:
            assert await wait_until(lambda:contents(viewer).get('host-shape')=='rectangle')
            assert 'forged' not in contents(viewer)
    with live_server(settings) as server:asyncio.run(read(server))

def test_bad_signature_and_wrong_room_rejected_before_connect(tmp_path):
    async def scenario(server):
        with pytest.raises(InvalidStatus):
            async with YClient(url(server,'not-a-signed-token')):pass
        with pytest.raises(InvalidStatus):
            async with YClient(url(server,board_token('opora-other-room',can_draw=True))):pass
    with live_server(make_settings(tmp_path)) as server:asyncio.run(scenario(server))
