"""SQLite: люди, события, приглашения, встречи, вопросы, отложенные сообщения."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from .config import DB_PATH, TZ

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,            -- chat id в Telegram
    name TEXT, phone TEXT, username TEXT,
    status TEXT NOT NULL DEFAULT 'new', -- new · candidate · active
    is_coordinator INTEGER NOT NULL DEFAULT 0,
    roles TEXT NOT NULL DEFAULT '',     -- ключи ролей через запятую
    days TEXT NOT NULL DEFAULT '',      -- дни недели 0..6 через запятую
    prefs TEXT NOT NULL DEFAULT '{}',
    blocked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL, kind TEXT, format TEXT, program TEXT, group_name TEXT,
    role TEXT, place TEXT, start_date TEXT NOT NULL, end_date TEXT,
    time TEXT DEFAULT '', end_time TEXT DEFAULT '',
    need INTEGER NOT NULL DEFAULT 0,
    repeat TEXT NOT NULL DEFAULT 'none', weekdays TEXT DEFAULT '',
    cancelled_dates TEXT NOT NULL DEFAULT '[]',
    materials TEXT NOT NULL DEFAULT '[]',
    memo TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS invites (
    event_id TEXT, date TEXT, user_id INTEGER,
    status TEXT NOT NULL,               -- invited · accepted · declined · confirmed · attended · absent · removed
    invited_at TEXT, answered_at TEXT,
    hours REAL, feedback TEXT,
    PRIMARY KEY (event_id, date, user_id)
);
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, starts_at TEXT, place TEXT,
    status TEXT NOT NULL DEFAULT 'booked', need_route INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER, text TEXT, asked_at TEXT, answer TEXT
);
CREATE TABLE IF NOT EXISTS auth_codes (
    chat_id INTEGER PRIMARY KEY,
    email TEXT, code_hash TEXT, expires_at TEXT,
    attempts INTEGER NOT NULL DEFAULT 0, sent_at TEXT, sends_hour INTEGER NOT NULL DEFAULT 0, hour_start TEXT
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT, kind TEXT, user_id INTEGER,
    ref TEXT, date TEXT,                -- событие/встреча/вопрос, к которому относится запись
    text TEXT,
    action TEXT,                        -- confirm · outcome · answer — нужно решение координатора
    done INTEGER NOT NULL DEFAULT 0, seen INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at TEXT, audience TEXT, kind TEXT, text TEXT, recipients INTEGER
);
CREATE TABLE IF NOT EXISTS sent (key TEXT PRIMARY KEY, at TEXT);
CREATE TABLE IF NOT EXISTS conv_seen (            -- до какого сообщения разговора на сайте человек уже получил пересылку
    user_id INTEGER, conversation_id TEXT, seq INTEGER NOT NULL,
    PRIMARY KEY (user_id, conversation_id)
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER, text TEXT, markup TEXT, send_after TEXT
);
"""


def now() -> datetime:
    return datetime.now(TZ)


def stamp() -> str:
    return now().isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


@contextmanager
def tx():
    con = connect()
    try:
        yield con
        con.commit()
    finally:
        con.close()


MIGRATIONS = {"users": {"email": "TEXT", "site_id": "TEXT"}, "outbox": {"photo": "TEXT"}, "broadcasts": {"photo": "TEXT"}}


def init() -> None:
    with tx() as con:
        con.executescript(SCHEMA)
        for table, cols in MIGRATIONS.items():
            have = {r["name"] for r in con.execute(f"PRAGMA table_info({table})")}
            for col, kind in cols.items():
                if col not in have:
                    con.execute(f"ALTER TABLE {table} ADD COLUMN {col} {kind}")


def one(sql: str, *args):
    with tx() as con:
        return con.execute(sql, args).fetchone()


def all_(sql: str, *args):
    with tx() as con:
        return con.execute(sql, args).fetchall()


def run(sql: str, *args) -> int:
    with tx() as con:
        cur = con.execute(sql, args)
        return cur.lastrowid


# --- люди -------------------------------------------------------------------

def user(uid: int):
    return one("SELECT * FROM users WHERE id=?", uid)


def ensure_user(uid: int, username: str | None):
    if not user(uid):
        run("INSERT INTO users (id, username, created_at) VALUES (?,?,?)", uid, username or "", stamp())
    return user(uid)


def update_user(uid: int, **fields) -> None:
    keys = ", ".join(f"{k}=?" for k in fields)
    run(f"UPDATE users SET {keys} WHERE id=?", *fields.values(), uid)


def prefs(u) -> dict:
    base = {"news": True, "thanks": True, "paused": False, "mode": "coord"}
    base.update(json.loads(u["prefs"] or "{}"))
    return base


def coordinators():
    return all_("SELECT * FROM users WHERE is_coordinator=1 AND blocked=0")


# --- события ----------------------------------------------------------------

def event(eid: str):
    return one("SELECT * FROM events WHERE id=?", eid)


def events():
    return all_("SELECT * FROM events ORDER BY start_date")


def invite(eid: str, date: str, uid: int):
    return one("SELECT * FROM invites WHERE event_id=? AND date=? AND user_id=?", eid, date, uid)


def team(eid: str, date: str):
    return all_(
        "SELECT i.*, u.name, u.phone, u.username FROM invites i JOIN users u ON u.id=i.user_id "
        "WHERE i.event_id=? AND i.date=? ORDER BY i.invited_at", eid, date)


def set_invite(eid: str, date: str, uid: int, status: str, **extra) -> None:
    if invite(eid, date, uid):
        fields = {"status": status, **extra}
        if status != "invited":
            fields.setdefault("answered_at", stamp())
        keys = ", ".join(f"{k}=?" for k in fields)
        run(f"UPDATE invites SET {keys} WHERE event_id=? AND date=? AND user_id=?", *fields.values(), eid, date, uid)
    else:
        run("INSERT INTO invites (event_id, date, user_id, status, invited_at) VALUES (?,?,?,?,?)",
            eid, date, uid, status, stamp())


def confirmed_count(eid: str, date: str) -> int:
    row = one("SELECT COUNT(*) AS n FROM invites WHERE event_id=? AND date=? AND status IN ('confirmed','attended')",
              eid, date)
    return row["n"]


def mark_sent(key: str) -> bool:
    """True, если ключ новый (сообщение ещё не отправляли)."""
    try:
        run("INSERT INTO sent (key, at) VALUES (?,?)", key, stamp())
        return True
    except sqlite3.IntegrityError:
        return False


# --- лента «Новые уведомления» для координатора -----------------------------------------

def log(kind: str, uid: int | None, text: str, ref: str = "", date: str = "", action: str | None = None) -> int:
    """Запись в ленту координатора вместо отдельного сообщения. action — если нужно решение."""
    return run("INSERT INTO activity (at, kind, user_id, ref, date, text, action) VALUES (?,?,?,?,?,?,?)",
               stamp(), kind, uid, ref, date, text, action)


def resolve(action: str, uid: int | None = None, ref: str = "", date: str = "") -> None:
    sql, args = "UPDATE activity SET done=1 WHERE action=? AND done=0", [action]
    if uid is not None:
        sql += " AND user_id=?"
        args.append(uid)
    if ref:
        sql += " AND ref=?"
        args.append(ref)
    if date:
        sql += " AND date=?"
        args.append(date)
    run(sql, *args)


def open_actions():
    return all_("SELECT * FROM activity WHERE action IS NOT NULL AND done=0 ORDER BY id")
