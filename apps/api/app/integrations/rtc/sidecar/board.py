"""Доска: комнаты pycrdt-websocket + SQLite-хранилище.

Комната живёт, пока к ней подключён хоть один клиент; при закрытии история
сжимается в одно обновление. Протокол и права — в `channel.py`.
"""

import gc
import logging
import math
import time
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass, field
from typing import Any, Optional

import anyio
from anyio.abc import TaskGroup
from anyio.streams.memory import MemoryObjectReceiveStream, MemoryObjectSendStream
from pycrdt import Doc
from pycrdt.websocket import YRoom

from .channel import MSG_AWARENESS, MalformedMessage, awareness_payload, parse_awareness_update
from .config import Settings
from .store import BoardStore

log = logging.getLogger("opora_board_sidecar.board")


class RoomUnavailable(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _room_exception_logger(exception: Exception, logger: logging.Logger) -> bool:
    logger.error("board room error: %s", type(exception).__name__, exc_info=exception)
    return True


def _message_error(exc: Exception, message: bytes, channel: Any) -> bool:
    log.warning(
        "board message rejected room=%s type=%s len=%d",
        getattr(channel, "path", "?"),
        type(exc).__name__,
        len(message),
    )
    return True


def awareness_filter(room: YRoom, max_clients: int) -> Callable[[bytes], bool]:
    """`YRoom.on_message`: True — сообщение не рассылать и не применять.

    pycrdt рассылает каждое awareness-сообщение всем в комнате, не глядя,
    новое ли оно, а клиент y-websocket пересылает обратно каждое полученное
    чужое изменение. Без фильтра одно движение курсора давало N² кадров
    (замер: 16 клиентов, 10 движений — 2 560 кадров вместо 160). Пропускаем,
    как сервер y-websocket, только то, что меняет состояние (clock новее),
    и не даём раздуть комнату выдуманными client_id.
    """

    def skip(message: bytes) -> bool:
        if not message or message[0] != MSG_AWARENESS:
            return False
        try:
            entries = parse_awareness_update(awareness_payload(message))
        except MalformedMessage:
            return True
        meta, states = room.awareness.meta, room.awareness.states
        fresh = False
        unknown = 0
        for client_id, clock, removal in entries:
            known = meta.get(client_id)
            if known is None:
                unknown += 1
            current = 0 if known is None else known["clock"]
            if current < clock or (current == clock and removal and client_id in states):
                fresh = True
        if unknown and len(meta) + unknown > max_clients:
            return True
        return not fresh

    return skip


@dataclass
class _RoomEntry:
    topic: str
    room: YRoom
    doc: Doc
    send: MemoryObjectSendStream
    writer_done: anyio.Event
    subscription: Any = None
    connections: int = 0
    write_errors: int = field(default=0)
    compact_pending: bool = field(default=False)


class BoardHub:
    """Живые комнаты досок; комната закрывается, когда уходит последний клиент."""

    def __init__(self, settings: Settings, store: BoardStore):
        self.settings = settings
        self.store = store
        self._rooms: dict[str, _RoomEntry] = {}
        self._lock = anyio.Lock()
        self._tg: Optional[TaskGroup] = None
        self._tg_cm: Any = None

    # --- жизненный цикл -------------------------------------------------
    async def start(self) -> None:
        self._tg_cm = anyio.create_task_group()
        self._tg = await self._tg_cm.__aenter__()
        self._tg.start_soon(self._cleanup_loop)

    async def stop(self) -> None:
        with anyio.CancelScope(shield=True):
            async with self._lock:
                for topic in list(self._rooms):
                    entry = self._rooms.get(topic)
                    if entry is not None:
                        await self._close_room_safely(entry)
        if self._tg is not None:
            self._tg.cancel_scope.cancel()
            await self._tg_cm.__aexit__(None, None, None)
            self._tg = None

    @property
    def active_rooms(self) -> dict[str, int]:
        return {t: e.connections for t, e in self._rooms.items()}

    # --- подключение -----------------------------------------------------
    @asynccontextmanager
    async def join(self, topic: str) -> AsyncIterator[YRoom]:
        async with self._lock:
            entry = self._rooms.get(topic)
            if entry is None:
                if len(self._rooms) >= self.settings.max_rooms:
                    raise RoomUnavailable("too_many_rooms")
                entry = await self._open_room(topic)
            if entry.connections >= self.settings.max_connections_per_room:
                raise RoomUnavailable("room_full")
            entry.connections += 1
        try:
            yield entry.room
        finally:
            with anyio.CancelScope(shield=True):
                async with self._lock:
                    entry.connections -= 1
                    if entry.connections <= 0 and self._rooms.get(topic) is entry:
                        await self._close_room_safely(entry)

    async def _open_room(self, topic: str) -> _RoomEntry:
        assert self._tg is not None, "BoardHub is not started"
        updates = await anyio.to_thread.run_sync(self.store.load, topic)
        doc = Doc()
        bad = 0
        for update in updates:
            try:
                doc.apply_update(update)
            except Exception:  # noqa: BLE001 — битая запись не должна ронять доску
                bad += 1
        if bad:
            log.error("board load room=%s skipped %d corrupt updates", topic, bad)
        room = YRoom(ready=True, ydoc=doc, exception_handler=_room_exception_logger, log=log)
        room.on_message_error = _message_error
        room.on_message = awareness_filter(room, self.settings.max_awareness_clients)
        await self._tg.start(room.start)
        await room.ydoc_observed.wait()
        send, receive = anyio.create_memory_object_stream(max_buffer_size=16)
        entry = _RoomEntry(topic=topic, room=room, doc=doc, send=send, writer_done=anyio.Event())

        def _on_change(event: Any) -> None:
            try:
                send.send_nowait(bytes(event.update))
            except anyio.WouldBlock:
                # Keep the CRDT source of truth and coalesce pressure into one bounded snapshot.
                entry.compact_pending = True
            except (anyio.ClosedResourceError, anyio.BrokenResourceError):
                log.error("board update after close room=%s (not persisted)", topic)

        entry.subscription = doc.observe(_on_change)
        self._tg.start_soon(self._writer, entry, receive)
        self._rooms[topic] = entry
        log.info("board room opened room=%s stored_updates=%d", topic, len(updates))
        return entry

    async def _writer(self, entry: _RoomEntry, receive: MemoryObjectReceiveStream) -> None:
        try:
            async with receive:
                async for update in receive:
                    batch = [update]
                    while True:
                        try:
                            batch.append(receive.receive_nowait())
                        except (anyio.WouldBlock, anyio.EndOfStream):
                            break
                    await self._persist(entry, batch)
                    while entry.compact_pending:
                        entry.compact_pending = False
                        await self._compact(entry)
        finally:
            entry.writer_done.set()

    async def _persist(self, entry: _RoomEntry, batch: list) -> None:
        try:
            total = await anyio.to_thread.run_sync(self.store.append, entry.topic, batch)
        except Exception:  # noqa: BLE001
            entry.write_errors += 1
            log.exception("board persist failed room=%s updates=%d", entry.topic, len(batch))
            return
        if total >= self.settings.compact_after_updates:
            await self._compact(entry)

    async def _compact(self, entry: _RoomEntry) -> None:
        squashed = entry.doc.get_update()
        try:
            await anyio.to_thread.run_sync(self.store.replace, entry.topic, squashed)
        except Exception:  # noqa: BLE001
            log.exception("board compact failed room=%s", entry.topic)

    async def _close_room_safely(self, entry: _RoomEntry) -> None:
        # Сбой одной комнаты не должен мешать закрыть остальные (stop) или
        # уронить обработчик соединения (join).
        try:
            await self._close_room(entry)
        except Exception:  # noqa: BLE001
            log.exception("board close failed room=%s", entry.topic)

    async def _close_room(self, entry: _RoomEntry) -> None:
        self._rooms.pop(entry.topic, None)
        try:
            with suppress(RuntimeError):
                await entry.room.stop()
            if entry.subscription is not None:
                entry.doc.unobserve(entry.subscription)
                entry.subscription = None
            # Объекты pycrdt привязаны к потоку: рвём циклы и собираем мусор здесь,
            # в потоке event loop, чтобы их не добил GC в потоке-исполнителе.
            entry.room._subscription = None
        finally:
            # Очередь записи закрываем и дожидаемся всегда — иначе хвост
            # обновлений потеряется, а писатель повиснет в группе задач хаба.
            entry.send.close()
            await entry.writer_done.wait()
        try:
            count = await anyio.to_thread.run_sync(self.store.count, entry.topic)
            if count > 1:
                await self._compact(entry)
        except Exception:  # noqa: BLE001
            log.exception("board final compact failed room=%s", entry.topic)
        finally:
            entry.room = None  # type: ignore[assignment]
            gc.collect()
            log.info("board room closed room=%s", entry.topic)

    # --- уборка ----------------------------------------------------------
    async def cleanup_once(self, now: Optional[float] = None) -> int:
        ts = time.time() if now is None else now
        cutoff = ts - self.settings.board_retention_days * 86400
        removed = await anyio.to_thread.run_sync(
            lambda: self.store.delete_older_than(cutoff, keep_rooms=list(self._rooms))
        )
        if removed:
            log.info("board cleanup removed=%d", len(removed))
        return len(removed)

    async def _cleanup_loop(self) -> None:
        while True:
            try:
                await self.cleanup_once()
            except Exception:  # noqa: BLE001
                log.exception("board cleanup failed")
            await anyio.sleep(self.settings.cleanup_interval_s)
