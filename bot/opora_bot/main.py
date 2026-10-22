"""Запуск: python -m opora_bot (из папки bot/)."""
import asyncio
import logging
import os
import ssl

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonCommands, Message

from . import broadcasts, common, coordinator, db, menu, jobs, pcoordinator, pjobs, platform, pvolunteer, screen, seed, testmode, ui, volunteer
from .config import TEST_MODE, TOKEN

fallback = Router(name="fallback")

# Видно в пустом чате до «Старт» (до 512 символов) и в профиле бота (до 120). Факты — из презентации фонда 2025.
DESCRIPTION = ("Благотворительный фонд «Дети Марии» почти 30 лет поддерживает детей и взрослых с опытом жизни "
               "в социальных учреждениях. Помогаем через творчество: мастерские керамики, живописи, шитья "
               "и кулинарии работают семь дней в неделю, а летом — арт-резиденция на Волге.\n\n"
               "Это бот для волонтёров фонда: приглашения на занятия и мероприятия, напоминания, материалы "
               "и связь с координатором. Нажмите «Старт», чтобы начать.")
SHORT_DESCRIPTION = "Бот для волонтёров фонда «Дети Марии»: собеседования, занятия, приглашения и связь с координатором."


@fallback.message(F.text)
async def unknown(msg: Message):
    u = db.ensure_user(msg.chat.id, msg.from_user.username)
    await ui.send_menu(msg, u, "Не поняли сообщение. Выберите, что нужно:")


def make_session() -> AiohttpSession | None:
    """Если сеть проверяет TLS своим сертификатом (SSL_CERT_FILE) или нужен прокси (BOT_PROXY,
    для socks-прокси нужен пакет aiohttp-socks) — используем их. На обычном сервере переменных нет,
    и бот ходит в Telegram напрямую."""
    proxy, cafile = os.environ.get("BOT_PROXY"), os.environ.get("SSL_CERT_FILE")
    if not proxy and not cafile:
        return None
    session = AiohttpSession(proxy=proxy) if proxy else AiohttpSession()
    if cafile:
        session._connector_init["ssl"] = ssl.create_default_context(cafile=cafile)
    return session


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if not TOKEN:
        if os.environ.get("BOT_WAIT_FOR_TOKEN"):
            # На сервере сервис бота есть всегда; пока токен не вписан, он ждёт, а не перезапускается по кругу.
            logging.warning("BOT_TOKEN не задан — бот не запущен, ждём настройки")
            while True:
                await asyncio.sleep(3600)
        raise SystemExit("Нет BOT_TOKEN. Скопируйте .env.example в .env и вставьте токен от @BotFather.")
    db.init()
    if not platform.enabled():  # с платформой события и люди — на сайте, демо-данные бота не нужны
        seed.seed()
    bot = Bot(TOKEN, session=make_session(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.callback_query.outer_middleware(screen.ScreenCallbacks())
    bot.session.middleware(screen.ScreenRequests())
    # Разделы на данных сайта стоят раньше прежних: без платформы они выключены своим фильтром.
    dp.include_routers(common.router, menu.router, testmode.router, pcoordinator.router, pvolunteer.router,
                       coordinator.login_router, coordinator.router, broadcasts.router, volunteer.router, fallback)
    commands = [BotCommand(command="menu", description="Меню"), BotCommand(command="start", description="Начать сначала")]
    if TEST_MODE:
        commands.append(BotCommand(command="reset", description="Сбросить диалог (тест)"))
    await bot.set_my_commands(commands)
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())  # кнопка «Меню» у поля ввода
    await bot.set_my_description(description=DESCRIPTION)
    await bot.set_my_short_description(short_description=SHORT_DESCRIPTION)
    # Бот получает сообщения опросом; если у токена остался webhook (старый запуск), Telegram опрос не отдаст.
    await bot.delete_webhook(drop_pending_updates=False)
    asyncio.create_task(pjobs.loop(bot) if platform.enabled() else jobs.loop(bot))
    await dp.start_polling(bot)


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
