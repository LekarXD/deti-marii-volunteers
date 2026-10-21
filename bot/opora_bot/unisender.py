"""Отправка писем через Unisender Go (transactional API, метод email/send.json).

Документация API (у Unisender Go и UniOne оно общее): https://docs.unione.io/en/web-api-ref
Ключ передаётся в заголовке X-API-KEY. Подстановки в письме — {{name}} без пробелов внутри скобок.
Пока UNISENDER_API_KEY пуст — тестовый режим: письмо не уходит, а сохраняется в data/emails/.
"""
import json
import logging
import os
import ssl
from dataclasses import dataclass
from pathlib import Path

import aiohttp

from . import db
from .config import (BASE, UNISENDER_API_KEY, UNISENDER_API_URL, UNISENDER_FROM_EMAIL, UNISENDER_FROM_NAME,
                     UNISENDER_TEMPLATE_ID)

log = logging.getLogger(__name__)
TEMPLATES = BASE / "email_templates"
DRY_DIR = BASE / "data" / "emails"
SUBJECT = "Код для входа в бот фонда «Дети Марии»"


@dataclass
class Result:
    ok: bool
    dry_run: bool = False
    detail: str = ""


def render(text: str, subs: dict) -> str:
    for key, value in subs.items():
        text = text.replace("{{" + key + "}}", str(value))
    return text


def payload(email: str, subs: dict, idempotence_key: str) -> dict:
    message = {
        "recipients": [{"email": email, "substitutions": subs}],
        "subject": SUBJECT,
        "from_name": UNISENDER_FROM_NAME,
        "track_links": 0,
        "track_read": 0,
        "idempotence_key": idempotence_key[:64],
    }
    if UNISENDER_FROM_EMAIL:
        message["from_email"] = UNISENDER_FROM_EMAIL
    if UNISENDER_TEMPLATE_ID:
        message["template_id"] = UNISENDER_TEMPLATE_ID
    else:
        message["body"] = {"html": (TEMPLATES / "login_code.html").read_text(encoding="utf-8"),
                           "plaintext": (TEMPLATES / "login_code.txt").read_text(encoding="utf-8")}
    return {"message": message}


def _ssl():
    cafile = os.environ.get("SSL_CERT_FILE")
    return ssl.create_default_context(cafile=cafile) if cafile else None


async def send_login_code(email: str, subs: dict, idempotence_key: str) -> Result:
    if not UNISENDER_API_KEY:
        DRY_DIR.mkdir(parents=True, exist_ok=True)
        name = f"{db.now():%Y%m%d-%H%M%S}-{email.replace('@', '_at_')}"
        (DRY_DIR / f"{name}.html").write_text(render((TEMPLATES / "login_code.html").read_text(encoding="utf-8"), subs),
                                             encoding="utf-8")
        (DRY_DIR / f"{name}.json").write_text(json.dumps(payload(email, subs, idempotence_key), ensure_ascii=False, indent=1),
                                             encoding="utf-8")
        log.info("Unisender Go: тестовый режим, письмо для %s сохранено в %s", email, DRY_DIR / name)
        return Result(ok=True, dry_run=True, detail=str(DRY_DIR / f"{name}.html"))
    if not UNISENDER_FROM_EMAIL and not UNISENDER_TEMPLATE_ID:
        return Result(ok=False, detail="Не задан UNISENDER_FROM_EMAIL")
    headers = {"X-API-KEY": UNISENDER_API_KEY, "Content-Type": "application/json", "Accept": "application/json"}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20)) as s:
            async with s.post(UNISENDER_API_URL, json=payload(email, subs, idempotence_key), headers=headers, ssl=_ssl()) as r:
                data = await r.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError) as e:
        log.warning("Unisender Go недоступен: %s", e)
        return Result(ok=False, detail=type(e).__name__)
    if data.get("status") == "success" and email in data.get("emails", []):
        return Result(ok=True, detail=data.get("job_id", ""))
    reason = (data.get("failed_emails") or {}).get(email) or data.get("message") or str(data)
    log.warning("Unisender Go отказал для %s: %s", email, reason)
    return Result(ok=False, detail=str(reason))
