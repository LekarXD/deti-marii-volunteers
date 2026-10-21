"""Dedicated pinned Yjs/Excalidraw transport, with fresh Opora resource introspection."""
from contextlib import asynccontextmanager,suppress
import re
import anyio
import httpx
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route,WebSocketRoute
from starlette.websockets import WebSocketDisconnect
from .config import Settings,load_settings
from .auth import verify_board_token
from .board import BoardHub
from .store import BoardStore
from .channel import BoardChannel

async def authorize(client,settings,token,grant):
    try:
        response=await client.post(settings.auth_url,headers={'Authorization':'Bearer '+token},timeout=3)
        payload=response.json()
        return response.status_code==200 and payload.get('allowed') is True and payload.get('can_draw')==grant.can_draw
    except (httpx.HTTPError,ValueError):return False

async def board_endpoint(websocket):
    settings=websocket.app.state.settings;topic=websocket.path_params['topic'];token=websocket.query_params.get('token','')
    if not re.fullmatch(r'opora-[A-Za-z0-9_-]{1,120}',topic):await websocket.close(code=1008);return
    try:grant=verify_board_token(token,topic,settings.secret)
    except ValueError:await websocket.close(code=1008);return
    client=websocket.app.state.client
    if not await authorize(client,settings,token,grant):await websocket.close(code=1008);return
    try:
        async with websocket.app.state.hub.join(topic) as room:
            await websocket.accept()
            channel=BoardChannel(websocket,topic,can_draw=grant.can_draw,settings=settings,expires_at=grant.exp)
            async with anyio.create_task_group() as group:
                async def monitor():
                    while True:
                        await anyio.sleep(settings.introspect_seconds)
                        if not await authorize(client,settings,token,grant):
                            with suppress(RuntimeError,WebSocketDisconnect):await websocket.close(code=4401)
                            group.cancel_scope.cancel();return
                group.start_soon(monitor)
                try:await room.serve(channel)
                finally:group.cancel_scope.cancel()
    except WebSocketDisconnect:pass

async def health(request):
    try:await anyio.to_thread.run_sync(request.app.state.store.ping)
    except Exception:return JSONResponse({'ok':False},status_code=503)
    return JSONResponse({'ok':True})

def create_app(settings:Settings|None=None,*,authorization_transport=None):
    from .logredact import install
    import logging
    for name in ('','uvicorn','uvicorn.error','uvicorn.access'):install(logging.getLogger(name))
    settings=settings or load_settings()
    @asynccontextmanager
    async def lifespan(app):
        store=BoardStore(settings.board_db_path);await anyio.to_thread.run_sync(store.open)
        hub=BoardHub(settings,store);await hub.start()
        async with httpx.AsyncClient(follow_redirects=False,transport=authorization_transport) as client:
            app.state.settings=settings;app.state.store=store;app.state.hub=hub;app.state.client=client
            try:yield
            finally:await hub.stop();await anyio.to_thread.run_sync(store.close)
    return Starlette(routes=[WebSocketRoute('/board/{topic}',board_endpoint),Route('/healthz',health)],lifespan=lifespan)
