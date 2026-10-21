"""Opt-in real JS y-websocket client against isolated loopback sidecar.

Run with this sidecar's separate Python runtime and installed web dependencies.
"""
import json,subprocess,tempfile
from pathlib import Path
from uuid import uuid4
from helpers import make_settings,live_server,board_token

def run():
    here=Path(__file__).resolve().parent;root=here.parents[6]
    with tempfile.TemporaryDirectory(prefix='opora-js-board-') as directory:
        path=Path(directory);room='opora-f'+uuid4().hex+'-s'+uuid4().hex+'-g1'
        with live_server(make_settings(path)) as server:
            fixture=path/'fixture.json';fixture.write_text(json.dumps({'url':server.ws+'/board','room':room,'host':board_token(room,can_draw=True),'viewer':board_token(room,can_draw=False)}));fixture.chmod(0o600)
            result=subprocess.run(['node',str(here/'js_client_smoke.mjs'),str(fixture),str(root/'apps/web/node_modules')],capture_output=True,timeout=15)
            if result.returncode:raise RuntimeError('Actual JS client protocol smoke failed; raw transport errors suppressed')
            evidence=json.loads(result.stdout)
            assert evidence=={'actual_js_y_websocket':True,'host_draw_sync':True,'viewer_update_denied':True,'physical_media_requested':False}
            print(json.dumps(evidence))

if __name__=='__main__':run()
