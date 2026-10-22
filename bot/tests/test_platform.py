"""Подключение Telegram из профиля на сайте, без Telegram: python -m tests.test_platform (из папки bot/).

Поднимает локальный поддельный сервер платформы (те же адреса и заголовки, что у apps/api) и гоняет бота
через диспетчер aiogram, как tests.test_flows.
"""
import asyncio
import os
import tempfile
from datetime import datetime

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "platform.db")
os.environ["BOT_TOKEN"] = "1:test"
os.environ["QUIET_HOURS"] = "off"
os.environ["OPORA_BOT_API_SECRET"] = "bot_secret_" + "1" * 32
os.environ["OPORA_WEBHOOK_SECRET"] = "hook_secret_" + "2" * 32

from aiohttp import web  # noqa: E402
from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.methods import AnswerCallbackQuery  # noqa: E402
from aiogram.types import Chat, Message, Update, User  # noqa: E402

import opora_bot.config as config  # noqa: E402
from opora_bot import common, db, menu, platform, screen, seed, ui, volunteer  # noqa: E402
from opora_bot.main import fallback  # noqa: E402

BIND = "bind_" + "A" * 43
SECRET, HOOK = os.environ["OPORA_BOT_API_SECRET"], os.environ["OPORA_WEBHOOK_SECRET"]


class FakeSession(BaseSession):
    """Telegram без сети — как в tests.test_flows."""

    def __init__(self):
        super().__init__()
        self.calls = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, AnswerCallbackQuery) or type(method).__name__.startswith(("SetMy", "Delete")):
            return True
        if type(method).__name__ == "GetMe":
            return User(id=8824299081, is_bot=True, first_name="Дети Марии", username="detimarie_bot")
        return Message(message_id=len(self.calls), date=datetime.now(), chat=Chat(id=getattr(method, "chat_id", None) or 0, type="private"),
                       text=getattr(method, "text", None) or "")

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        pass


class FakePlatform:
    """Ведёт себя как apps/api: webhook привязки, сессии бота, один защищённый адрес /me/profile."""

    def __init__(self):
        self.bound, self.sessions, self.seen = {}, {}, []
        self.up = True

    async def webhook(self, request):
        assert request.headers["X-Telegram-Bot-Api-Secret-Token"] == HOOK
        m = (await request.json())["message"]
        self.seen.append(m)
        assert m["chat"]["id"] == m["from"]["id"] and m["chat"]["type"] == "private" and m["from"]["is_bot"] is False
        if not m["text"].endswith(BIND):
            return web.json_response({"state": "ignored"})
        if m["from"]["id"] in self.bound or "user-anna" in self.bound.values():
            return web.json_response({"state": "conflict"})
        self.bound[m["from"]["id"]] = "user-anna"
        return web.json_response({"state": "linked"})

    async def session(self, request):
        if not self.up:
            raise web.HTTPServiceUnavailable()
        if request.headers.get("Authorization") != f"Bearer {SECRET}":
            return web.json_response({"code": "telegram_bot_unauthorized"}, status=401)
        tg = (await request.json())["telegram_user_id"]
        if tg not in self.bound:
            return web.json_response({"code": "telegram_not_linked"}, status=404)
        token = f"session-{tg}-{len(self.sessions)}"
        self.sessions[token] = self.bound[tg]
        return web.json_response({"user_id": self.bound[tg], "display_name": "Анна Соколова",
                                  "session_token": token, "expires_at": "2026-10-22T12:00:00+00:00"})

    async def profile(self, request):
        user = self.sessions.get(request.cookies.get("opora_session", ""))
        if request.headers.get("Authorization") != f"Bearer {SECRET}" or not user:
            return web.json_response({"code": "session_expired"}, status=401)
        return web.json_response({"user_id": user})


session = FakeSession()
bot = Bot("1:test", session=session)
dp = Dispatcher(storage=MemoryStorage())
dp.callback_query.outer_middleware(screen.ScreenCallbacks())
session.middleware(screen.ScreenRequests())
dp.include_routers(common.router, menu.router, volunteer.router, fallback)
n = 0


async def say(uid, text):
    global n
    n += 1
    msg = Message(message_id=n, date=datetime.now(), chat=Chat(id=uid, type="private"),
                  from_user=User(id=uid, is_bot=False, first_name=f"U{uid}"), text=text)
    session.calls.clear()
    await dp.feed_update(bot, Update(update_id=n, message=msg))
    return [getattr(c, "text", "") or "" for c in session.calls], list(session.calls)


def buttons(call):
    return [(b.text, b.url) for row in call.reply_markup.inline_keyboard for b in row]


async def main():
    fake = FakePlatform()
    app = web.Application()
    app.router.add_post("/deti-marii/api/v1/integrations/telegram/webhook", fake.webhook)
    app.router.add_post("/deti-marii/api/v1/integrations/telegram/bot/sessions", fake.session)
    app.router.add_get("/deti-marii/api/v1/me/profile", fake.profile)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    config.OPORA_URL, config.OPORA_BOT_API_SECRET, config.OPORA_WEBHOOK_SECRET = f"http://127.0.0.1:{port}/deti-marii", SECRET, HOOK
    config.PLATFORM = True
    db.init()
    seed.seed()
    ANNA, OLEG = 200, 300
    try:
        # новый человек: анкета и вход ведут на сайт, вход по почте не предлагается
        out, calls = await say(ANNA, "/start")
        assert any("Подключить Telegram" in t for t in out), out
        welcome = [c for c in calls if "Ещё не волонтёр фонда?" in (getattr(c, "text", "") or "")][0]
        assert buttons(welcome) == [(ui.BTN_ANKETA, f"{config.OPORA_URL}/application"), (ui.BTN_CONNECT, f"{config.OPORA_URL}/profile")]
        out, _ = await say(ANNA, ui.BTN_LOGIN)
        assert any("Вход по почте больше не нужен" in t for t in out), out

        # ссылка из профиля: платформа подтверждает, бот получает сессию и имя из профиля
        out, _ = await say(ANNA, f"/start {BIND}")
        assert any("Telegram подключён к вашему профилю" in t and "Анна Соколова" in t for t in out), out
        u = db.user(ANNA)
        assert u["site_id"] == "user-anna" and u["status"] == "candidate" and u["name"] == "Анна Соколова"
        assert fake.seen[-1]["text"] == f"/start {BIND}"

        # дальше бот ходит в API от имени Анны: cookie сессии + секрет бота
        status, body = await platform.call(ANNA, "GET", "/me/profile")
        assert status == 200 and body == {"user_id": "user-anna"}
        # сессию отозвали (например, отключили Telegram на сайте) — бот один раз берёт новую
        fake.sessions.clear()
        status, body = await platform.call(ANNA, "GET", "/me/profile")
        assert status == 200 and len(fake.sessions) == 1
        # Telegram не подключён — платформа отвечает 404, бот это различает
        assert await platform.call(OLEG, "GET", "/me/profile") is None

        # чужая или старая ссылка, тот же профиль на другом Telegram, сайт недоступен
        out, _ = await say(OLEG, "/start bind_" + "B" * 43)
        assert any("ссылка уже не работает" in t for t in out), out
        out, _ = await say(OLEG, f"/start {BIND}")
        assert any("уже подключён к другому профилю" in t for t in out), out
        await runner.cleanup()
        out, _ = await say(OLEG, f"/start {BIND}")
        assert any("Сайт фонда сейчас не отвечает" in t for t in out), out
        assert db.user(OLEG)["status"] == "new"
    finally:
        await runner.cleanup()
    print("PASS: анкета и подключение ведут на сайт, вход по почте выключен, ссылка из профиля привязывает Telegram, "
          "сессия бота от имени волонтёра и её обновление, не подключённый Telegram, устаревшая ссылка, "
          "Telegram другого профиля, сайт недоступен")


asyncio.run(main())
