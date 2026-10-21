"""Канал y-websocket поверх Starlette WebSocket: права, лимиты, таймаут простоя.

Протокол — y-protocols в бинарных кадрах (совместим с клиентом `y-websocket` 3.x):
первый varUint — тип (0 sync, 1 awareness, 2 auth, 3 query-awareness), у sync
второй varUint — подтип (0 step1, 1 step2, 2 update); оба < 128, т. е. один байт.

Право рисовать проверяет сервер: от клиента без `can_draw` отбрасываются
sync step2 и update (они меняют документ). Step1 (запрос состояния) и
awareness (курсоры) проходят — зритель видит доску и чужие курсоры, но
awareness крупнее `max_awareness_bytes` отбрасывается (его рассылают всем).
Step1 — тоже под лимитом частоты (у всех, не только у зрителей): ответ на
него — весь документ, и без лимита трёхбайтовые запросы от клиента, который
не читает сокет, копили бы в памяти сервера копии документа без предела.

Кадр проверяется по структуре до pycrdt (`well_formed`): ровно одна
varUint8Array после заголовка, varUint не длиннее 8 байт, awareness разобран
целиком. Разбор varUint у pycrdt квадратичный по длине цепочки (64 КиБ из 0xFF —
~0,5 с CPU в потоке event loop на одно сообщение), а битый awareness pycrdt
рассылает всем ещё до того, как сам на нём споткнётся.

Соединение живёт не дольше токена (`exp` + leeway): по истечении закрывается
кодом 4401, клиент берёт новый токен (`GET …/studio/board-token`) и
переподключается. Так отзыв права рисовать доходит за один TTL токена.
"""

import json
import logging
import time
from typing import Optional

import anyio
from starlette.websockets import WebSocket, WebSocketState

from .config import Settings

log = logging.getLogger("opora_board_sidecar.board")

MSG_SYNC = 0
MSG_AWARENESS = 1
SYNC_STEP1 = 0
SYNC_STEP2 = 1
SYNC_UPDATE = 2

#: y-protocols пишет числа JS (≤ 2**53) — это не больше 8 байт varUint.
MAX_VARUINT_BYTES = 8

CLOSE_POLICY = 1008
CLOSE_TOO_BIG = 1009
CLOSE_INTERNAL = 1011
CLOSE_TRY_AGAIN = 1013
CLOSE_TOKEN_EXPIRED = 4401
CLOSE_IDLE = 4408


def message_allowed(message: bytes, *, can_draw: bool) -> bool:
    """Пропускать ли сообщение клиента в комнату."""
    if len(message) < 2:
        return False
    kind = message[0]
    if kind == MSG_AWARENESS:
        return True
    if kind == MSG_SYNC:
        sub = message[1]
        if sub == SYNC_STEP1:
            return True
        if sub in (SYNC_STEP2, SYNC_UPDATE):
            return can_draw
        return False
    # auth / query-awareness / неизвестное — pycrdt их всё равно не обрабатывает.
    return False


class MalformedMessage(ValueError):
    """Кадр не похож на сообщение y-protocols."""


def read_var_uint(data: bytes, pos: int) -> tuple[int, int]:
    """varUint с позиции `pos` → (значение, позиция после него)."""
    value = 0
    for index in range(MAX_VARUINT_BYTES):
        if pos >= len(data):
            raise MalformedMessage("truncated")
        byte = data[pos]
        pos += 1
        value |= (byte & 0x7F) << (7 * index)
        if byte < 0x80:
            return value, pos
    raise MalformedMessage("varuint_too_long")


def var_bytes_end(data: bytes, pos: int) -> tuple[int, int]:
    """varUint8Array с позиции `pos` → (начало данных, конец данных)."""
    length, start = read_var_uint(data, pos)
    end = start + length
    if end > len(data):
        raise MalformedMessage("truncated")
    return start, end


def parse_awareness_update(update: bytes) -> list[tuple[int, int, bool]]:
    """Awareness update → [(client_id, clock, это_удаление)]; иначе MalformedMessage."""
    try:
        count, pos = read_var_uint(update, 0)
        entries = []
        for _ in range(count):
            client_id, pos = read_var_uint(update, pos)
            clock, pos = read_var_uint(update, pos)
            start, pos = var_bytes_end(update, pos)
            state = update[start:pos]
            # pycrdt: пустая строка и JSON null — удаление состояния клиента.
            removal = state in (b"", b"null")
            if not removal:
                json.loads(state.decode("utf-8"))
            entries.append((client_id, clock, removal))
    except MalformedMessage:
        raise
    except (ValueError, RecursionError) as exc:  # не UTF-8 / не JSON
        raise MalformedMessage("bad_state") from exc
    if pos != len(update):
        raise MalformedMessage("trailing_bytes")
    return entries


def awareness_payload(message: bytes) -> bytes:
    start, end = var_bytes_end(message, 1)
    if end != len(message):
        raise MalformedMessage("trailing_bytes")
    return message[start:end]


def well_formed(message: bytes) -> bool:
    """Кадр sync/awareness устроен как у y-protocols (тип и права — `message_allowed`)."""
    try:
        if message[0] == MSG_SYNC:
            _, end = var_bytes_end(message, 2)
            return end == len(message)
        if message[0] == MSG_AWARENESS:
            parse_awareness_update(awareness_payload(message))
            return True
    except MalformedMessage:
        return False
    return False


class BoardChannel:
    """`pycrdt.Channel` поверх Starlette WebSocket с фильтром прав и лимитами."""

    def __init__(
        self,
        websocket: WebSocket,
        topic: str,
        *,
        can_draw: bool,
        settings: Settings,
        expires_at: Optional[float] = None,
    ):
        self._ws = websocket
        self._topic = topic
        self._can_draw = can_draw
        self._max_bytes = settings.max_message_bytes
        self._max_awareness = settings.max_awareness_bytes
        self._idle = settings.idle_timeout_s
        # Unix-время, после которого соединение закрывается (exp токена + leeway).
        self._deadline = None if expires_at is None else float(expires_at) + settings.jwt_leeway_s
        self._aw_rate = float(settings.awareness_per_second)
        self._aw_tokens = float(settings.awareness_burst)
        self._aw_burst = float(settings.awareness_burst)
        self._aw_at = time.monotonic()
        self._sync_rate = settings.sync_requests_per_minute / 60.0
        self._sync_burst = float(settings.sync_requests_burst)
        self._sync_tokens = self._sync_burst
        self._sync_at = self._aw_at
        self._send_lock = anyio.Lock()
        self._closed = False
        self.dropped = 0
        self.close_reason: Optional[str] = None

    @property
    def path(self) -> str:
        return self._topic

    def __aiter__(self) -> "BoardChannel":
        return self

    async def __anext__(self) -> bytes:
        while True:
            message = await self._receive()
            if message is None:
                raise StopAsyncIteration()
            if message_allowed(message, can_draw=self._can_draw):
                if message[0] == MSG_AWARENESS:
                    # Размер и частота — до разбора: JSON состояний разбираем не впустую.
                    ok = len(message) <= self._max_awareness and self._take_awareness_token() and well_formed(message)
                elif message[1] == SYNC_STEP1:
                    ok = well_formed(message) and self._take_sync_request_token()
                else:
                    ok = well_formed(message)
                if ok:
                    return message
            self.dropped += 1

    async def recv(self) -> bytes:
        return await self.__anext__()

    def _take_awareness_token(self) -> bool:
        # Курсоры шлются на каждое движение мыши и рассылаются всем в комнате —
        # лишнее молча отбрасываем. Sync-сообщения не трогаем: пропуск update
        # рассинхронизировал бы документ.
        now = time.monotonic()
        self._aw_tokens = min(self._aw_burst, self._aw_tokens + (now - self._aw_at) * self._aw_rate)
        self._aw_at = now
        if self._aw_tokens >= 1.0:
            self._aw_tokens -= 1.0
            return True
        return False

    def _take_sync_request_token(self) -> bool:
        now = time.monotonic()
        self._sync_tokens = min(self._sync_burst, self._sync_tokens + (now - self._sync_at) * self._sync_rate)
        self._sync_at = now
        if self._sync_tokens >= 1.0:
            self._sync_tokens -= 1.0
            return True
        return False

    async def _receive(self) -> Optional[bytes]:
        if self._closed:
            return None
        timeout = float(self._idle)
        # Чем кончится ожидание, решаем заранее: перепроверка time.time() после
        # move_on_after (тот меряет монотонными часами) иногда давала «чуть рано»
        # и закрытие по токену уходило кодом простоя 4408.
        expiring = False
        if self._deadline is not None:
            remaining = self._deadline - time.time()
            if remaining <= 0:
                await self.close(CLOSE_TOKEN_EXPIRED, "token_expired")
                return None
            if remaining <= timeout:
                timeout, expiring = remaining, True
        with anyio.move_on_after(timeout) as scope:
            try:
                event = await self._ws.receive()
            except RuntimeError:
                self._closed = True
                return None
        if scope.cancelled_caught:
            if expiring:
                await self.close(CLOSE_TOKEN_EXPIRED, "token_expired")
            else:
                await self.close(CLOSE_IDLE, "idle")
            return None
        if event["type"] == "websocket.disconnect":
            self._closed = True
            return None
        data = event.get("bytes")
        if data is None:
            # Текстовые кадры y-websocket не шлёт — игнорируем.
            return b""
        if len(data) > self._max_bytes:
            await self.close(CLOSE_TOO_BIG, "message_too_big")
            return None
        return bytes(data)

    async def send(self, message: bytes) -> None:
        # Ошибки отправки глушим: иначе они роняют задачи комнаты pycrdt.
        if self._closed:
            return
        async with self._send_lock:
            try:
                await self._ws.send_bytes(message)
            except Exception as exc:  # noqa: BLE001 — клиент ушёл, это норма
                self._closed = True
                log.debug("board send failed room=%s: %s", self._topic, type(exc).__name__)

    async def close(self, code: int, reason: str) -> None:
        if self._closed:
            return
        self._closed = True
        self.close_reason = reason
        try:
            if self._ws.application_state == WebSocketState.CONNECTED:
                await self._ws.close(code=code)
        except Exception as exc:  # noqa: BLE001
            log.debug("board close failed room=%s: %s", self._topic, type(exc).__name__)
