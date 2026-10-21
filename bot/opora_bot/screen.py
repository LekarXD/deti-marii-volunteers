"""Экраны: чтобы сообщения бота не копились в чате.

Экран — это меню или раздел, открытый кнопкой (лента уведомлений, карточка, список событий, настройки…).
Когда кнопка на экране открывает что-то новое, прежний экран удаляется, под последним новым сообщением
появляется кнопка «Меню». По «Меню» экран убирается и показывается меню.

Не трогаем: приглашения, напоминания, ответы координатора и файлы (Excel, .ics) — они остаются в чате.

Подключение (main.py и тесты):
    dp.callback_query.outer_middleware(ScreenCallbacks())
    bot.session.middleware(ScreenRequests())
"""
from aiogram import BaseMiddleware
from aiogram.client.session.middlewares.base import BaseRequestMiddleware
from aiogram.exceptions import TelegramAPIError
from aiogram.methods import SendMessage, SendPhoto
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from . import ui


class ScreenRequests(BaseRequestMiddleware):
    """Запоминает сообщения, которые бот отправил в этот чат, пока обрабатывается нажатие на экране."""

    async def __call__(self, make_request, bot, method):
        res = await make_request(bot, method)
        st = ui.TRACK.get()
        if (st is not None and isinstance(method, (SendMessage, SendPhoto)) and isinstance(res, Message)
                and method.chat_id == st["chat"]):
            ui.remember(st["chat"], res.message_id)
            st["last"] = (res.message_id, method.reply_markup)
        return res


class ScreenCallbacks(BaseMiddleware):
    async def __call__(self, handler, event: CallbackQuery, data):
        msg = event.message
        if not isinstance(msg, Message):
            return await handler(event, data)
        chat = msg.chat.id
        on_screen = msg.message_id in ui.SCREENS.get(chat, []) or (event.data or "").startswith("menu:")
        if not on_screen:
            return await handler(event, data)
        st = {"chat": chat, "last": None, "menu": False,
              "before": {*ui.SCREENS.get(chat, []), msg.message_id}}
        token = ui.TRACK.set(st)
        try:
            return await handler(event, data)
        finally:
            ui.TRACK.reset(token)
            if st["last"] and not st["menu"]:
                await replace(event.bot, st)


async def replace(bot, st) -> None:
    chat = st["chat"]
    for mid in st["before"]:
        try:
            await bot.delete_message(chat, mid)
        except TelegramAPIError:
            pass
    ui.SCREENS[chat] = [m for m in ui.SCREENS.get(chat, []) if m not in st["before"]]
    mid, markup = st["last"]
    if markup is not None and not isinstance(markup, InlineKeyboardMarkup):
        return
    rows = list(markup.inline_keyboard) if markup else []
    if any(b.callback_data == ui.MenuCB(item="home").pack() for row in rows for b in row):
        return
    try:
        await bot.edit_message_reply_markup(chat_id=chat, message_id=mid,
                                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[*rows, [ui.home_button()]]))
    except TelegramAPIError:
        pass
