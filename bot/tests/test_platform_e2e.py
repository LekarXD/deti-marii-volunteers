"""Бот + настоящий API платформы на демо-данных стенда, без Telegram: python -m tests.test_platform_e2e (из папки bot/).

Нужны локальный PostgreSQL и зависимости API в том же окружении, что и бот (см. infra/README.md). Тест
пересоздаёт базу OPORA_E2E_DATABASE_URL (имя базы обязано быть opora_stage — так требует заполнение демо-данными;
после теста она снова пустая, с миграциями),
заполняет её вымышленными людьми и событиями (app.stage_demo), поднимает API на 127.0.0.1:8012 и гоняет бота
через диспетчер aiogram: подключение из профиля, разделы волонтёра и координатора, фоновые задачи.
Без OPORA_E2E_DATABASE_URL тест пропускается.
"""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

DB = os.environ.get("OPORA_E2E_DATABASE_URL", "")
if not DB:
    print("SKIP: задайте OPORA_E2E_DATABASE_URL=postgresql+psycopg://…/opora_stage")
    raise SystemExit(0)
if not DB.endswith("/opora_stage"):
    raise SystemExit("OPORA_E2E_DATABASE_URL должен указывать на отдельную базу opora_stage")

ROOT = Path(__file__).resolve().parents[2]
API = ROOT / "apps" / "api"
PORT = 8012
HOOK, BOT_SECRET = "hook_secret_" + "2" * 32, "bot_secret_" + "1" * 32
PRIVATE = Path(tempfile.mkdtemp())
PRIVATE.chmod(0o700)
API_ENV = dict(os.environ, OPORA_DATABASE_URL=DB, OPORA_ENVIRONMENT="staging", OPORA_COOKIE_SECURE="true",
               OPORA_DEV_INBOX="false", OPORA_SECRET_KEY="e2e-" + "k" * 40, OPORA_DEMO_EMAIL_CODES="false",
               OPORA_TRUSTED_ORIGINS=f'["http://127.0.0.1:{PORT}"]', OPORA_TELEGRAM_LINK_ENABLED="true",
               OPORA_TELEGRAM_BOT_USERNAME="detimarie_bot", OPORA_TELEGRAM_WEBHOOK_SECRET=HOOK,
               OPORA_TELEGRAM_BOT_API_SECRET=BOT_SECRET, OPORA_ASSET_ROOT=str(PRIVATE / "assets"), PYTHONPATH=str(API))
API_ENV.pop("OPORA_TELEGRAM_BOT_TOKEN", None)


def psql(sql: str) -> None:
    from sqlalchemy.engine import make_url
    url = make_url(DB)
    subprocess.run(["psql", "-h", url.host, "-p", str(url.port), "-U", url.username, "-d", "postgres", "-qc", sql],
                   env=dict(os.environ, PGPASSWORD=url.password or ""), check=True)


# --- платформа: чистая база, демо-данные, API --------------------------------------------------
psql("DROP DATABASE IF EXISTS opora_stage WITH (FORCE)")
psql("CREATE DATABASE opora_stage")
subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API, env=API_ENV, check=True, capture_output=True)
subprocess.run([sys.executable, "-m", "app.stage_demo", "--confirm", "ONLY_SYNTHETIC_OPORA_STAGE",
                "--credentials-path", str(PRIVATE / "demo.json"), "seed"], cwd=API,
               env=dict(API_ENV, OPORA_STAGE_FIXTURE_SEED_ALLOW="true"), check=True, capture_output=True)
CREDS = json.loads((PRIVATE / "demo.json").read_text())["identities"]

os.environ.update({k: v for k, v in API_ENV.items() if k.startswith("OPORA_")})
sys.path.insert(0, str(API))
import httpx  # noqa: E402
import pyotp  # noqa: E402
from sqlalchemy import text, update  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402
from starlette.responses import Response  # noqa: E402
from app.core.auth import issue_session  # noqa: E402
from app.core.clock import utcnow  # noqa: E402
from app.core.models import MfaFactor  # noqa: E402


async def web_sessions():
    """Как будто координатор и волонтёры уже вошли на сайт (координатор подтвердил код при первом входе)."""
    engine = create_async_engine(DB)
    f = async_sessionmaker(engine, expire_on_commit=False)
    out = {}
    async with f() as db:
        await db.execute(update(MfaFactor).where(MfaFactor.user_id == uuid.UUID(CREDS["coordinator"]["user_id"])).values(confirmed_at=utcnow()))
        for key in ("coordinator", "volunteer", "candidate"):
            r = Response()
            _, csrf = await issue_session(db, r, user_id=uuid.UUID(CREDS[key]["user_id"]))
            out[key] = (r.headers["set-cookie"].split(";")[0].split("=", 1)[1], csrf)
        await db.commit()
    await engine.dispose()
    return out


WEB = asyncio.run(web_sessions())
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT),
                           "--no-access-log"], cwd=API, env=API_ENV, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
for _ in range(80):
    try:
        if httpx.get(f"http://127.0.0.1:{PORT}/ready").status_code < 500:
            break
    except httpx.HTTPError:
        time.sleep(0.25)


def web(key: str) -> httpx.Client:
    token, csrf = WEB[key]
    return httpx.Client(base_url=f"http://127.0.0.1:{PORT}/api/v1", cookies={"opora_session": token},
                        headers={"Origin": f"http://127.0.0.1:{PORT}", "X-CSRF-Token": csrf})


def link_command(key: str) -> str:
    """«Подключить Telegram» в профиле на сайте → текст /start из ссылки."""
    res = web(key).post("/me/notification-channels/telegram/link-tokens", json={}, headers={"Idempotency-Key": str(uuid.uuid4())})
    assert res.status_code == 200, res.text
    return "/start " + res.json()["start_url"].split("start=")[1]


# --- бот ----------------------------------------------------------------------------------------
os.environ.update(DB_PATH=str(PRIVATE / "bot.db"), BOT_TOKEN="1:test", QUIET_HOURS="off", TEST_MODE="off",
                  OPORA_URL=f"http://127.0.0.1:{PORT}", OPORA_PUBLIC_URL="https://opora.example/deti-marii",
                  OPORA_BOT_API_SECRET=BOT_SECRET, OPORA_WEBHOOK_SECRET=HOOK)
from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.methods import AnswerCallbackQuery  # noqa: E402
from aiogram.types import CallbackQuery, Chat, Message, Update, User  # noqa: E402

from opora_bot import (broadcasts, common, coordinator, db, menu, pcoordinator, pjobs, platform,  # noqa: E402
                       pvolunteer, screen, testmode, ui, volunteer)
from opora_bot.main import fallback  # noqa: E402

assert platform.enabled()


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        name = type(method).__name__
        if isinstance(method, AnswerCallbackQuery) or name.startswith(("SetMy", "Delete", "EditMessageReplyMarkup")):
            return True
        if name == "GetMe":
            return User(id=8824299081, is_bot=True, first_name="Дети Марии", username="detimarie_bot")
        return Message(message_id=len(self.calls), date=datetime.now(), chat=Chat(id=getattr(method, "chat_id", None) or 0, type="private"),
                       text=getattr(method, "text", None) or getattr(method, "caption", None) or "")

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        pass


session = FakeSession()
bot = Bot("1:test", session=session)
dp = Dispatcher(storage=MemoryStorage())
dp.callback_query.outer_middleware(screen.ScreenCallbacks())
session.middleware(screen.ScreenRequests())
dp.include_routers(common.router, menu.router, testmode.router, pcoordinator.router, pvolunteer.router,
                   coordinator.login_router, coordinator.router, broadcasts.router, volunteer.router, fallback)
n = 0


async def say(uid, text):
    global n
    n += 1
    msg = Message(message_id=n, date=datetime.now(), chat=Chat(id=uid, type="private"),
                  from_user=User(id=uid, is_bot=False, first_name=f"U{uid}"), text=text)
    session.calls.clear()
    await dp.feed_update(bot, Update(update_id=n, message=msg))
    return list(session.calls)


async def press(uid, data, text="..."):
    global n
    n += 1
    msg = Message(message_id=n, date=datetime.now(), chat=Chat(id=uid, type="private"), text=text,
                  from_user=User(id=8824299081, is_bot=True, first_name="bot"))
    cb = CallbackQuery(id=str(n), from_user=User(id=uid, is_bot=False, first_name=f"U{uid}"), chat_instance="x",
                       data=data if isinstance(data, str) else data.pack(), message=msg)
    session.calls.clear()
    await dp.feed_update(bot, Update(update_id=n, callback_query=cb))
    return list(session.calls)


def texts(calls):
    return [getattr(c, "text", None) or getattr(c, "caption", None) or "" for c in calls]


def joined(calls):
    return "\n".join(texts(calls))


def buttons(calls):
    out = []
    for c in calls:
        markup = getattr(c, "reply_markup", None)
        for row in getattr(markup, "inline_keyboard", None) or []:
            out += [(b.text, b.callback_data, b.url) for b in row]
    return out


def button(calls, start):
    for label, data, url in buttons(calls):
        if label.startswith(start):
            return data or url
    raise AssertionError(f"нет кнопки «{start}» среди {[b[0] for b in buttons(calls)]}")


def docs(calls):
    return [c for c in calls if type(c).__name__ == "SendDocument"]


async def main():
    db.init()
    ANNA, COORD, NEW = 200, 100, 300

    # подключение из профиля
    out = joined(await say(ANNA, link_command("volunteer")))
    assert "Telegram подключён" in out and "Анна Демонстрационная" in out, out
    menu_calls = await say(ANNA, "/menu")
    assert ui.BTN_MY in [b[0] for b in buttons(menu_calls)]

    # Мои занятия: данные с сайта, часы, приглашение → «Приду»
    calls = await press(ANNA, ui.MenuCB(item="my"))
    out = joined(calls)
    assert "Мои занятия" in out and "[ДЕМО]" in out, out
    site = web("volunteer").get("/me/schedule", params={"from": db.now().date().isoformat(), "to": (db.now().date() + timedelta(days=45)).isoformat(), "state": "active"}).json()["items"]
    invited = [a for a in site if a["status"] == "invited" and "confirm" in a["allowed_actions"]]
    covered = []
    if invited:
        covered.append("приглашение → Приду")
        aid = invited[0]["id"]
        out = joined(await press(ANNA, pvolunteer.PA(action="open", aid=aid)))
        assert invited[0]["title"] in out, out
        out = joined(await press(ANNA, pvolunteer.PA(action="yes", aid=aid)))
        assert "ждём вас" in out, out
        assert web("volunteer").get(f"/assignments/{aid}").json()["status"] == "confirmed"
    confirmed = [a for a in site if a["status"] == "confirmed"] or invited
    assert confirmed, "в демо-данных у Анны должно быть подтверждённое занятие"
    out = joined(await press(ANNA, ui.MenuCB(item="materials")))
    assert "Ближайшее занятие" in out, out
    assert docs(await press(ANNA, pvolunteer.PA(action="ics"))), "файл календаря"

    # Собеседование (у кандидата есть запись в демо-данных) и отмена
    out = joined(await say(NEW, link_command("candidate")))
    assert "Telegram подключён" in out, out
    calls = await press(NEW, ui.MenuCB(item="meeting"))
    out = joined(calls)
    booking = [m for m in web("candidate").get("/me/interviews").json() if m["status"] == "booked"]
    if booking:
        covered.append("отмена собеседования")
        assert "Собеседование с координатором" in out, out
        out = joined(await press(NEW, pvolunteer.PM(action="cancel_yes", bid=booking[0]["id"])))
        assert "Запись отменена" in out, out
        assert web("candidate").get("/me/interviews").json()[0]["status"] == "cancelled"
    else:
        assert "Записи на собеседование сейчас нет" in out, out

    # Написать координатору → разговор на сайте
    await press(ANNA, ui.MenuCB(item="ask"))
    out = joined(await say(ANNA, "Здравствуйте! Можно прийти на полчаса позже?"))
    assert "Отправили координатору" in out, out
    convs = web("coordinator").get("/conversations").json()["items"]
    assert any((c["last_message"] or {}).get("text", "").startswith("Здравствуйте! Можно прийти") for c in convs), convs

    # Настройки: новости вкл/выкл — меняется на сайте
    before = web("volunteer").get("/me/notification-preferences").json()["topics"].get("news", False)
    await press(ANNA, ui.MenuCB(item="settings"))
    await press(ANNA, pvolunteer.PS(key="news"))
    assert web("volunteer").get("/me/notification-preferences").json()["topics"].get("news", False) is (not before)

    # координатор: привязка, вход с кодом, лента, события, выгрузки
    out = joined(await say(COORD, link_command("coordinator")))
    assert "Telegram подключён" in out, out
    out = joined(await say(COORD, "/coordinator"))
    assert "Введите 6 цифр" in out, out
    out = joined(await say(COORD, "000000" if pyotp.TOTP(CREDS["coordinator"]["totp_secret"]).now() != "000000" else "111111"))
    assert "Код не подошёл" in out, out
    out = joined(await say(COORD, pyotp.TOTP(CREDS["coordinator"]["totp_secret"]).now()))
    assert "Вы вошли как координатор" in out, out
    assert db.user(COORD)["is_coordinator"] and platform.is_staff(COORD)

    calls = await press(COORD, ui.MenuCB(item="feed"))
    out = joined(calls)
    assert "Нужно решить" in out, out

    # ответ волонтёру в разговоре из бота координатора и пересылка Анне фоновой задачей
    await pjobs.tick(bot, 1)  # первый проход запоминает, что уже было
    conv = next(c for c in web("coordinator").get("/conversations").json()["items"]
                if (c["last_message"] or {}).get("text", "").startswith("Здравствуйте! Можно прийти"))
    await press(COORD, pvolunteer.PR(cid=conv["id"]))
    out = joined(await say(COORD, "Конечно, ждём!"))
    assert "Отправлено" in out, out
    session.calls.clear()
    await pjobs.tick(bot, 1)
    forwarded = [c for c in session.calls if getattr(c, "chat_id", None) == ANNA and "Конечно, ждём!" in (getattr(c, "text", "") or "")]
    assert forwarded, texts(session.calls)

    calls = await press(COORD, ui.MenuCB(item="events"))
    assert "События на 45 дней" in joined(calls), joined(calls)
    month_key = next(d for _, d, _ in buttons(calls) if d and d.startswith("pe:month"))
    calls = await press(COORD, month_key)
    event_key = next(d for _, d, _ in buttons(calls) if d and d.startswith("pe:open"))
    calls = await press(COORD, event_key)
    out = joined(calls)
    assert "👥" in out, out
    call_key = next((d for _, d, _ in buttons(calls) if d and d.startswith("pe:call")), None)
    if call_key:
        calls = await press(COORD, call_key)
        pick = next((d for _, d, _ in buttons(calls) if d and d.startswith("pe:pick")), None)
        if pick:
            covered.append("позвать людей")
            await press(COORD, pick)
            out = joined(await press(COORD, pcoordinator.PE(action="send")))
            assert "Приглашения отправлены" in out, out

    # новое событие
    await press(COORD, ui.MenuCB(item="new_event"))
    await say(COORD, "Арт-суббота E2E")
    await say(COORD, "25.12")
    await say(COORD, "11:00-14:00")
    calls = await say(COORD, "онлайн")
    role = next(d for _, d, _ in buttons(calls) if d and d.startswith("pn:role:") and d != "pn:role:")
    await press(COORD, role)
    await say(COORD, "2")
    out = joined(await press(COORD, pcoordinator.PN(step="once")))
    assert "Событие создано" in out, out
    titles = [o["title"] for o in await pcoordinator.occurrences(COORD, 120)]
    assert "Арт-суббота E2E" in titles

    # полный путь приглашения: координатор зовёт Анну в новое событие → бот присылает ей приглашение → «Приду»
    created = next(o for o in await pcoordinator.occurrences(COORD, 120) if o["title"] == "Арт-суббота E2E")
    calls = await press(COORD, pcoordinator.PE(action="open", id=created["id"]))
    assert "0 из 2" in joined(calls), joined(calls)
    calls = await press(COORD, button(calls, "Позвать"))
    await press(COORD, button(calls, "[ДЕМО] Анна"))
    out = joined(await press(COORD, pcoordinator.PE(action="send")))
    assert "Приглашения отправлены" in out and "Анна" in out, out
    covered.append("позвать людей")
    session.calls.clear()
    await pjobs.tick(bot, 0)  # приглашение без согласования координатора волонтёру ещё не уходит
    assert not [c for c in session.calls if getattr(c, "chat_id", None) == ANNA and "Арт-суббота E2E" in (getattr(c, "text", "") or "")]
    calls = await press(COORD, pcoordinator.PE(action="open", id=created["id"]))
    out = joined(await press(COORD, button(calls, "Подтвердить: [ДЕМО] Анна")))
    assert "подтверждён" in out, out
    session.calls.clear()
    await pjobs.tick(bot, 0)  # раз в 5 минут — расписание и приглашения
    invite = [c for c in session.calls if getattr(c, "chat_id", None) == ANNA and "Арт-суббота E2E" in (getattr(c, "text", "") or "")]
    assert invite and "Приглашаем" in invite[0].text, texts(session.calls)
    out = joined(await press(ANNA, button(invite, "Приду")))
    assert "ждём вас" in out, out
    team = (await platform.get(COORD, "/coord/assignments", occurrence_id=created["id"]))["items"]
    assert [a["status"] for a in team if a["display_name"].startswith("[ДЕМО] Анна")] == ["confirmed"], team
    covered.append("приглашение в боте → Приду")
    session.calls.clear()
    await pjobs.tick(bot, 0)
    assert not [c for c in session.calls if "Приглашаем" in (getattr(c, "text", "") or "")], "приглашение не повторяется"

    assert docs(await press(COORD, pcoordinator.PX(kind="volunteers")))
    assert docs(await press(COORD, pcoordinator.PX(kind="teams")))

    # Telegram отключили на сайте — бот это замечает
    st = web("volunteer").get("/me/notification-channels/telegram").json()
    web("volunteer").post("/me/notification-channels/telegram/disconnect", json={"expected_version": st["version"]},
                          headers={"Idempotency-Key": str(uuid.uuid4())})
    out = joined(await press(ANNA, ui.MenuCB(item="my")))
    assert "больше не подключён" in out, out
    assert db.user(ANNA)["status"] == "new"
    print("E2E PASS: подключение из профиля, мои занятия и «Приду», материалы, календарь, собеседование и отмена, "
          "переписка с координатором в обе стороны, настройки, вход координатора с кодом, лента, события и приглашения, "
          "новое событие, выгрузки, отключение Telegram на сайте. Ветки с данными: " + ", ".join(covered))


try:
    asyncio.run(main())
finally:
    server.terminate()
    log = server.communicate(timeout=10)[0].decode(errors="replace")
    if "Traceback" in log:
        print(log[-4000:])
    # вернуть пустую базу с миграциями — такой её ждут тесты API (OPORA_STAGE_DEMO_TEST_DATABASE_URL)
    psql("DROP DATABASE IF EXISTS opora_stage WITH (FORCE)")
    psql("CREATE DATABASE opora_stage")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API, env=API_ENV, check=True, capture_output=True)
