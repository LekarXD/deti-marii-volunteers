"""Одноразовые коды для входа по почте: 6 цифр, 15 минут, 5 попыток, повтор не чаще раза в минуту и 5 писем в час."""
import hashlib
import re
import secrets
from datetime import datetime, timedelta

from . import db
from .config import CODE_TTL_MINUTES, TOKEN

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
MAX_ATTEMPTS = 5
RESEND_AFTER = timedelta(seconds=60)
MAX_PER_HOUR = 5


def valid_email(text: str) -> str | None:
    email = text.strip().lower()
    return email if EMAIL_RE.match(email) and len(email) <= 254 else None


def mask(email: str) -> str:
    local, domain = email.split("@", 1)
    return (local[0] + "•••" + (local[-1] if len(local) > 2 else "")) + "@" + domain


def _hash(chat_id: int, code: str) -> str:
    return hashlib.sha256(f"{TOKEN}:{chat_id}:{code}".encode()).hexdigest()


def can_send(chat_id: int) -> str | None:
    """None — можно отправлять; иначе текст, почему нельзя."""
    row = db.one("SELECT * FROM auth_codes WHERE chat_id=?", chat_id)
    if not row or not row["sent_at"]:
        return None
    n = db.now()
    if n - datetime.fromisoformat(row["sent_at"]) < RESEND_AFTER:
        return "Код уже отправлен. Новый можно запросить через минуту."
    if row["hour_start"] and n - datetime.fromisoformat(row["hour_start"]) < timedelta(hours=1) and row["sends_hour"] >= MAX_PER_HOUR:
        return "Слишком много писем подряд. Попробуйте через час или напишите координатору."
    return None


def issue(chat_id: int, email: str) -> str:
    code = f"{secrets.randbelow(1_000_000):06d}"
    n = db.now()
    row = db.one("SELECT * FROM auth_codes WHERE chat_id=?", chat_id)
    fresh_hour = not row or not row["hour_start"] or n - datetime.fromisoformat(row["hour_start"]) >= timedelta(hours=1)
    db.run("INSERT OR REPLACE INTO auth_codes (chat_id, email, code_hash, expires_at, attempts, sent_at, sends_hour, hour_start) "
           "VALUES (?,?,?,?,0,?,?,?)", chat_id, email, _hash(chat_id, code),
           (n + timedelta(minutes=CODE_TTL_MINUTES)).isoformat(), n.isoformat(),
           1 if fresh_hour else row["sends_hour"] + 1, n.isoformat() if fresh_hour else row["hour_start"])
    return code


def check(chat_id: int, code: str) -> tuple[str, str | None]:
    """('ok', email) · ('wrong', None) · ('expired', None) · ('locked', None) · ('none', None)."""
    row = db.one("SELECT * FROM auth_codes WHERE chat_id=?", chat_id)
    if not row or not row["code_hash"]:
        return "none", None
    if db.now() > datetime.fromisoformat(row["expires_at"]):
        return "expired", None
    if row["attempts"] >= MAX_ATTEMPTS:
        return "locked", None
    if not secrets.compare_digest(_hash(chat_id, re.sub(r"\D", "", code)), row["code_hash"]):
        db.run("UPDATE auth_codes SET attempts=attempts+1 WHERE chat_id=?", chat_id)
        return ("locked" if row["attempts"] + 1 >= MAX_ATTEMPTS else "wrong"), None
    db.run("UPDATE auth_codes SET code_hash=NULL WHERE chat_id=?", chat_id)  # код одноразовый
    return "ok", row["email"]


def attempts_left(chat_id: int) -> int:
    row = db.one("SELECT attempts FROM auth_codes WHERE chat_id=?", chat_id)
    return MAX_ATTEMPTS - (row["attempts"] if row else 0)
