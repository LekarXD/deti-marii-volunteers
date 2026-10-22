"""Связь с платформой «Опора»: подключение Telegram из профиля и сессия бота от имени человека.

Как устроено (подробно — apps/api/app/modules/notifications/TELEGRAM.md):
- в профиле на сайте человек нажимает «Подключить Telegram» и попадает в бот по ссылке /start bind_…;
  бот пересылает это сообщение платформе (тот же webhook, что ждал бы Telegram), платформа проверяет ссылку;
- дальше бот по секрету OPORA_BOT_API_SECRET получает сессию этого человека и ходит в обычный API сайта,
  как сам человек в браузере. Права координатора у сессии появляются только после /coordinator с кодом
  из приложения-аутентификатора — так же, как на сайте.
"""
import logging
import os
import ssl
import time
import uuid

import aiohttp

from . import config

log = logging.getLogger(__name__)
_sessions: dict[int, tuple[str, float]] = {}  # telegram id → (токен сессии, когда истекает)
_staff: set[int] = set()  # у чьих сессий сейчас есть права координатора


class PlatformError(Exception):
    """Сайт не ответил или ответил не так, как ожидали."""


class NotLinked(PlatformError):
    """Этот Telegram не подключён к профилю на сайте."""


class ApiFailure(PlatformError):
    def __init__(self, status: int, body):
        self.status = status
        self.code = body.get("code", "") if isinstance(body, dict) else ""
        self.message = body.get("message", "") if isinstance(body, dict) else ""
        super().__init__(f"{status} {self.code}")


def enabled() -> bool:
    return config.PLATFORM


def site(path: str = "") -> str:
    """Ссылка на страницу сайта для человека (публичный адрес, не внутренний адрес API)."""
    return (config.OPORA_PUBLIC_URL or config.OPORA_URL) + path


def profile_url() -> str:
    return site("/profile")


def anketa_url() -> str:
    """Анкета на сайте вместо Яндекс-формы, когда платформа подключена."""
    return site("/application") if enabled() else config.ANKETA_URL


def is_staff(telegram_id: int) -> bool:
    return telegram_id in _staff


def _ssl():
    cafile = os.environ.get("SSL_CERT_FILE")
    return ssl.create_default_context(cafile=cafile) if cafile else None


async def _request(method: str, path: str, *, json=None, params=None, headers=None, cookies=None, raw=False):
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20), cookies=cookies) as s:
            async with s.request(method, config.OPORA_URL + path, json=json, params=params, headers=headers or {},
                                 ssl=_ssl()) as r:
                if raw and r.status < 400:
                    return r.status, await r.read()
                body = await r.json(content_type=None) if r.content_length != 0 else None
                return r.status, body
    except (aiohttp.ClientError, TimeoutError, ValueError) as e:
        log.warning("платформа недоступна: %s %s: %s", method, path, e)
        raise PlatformError("unavailable") from e


def _bearer() -> dict:
    return {"Authorization": f"Bearer {config.OPORA_BOT_API_SECRET}"}


async def link(telegram_id: int, is_bot: bool, chat_id: int, chat_type: str, text: str) -> str:
    """Передаёт платформе /start bind_… из личного чата. Ответ: linked · conflict · ignored."""
    update = {"update_id": 0, "message": {"from": {"id": telegram_id, "is_bot": is_bot},
                                          "chat": {"id": chat_id, "type": chat_type}, "text": text}}
    status, body = await _request("POST", "/api/v1/integrations/telegram/webhook", json=update,
                                  headers={"X-Telegram-Bot-Api-Secret-Token": config.OPORA_WEBHOOK_SECRET})
    if status != 200 or not isinstance(body, dict):
        raise PlatformError(f"link {status}")
    state = body.get("state", "ignored")
    if state == "linked":
        forget(telegram_id)  # новая привязка — старая сессия бота больше не нужна
    return state


def forget(telegram_id: int) -> None:
    _sessions.pop(telegram_id, None)
    _staff.discard(telegram_id)


async def open_session(telegram_id: int) -> dict | None:
    """Новая сессия человека для бота. None — этот Telegram не подключён к профилю."""
    status, body = await _request("POST", "/api/v1/integrations/telegram/bot/sessions",
                                  json={"telegram_user_id": telegram_id}, headers=_bearer())
    if status == 404:
        forget(telegram_id)
        return None
    if status != 200 or not isinstance(body, dict):
        raise PlatformError(f"session {status}")
    _staff.discard(telegram_id)
    # запас в 10 минут, чтобы не упереться в истечение посреди запроса
    _sessions[telegram_id] = (body["session_token"], time.time() + 11.8 * 3600)
    return body


async def call(telegram_id: int, method: str, path: str, json=None, headers=None, params=None, raw=False):
    """Запрос к API платформы от имени человека. Возвращает (статус, тело); None — Telegram не подключён."""
    for attempt in (1, 2):
        token, until = _sessions.get(telegram_id, ("", 0.0))
        if not token or until <= time.time():
            was_staff = telegram_id in _staff
            if await open_session(telegram_id) is None:
                return None
            token = _sessions[telegram_id][0]
            if was_staff:  # там, где сайт пускает сотрудников без кода (демо-стенд), права вернутся сами
                await coordinator(telegram_id, "", quiet=True)
                token = _sessions[telegram_id][0]
        status, body = await _request(method, "/api/v1" + path, json=json, params=params, raw=raw,
                                      cookies={"opora_session": token}, headers={**(headers or {}), **_bearer()})
        if status == 401 and attempt == 1:
            _sessions.pop(telegram_id, None)  # сессию отозвали или она истекла — берём новую один раз
            continue
        return status, body
    return None


async def _checked(telegram_id: int, method: str, path: str, json=None, params=None, idempotent=False, raw=False):
    headers = {"Idempotency-Key": str(uuid.uuid4())} if idempotent else None
    res = await call(telegram_id, method, path, json=json, headers=headers, params=params, raw=raw)
    if res is None:
        raise NotLinked()
    status, body = res
    if status >= 400:
        raise ApiFailure(status, body)
    return body


async def get(telegram_id: int, path: str, **params):
    return await _checked(telegram_id, "GET", path, params={k: v for k, v in params.items() if v is not None} or None)


async def download(telegram_id: int, path: str) -> bytes:
    return await _checked(telegram_id, "GET", path, raw=True)


async def post(telegram_id: int, path: str, body: dict | None = None):
    """POST с новым Idempotency-Key: повтор той же команды сайт не выполнит дважды."""
    return await _checked(telegram_id, "POST", path, json=body or {}, idempotent=True)


async def put(telegram_id: int, path: str, body: dict):
    return await _checked(telegram_id, "PUT", path, json=body, idempotent=True)


async def coordinator(telegram_id: int, code: str, quiet: bool = False) -> dict | None:
    """Режим координатора для сессии бота: код из приложения-аутентификатора (на демо-стенде — без кода).
    Возвращает {"is_staff", "permissions"}; ApiFailure — код не подошёл или профиль не сотрудник."""
    try:
        body = await post(telegram_id, "/integrations/telegram/bot/coordinator", {"code": code})
    except ApiFailure:
        if quiet:
            return None
        raise
    if body.get("is_staff"):
        _staff.add(telegram_id)
    return body
