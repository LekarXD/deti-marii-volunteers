"""Токены не должны попадать в журнал.

Пропуск к доске едет в query-строке (`/board/<topic>?token=<JWT>`: так устроен
клиент y-websocket). `access_log=False` выключает только журнал доступа uvicorn,
а строки рукопожатия WebSocket (`"WebSocket /board/…?token=…" [accepted]` / `403`)
uvicorn пишет в `uvicorn.error` — их и чистит этот фильтр.
"""

import logging
import re

_TOKEN = re.compile(r"([?&](?:token|access_token)=)[^&\s\"']+", re.IGNORECASE)
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE)


def redact(text: str) -> str:
    return _BEARER.sub(r"\1REDACTED", _TOKEN.sub(r"\1REDACTED", text))


class RedactTokens(logging.Filter):
    """Переписывает сообщение записи с вычищенными токенами (на уровне обработчика)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except (TypeError, ValueError):
            return True
        cleaned = redact(message)
        if cleaned != message:
            record.msg, record.args = cleaned, None
        return True


def install(root: logging.Logger | None = None) -> None:
    """Повесить фильтр на все обработчики корневого логгера (uvicorn.* туда и уходят)."""
    target = root or logging.getLogger()
    for handler in target.handlers:
        if not any(isinstance(f, RedactTokens) for f in handler.filters):
            handler.addFilter(RedactTokens())
