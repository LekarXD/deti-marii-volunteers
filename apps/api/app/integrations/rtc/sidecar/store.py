"""SQLite-хранилище досок на томе /data.

Схема: одна таблица `board_updates` (комната, порядковый номер, Y-update, время).
Документ = все обновления комнаты по порядку. При закрытии комнаты и после
`compact_after_updates` записей история сжимается в одно обновление.
Доски, которые не менялись дольше срока хранения, удаляются целиком.

Все вызовы синхронные (stdlib sqlite3) — вызывающий код гоняет их через
`anyio.to_thread.run_sync`, соединение защищено блокировкой.
"""

import logging
import sqlite3
import threading
import time
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Optional

log = logging.getLogger("opora_board_sidecar.store")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS board_updates (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    room TEXT NOT NULL,
    yupdate BLOB NOT NULL,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_board_updates_room_seq ON board_updates (room, seq);
CREATE INDEX IF NOT EXISTS idx_board_updates_created ON board_updates (created_at);
"""


class BoardStore:
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None

    def open(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path), check_same_thread=False, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.executescript(_SCHEMA)
        self._conn = conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def _db(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("BoardStore is not open")
        return self._conn

    def ping(self) -> bool:
        with self._lock:
            self._db().execute("SELECT 1").fetchone()
        return True

    def load(self, room: str) -> list[bytes]:
        with self._lock:
            rows = (
                self._db()
                .execute(
                    "SELECT yupdate FROM board_updates WHERE room = ? ORDER BY seq",
                    (room,),
                )
                .fetchall()
            )
        return [bytes(row[0]) for row in rows]

    def append(self, room: str, updates: Sequence[bytes], now: Optional[float] = None) -> int:
        """Дописать обновления; вернуть, сколько всего записей у комнаты."""
        if not updates:
            return self.count(room)
        ts = time.time() if now is None else now
        with self._lock:
            db = self._db()
            db.execute("BEGIN")
            try:
                db.executemany(
                    "INSERT INTO board_updates (room, yupdate, created_at) VALUES (?, ?, ?)",
                    [(room, sqlite3.Binary(u), ts) for u in updates],
                )
                db.execute("COMMIT")
            except sqlite3.Error:
                db.execute("ROLLBACK")
                raise
            row = db.execute("SELECT COUNT(*) FROM board_updates WHERE room = ?", (room,)).fetchone()
        return int(row[0])

    def count(self, room: str) -> int:
        with self._lock:
            row = self._db().execute("SELECT COUNT(*) FROM board_updates WHERE room = ?", (room,)).fetchone()
        return int(row[0])

    def replace(self, room: str, squashed: bytes, now: Optional[float] = None) -> None:
        """Заменить историю комнаты одним сжатым обновлением (атомарно).

        Время сохраняется как время последнего изменения, чтобы сжатие
        не продлевало жизнь заброшенной доске.
        """
        with self._lock:
            db = self._db()
            db.execute("BEGIN IMMEDIATE")
            try:
                row = db.execute("SELECT MAX(created_at) FROM board_updates WHERE room = ?", (room,)).fetchone()
                last_ts = row[0] if row and row[0] is not None else (time.time() if now is None else now)
                db.execute("DELETE FROM board_updates WHERE room = ?", (room,))
                db.execute(
                    "INSERT INTO board_updates (room, yupdate, created_at) VALUES (?, ?, ?)",
                    (room, sqlite3.Binary(squashed), last_ts),
                )
                db.execute("COMMIT")
            except sqlite3.Error:
                db.execute("ROLLBACK")
                raise

    def delete_older_than(self, cutoff_ts: float, *, keep_rooms: Iterable[str] = ()) -> list[str]:
        """Удалить доски, последнее изменение которых раньше `cutoff_ts`."""
        keep = set(keep_rooms)
        with self._lock:
            db = self._db()
            stale: list[tuple[str]] = db.execute(
                "SELECT room FROM board_updates GROUP BY room HAVING MAX(created_at) < ?",
                (cutoff_ts,),
            ).fetchall()
            rooms = [r[0] for r in stale if r[0] not in keep]
            if rooms:
                db.execute("BEGIN")
                try:
                    db.executemany("DELETE FROM board_updates WHERE room = ?", [(r,) for r in rooms])
                    db.execute("COMMIT")
                except sqlite3.Error:
                    db.execute("ROLLBACK")
                    raise
        if rooms:
            with self._lock:
                self._db().execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return rooms
