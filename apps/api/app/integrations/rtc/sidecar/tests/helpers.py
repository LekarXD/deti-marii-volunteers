"""Общие помощники тестов сайдкара: живой uvicorn в потоке и y-protocol клиент."""

import asyncio
import contextlib
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Optional

import jwt
import httpx
from uuid import uuid4
import uvicorn
from app.integrations.rtc.sidecar.app import create_app
from app.integrations.rtc.sidecar.config import Settings
from pycrdt import (
    Awareness,
    Doc,
    create_awareness_message,
    create_sync_message,
    create_update_message,
    handle_sync_message,
)
from websockets.asyncio.client import connect

SECRET = "s" * 40


def make_settings(tmp: Path, **overrides: Any) -> Settings:
    data = tmp / "data"
    out = tmp / "out"
    data.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)
    params: dict[str, Any] = dict(secret=SECRET, data_dir=data, auth_url='https://opora-api.example.test/board-auth')
    params.update(overrides)
    return Settings(**params)


def token(claims: dict[str, Any], *, secret: str = SECRET, ttl: int = 300) -> str:
    body = dict(claims)
    body.setdefault("exp", int(time.time()) + ttl)
    return jwt.encode(body, secret, algorithm="HS256")


def board_token(room: str, *, can_draw: bool, sub: str = "ident-abcdef12", **extra: Any) -> str:
    claims: dict[str, Any] = {"iss":"opora-api","aud": "opora-board", "room": room, "sub": sub, "can_draw": can_draw,"foundation_id":str(uuid4()),"session_id":str(uuid4()),"auth_session_id":str(uuid4())}
    claims.update(extra)
    return token(claims)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LiveServer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.port = _free_port()
        config = uvicorn.Config(
            create_app(settings,authorization_transport=httpx.MockTransport(lambda request:httpx.Response(200,json={"allowed":True,"can_draw":jwt.decode(request.headers["authorization"].removeprefix("Bearer "),SECRET,algorithms=["HS256"],audience="opora-board")["can_draw"]}))),
            host="127.0.0.1",
            port=self.port,
            log_level="warning",
            access_log=False,
            ws="websockets-sansio",
            ws_max_size=settings.max_message_bytes + 1024,
            lifespan="on",
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def http(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def ws(self) -> str:
        return f"ws://127.0.0.1:{self.port}"

    def start(self) -> "LiveServer":
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started:
            if time.time() > deadline or not self.thread.is_alive():
                raise RuntimeError("sidecar did not start")
            time.sleep(0.02)
        return self

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=15)
        assert not self.thread.is_alive(), "sidecar did not stop"


@contextlib.contextmanager
def live_server(settings: Settings) -> Iterator[LiveServer]:
    srv = LiveServer(settings).start()
    try:
        yield srv
    finally:
        srv.stop()


class YClient:
    """Минимальный клиент y-websocket: синхронизация + отправка обновлений."""

    def __init__(self, url: str):
        self.url = url
        self.doc = Doc()
        self.ws: Any = None
        self.received_awareness = 0
        self.synced = asyncio.Event()
        self._reader: Optional[asyncio.Task] = None
        self._sub: Any = None
        self.send_local_updates = True

    async def __aenter__(self) -> "YClient":
        self.ws = await connect(self.url, max_size=None, open_timeout=5)
        self._sub = self.doc.observe(self._on_local_change)
        self._reader = asyncio.create_task(self._read())
        await self.ws.send(create_sync_message(self.doc))
        await asyncio.wait_for(self.synced.wait(), 5)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._reader:
            self._reader.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._reader
        self.doc.unobserve(self._sub)
        self._sub = None
        with contextlib.suppress(Exception):
            await self.ws.close()

    def _on_local_change(self, event: Any) -> None:
        if getattr(self, "_applying", False) or not self.send_local_updates:
            return
        asyncio.get_running_loop().create_task(self.ws.send(create_update_message(event.update)))

    async def _read(self) -> None:
        async for message in self.ws:
            if not isinstance(message, bytes) or not message:
                continue
            if message[0] == 0:
                self._applying = True
                try:
                    reply = handle_sync_message(message[1:], self.doc)
                finally:
                    self._applying = False
                if reply is not None:
                    await self.ws.send(reply)
                if message[1] == 1:
                    self.synced.set()
            elif message[0] == 1:
                self.received_awareness += 1

    async def send_raw(self, message: bytes) -> None:
        await self.ws.send(message)

    async def send_awareness(self, state: dict[str, Any]) -> None:
        aw = Awareness(self.doc)
        aw.set_local_state(state)
        await self.ws.send(create_awareness_message(aw.encode_awareness_update([self.doc.client_id])))


async def wait_until(predicate: Any, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.02)
    return predicate()
