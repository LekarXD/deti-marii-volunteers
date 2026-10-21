"""Поиск профиля волонтёра на сайте по почте.

TODO: подключить API сайта, когда он появится. Ожидаемый ответ на GET {SITE_API_URL}/volunteers?email=…:
    {"id": "…", "name": "Анна Соколова", "status": "candidate" | "active",
     "roles": ["assistant", …], "days": [5, 6], "phone": "+7…",
     "interview": {"starts_at": "2026-10-22T18:30:00+03:00", "place": "Студия фонда на Новинском б-ре, 25 к10"}}
interview — запись на собеседование, которую человек сделал на сайте (может не быть).
404 — анкеты с такой почтой нет.

Пока SITE_API_URL не задан — демо-режим: любая почта считается зарегистрированной кандидатом без имени,
записанным на собеседование в ближайший будний день в 18:30.
"""
import logging
import os
import ssl
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import aiohttp

from . import db
from .config import SITE_API_TOKEN, SITE_API_URL, TZ

DEFAULT_PLACE = "Студия фонда на Новинском б-ре, 25 к10, подъезд 3"

log = logging.getLogger(__name__)


@dataclass
class Profile:
    email: str
    site_id: str = ""
    name: str = ""
    status: str = "candidate"
    roles: list = field(default_factory=list)
    days: list = field(default_factory=list)
    phone: str = ""
    interview_at: str = ""      # ISO-время собеседования, на которое человек записался на сайте
    interview_place: str = ""
    demo: bool = False


def demo_interview() -> str:
    """TODO: убрать, когда появится API сайта. Ближайший будний день (не сегодня) в 18:30."""
    day = db.now().date() + timedelta(days=1)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return datetime(day.year, day.month, day.day, 18, 30, tzinfo=TZ).isoformat()


async def find_by_email(email: str) -> Profile | None:
    if not SITE_API_URL:
        return Profile(email=email, interview_at=demo_interview(), interview_place=DEFAULT_PLACE, demo=True)
    cafile = os.environ.get("SSL_CERT_FILE")
    headers = {"Authorization": f"Bearer {SITE_API_TOKEN}"} if SITE_API_TOKEN else {}
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as s:
            async with s.get(f"{SITE_API_URL.rstrip('/')}/volunteers", params={"email": email}, headers=headers,
                             ssl=ssl.create_default_context(cafile=cafile) if cafile else None) as r:
                if r.status == 404:
                    return None
                r.raise_for_status()
                data = await r.json()
    except aiohttp.ClientError as e:
        log.warning("API сайта недоступно: %s", e)
        raise
    return Profile(email=email, site_id=str(data.get("id", "")), name=data.get("name", ""),
                   status="active" if data.get("status") == "active" else "candidate",
                   roles=list(data.get("roles", [])), days=[int(x) for x in data.get("days", [])],
                   phone=data.get("phone", ""),
                   interview_at=(data.get("interview") or {}).get("starts_at", ""),
                   interview_place=(data.get("interview") or {}).get("place", "") or DEFAULT_PLACE)
