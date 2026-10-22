"""Отправка сообщений: тихие часы, очередь до утра, отметка заблокировавших бота."""
from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardMarkup

from . import db
from .config import QUIET_FROM, QUIET_TO


def is_quiet(moment=None) -> bool:
    if QUIET_FROM == QUIET_TO:
        return False
    h = (moment or db.now()).hour
    return QUIET_FROM <= h < QUIET_TO if QUIET_FROM < QUIET_TO else (h >= QUIET_FROM or h < QUIET_TO)


def morning():
    n = db.now()
    day = n.date() if n.hour < QUIET_TO else n.date() + timedelta(days=1)
    return n.replace(year=day.year, month=day.month, day=day.day, hour=QUIET_TO, minute=0, second=0, microsecond=0)


async def send(bot: Bot, chat_id: int, text: str, markup=None, urgent: bool = False, photo: str | None = None,
               until=None) -> bool:
    """urgent=True — отправить сразу даже ночью (изменения на сегодня, отказ в последний момент).
    photo — file_id картинки из Telegram, text тогда идёт подписью (до 1024 символов).
    until — не раньше этого времени: личные тихие часы человека из настроек на сайте."""
    later = None if urgent else max(x for x in (morning() if is_quiet() else None, until, db.now()) if x is not None)
    if later is not None and later > db.now():
        db.run("INSERT INTO outbox (chat_id, text, markup, send_after, photo) VALUES (?,?,?,?,?)",
               chat_id, text, markup.model_dump_json(exclude_none=True) if markup else None,
               later.astimezone(db.now().tzinfo).isoformat(timespec="seconds"), photo)  # сравнивается строкой с db.stamp()
        return False
    try:
        if photo:
            await bot.send_photo(chat_id, photo, caption=text or None, reply_markup=markup)
        else:
            await bot.send_message(chat_id, text, reply_markup=markup, disable_web_page_preview=True)
        return True
    except TelegramForbiddenError:
        db.update_user(chat_id, blocked=1)
    except TelegramBadRequest:
        pass
    return False


async def to_coordinators(bot: Bot, text: str, markup=None, urgent: bool = True) -> None:
    """Координатору сообщения уходят сразу: это его рабочий инструмент."""
    for c in db.coordinators():
        await send(bot, c["id"], text, markup, urgent=urgent)


async def flush_outbox(bot: Bot) -> None:
    if is_quiet():
        return
    for row in db.all_("SELECT * FROM outbox WHERE send_after<=? ORDER BY id", db.stamp()):
        markup = InlineKeyboardMarkup.model_validate_json(row["markup"]) if row["markup"] else None
        await send(bot, row["chat_id"], row["text"], markup, urgent=True, photo=row["photo"])
        db.run("DELETE FROM outbox WHERE id=?", row["id"])
