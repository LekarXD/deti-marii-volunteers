"""Настройки бота. Секреты читаются из bot/.env (файл не попадает в git)."""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_env(BASE / ".env")

TOKEN = os.environ.get("BOT_TOKEN", "")
# Код, по которому сотрудник фонда входит как координатор: /coordinator <код>
COORDINATOR_CODE = os.environ.get("COORDINATOR_CODE", "")
# TODO: заменить на анкету на сайте фонда, когда она появится. Сейчас — текущая Яндекс-форма фонда.
ANKETA_URL = os.environ.get("ANKETA_URL", "https://forms.yandex.ru/u/691b104e49af47a8c29589c3/")

# Вход по почте: код приходит письмом через Unisender Go.
# Пока UNISENDER_API_KEY пуст, бот в тестовом режиме: письмо сохраняется в data/emails/, код показывается в чате.
UNISENDER_API_KEY = os.environ.get("UNISENDER_API_KEY", "")
UNISENDER_API_URL = os.environ.get("UNISENDER_API_URL", "https://go1.unisender.ru/ru/transactional/api/v1/email/send.json")
UNISENDER_FROM_EMAIL = os.environ.get("UNISENDER_FROM_EMAIL", "")  # TODO: адрес фонда, подтверждённый в Unisender Go
UNISENDER_FROM_NAME = os.environ.get("UNISENDER_FROM_NAME", "Фонд «Дети Марии»")
# TODO: если макет письма заведут в Unisender Go как шаблон — указать его id; иначе уходит наш HTML из email_templates/.
UNISENDER_TEMPLATE_ID = os.environ.get("UNISENDER_TEMPLATE_ID", "")
CODE_TTL_MINUTES = 15

# TODO: API сайта для поиска профиля по почте. Пока пусто — демо-режим: любая почта считается зарегистрированной.
SITE_API_URL = os.environ.get("SITE_API_URL", "")
SITE_API_TOKEN = os.environ.get("SITE_API_TOKEN", "")
DB_PATH = Path(os.environ.get("DB_PATH", BASE / "data" / "bot.db"))
TZ = ZoneInfo(os.environ.get("TZ_NAME", "Europe/Moscow"))

# Тихие часы: необязательные сообщения в это время копятся и уходят утром.
# QUIET_HOURS=22-9 по умолчанию; QUIET_HOURS=off — выключить (удобно для тестов).
_quiet = os.environ.get("QUIET_HOURS", "22-9").strip().lower()
QUIET_FROM, QUIET_TO = (0, 0) if _quiet == "off" else (int(_quiet.split("-")[0]), int(_quiet.split("-")[1]))
# Тестовый режим: кнопка «Сбросить диалог (тест)» и /reset. На рабочем сервере не включать.
TEST_MODE = os.environ.get("TEST_MODE", "off").strip().lower() in ("on", "1", "true", "yes")
# На сколько дней вперёд координатор видит события (горизонт фонда ~1,5 месяца).
HORIZON_DAYS = 45
