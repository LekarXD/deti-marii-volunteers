"""Сценарии целиком через диспетчер aiogram, без сети: python -m tests.test_flows (из папки bot/)."""
import asyncio
import os
import re
import tempfile
from datetime import datetime

os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(), "flows.db")
os.environ["COORDINATOR_CODE"] = "test-code"
os.environ["BOT_TOKEN"] = "1:test"
os.environ["QUIET_HOURS"] = "22-9"
os.environ["UNISENDER_API_KEY"] = ""
os.environ["TEST_MODE"] = "on"

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.session.base import BaseSession  # noqa: E402
from aiogram.fsm.storage.memory import MemoryStorage  # noqa: E402
from aiogram.methods import AnswerCallbackQuery  # noqa: E402
from aiogram.types import CallbackQuery, Chat, Message, PhotoSize, Update, User  # noqa: E402

import opora_bot.config as config  # noqa: E402
config.COORDINATOR_CODE = "test-code"
from opora_bot import screen  # noqa: E402
from opora_bot import auth, common, coordinator, menu, db, jobs, seed, testmode, ui, unisender, volunteer  # noqa: E402
from opora_bot import broadcasts as coordinator_bc  # noqa: E402
from pathlib import Path  # noqa: E402
unisender.DRY_DIR = Path(tempfile.mkdtemp())
from opora_bot.main import fallback  # noqa: E402

coordinator.COORDINATOR_CODE = "test-code"


class FakeSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.calls = []

    async def make_request(self, bot, method, timeout=None):
        self.calls.append(method)
        if isinstance(method, AnswerCallbackQuery) or type(method).__name__.startswith(("SetMy", "Delete")):
            return True
        if type(method).__name__ == "GetMe":
            return User(id=8824299081, is_bot=True, first_name="Дети Марии", username="detimarie_bot")
        chat_id = getattr(method, "chat_id", None) or 0
        return Message(message_id=len(self.calls), date=datetime.now(), chat=Chat(id=chat_id, type="private"),
                       text=getattr(method, "text", None) or "")

    async def stream_content(self, *a, **k):
        yield b""

    async def close(self):
        pass


session = FakeSession()
bot = Bot("1:test", session=session)
dp = Dispatcher(storage=MemoryStorage())
dp.callback_query.outer_middleware(screen.ScreenCallbacks())
session.middleware(screen.ScreenRequests())
dp.include_routers(common.router, menu.router, testmode.router, coordinator.login_router, coordinator.router, coordinator_bc.router, volunteer.router, fallback)
n = 0


def user(uid, name):
    return User(id=uid, is_bot=False, first_name=name, username=name.lower())


async def say(uid, text=None, contact=None, photo=None, caption=None):
    global n
    n += 1
    sizes = [PhotoSize(file_id=photo, file_unique_id=photo + "u", width=800, height=600)] if photo else None
    msg = Message(message_id=n, date=datetime.now(), chat=Chat(id=uid, type="private"), from_user=user(uid, f"U{uid}"),
                  text=text, contact=contact, photo=sizes, caption=caption)
    session.calls.clear()
    await dp.feed_update(bot, Update(update_id=n, message=msg))
    return list(session.calls)


async def press(uid, data, text="...", mid=None):
    global n
    n += 1
    msg = Message(message_id=mid or n, date=datetime.now(), chat=Chat(id=uid, type="private"), text=text,
                  from_user=User(id=8824299081, is_bot=True, first_name="bot"))
    cb = CallbackQuery(id=str(n), from_user=user(uid, f"U{uid}"), chat_instance="x", data=data.pack(), message=msg)
    session.calls.clear()
    await dp.feed_update(bot, Update(update_id=n, callback_query=cb))
    return list(session.calls)


def texts(calls, chat=None):
    return [getattr(c, "text", "") or getattr(c, "caption", "") or "" for c in calls
            if chat is None or getattr(c, "chat_id", None) == chat]


def docs(calls, chat):
    return [c for c in calls if type(c).__name__ == "SendDocument" and c.chat_id == chat]


async def main():
    db.init()
    seed.seed()
    db.now = lambda: datetime(2026, 10, 21, 12, 0, tzinfo=config.TZ)  # день: вне тихих часов
    COORD, ANNA = 100, 200

    # координатор входит по коду; неверный код не пускает
    assert "не подошёл" in " ".join(texts(await say(COORD, "/coordinator wrong")))
    assert "Вы вошли как координатор" in " ".join(texts(await say(COORD, "/coordinator test-code")))

    # два режима: у координатора свои кнопки, переключение в режим волонтёра и обратно
    labels = lambda u: [b.text for row in ui.menu(u).inline_keyboard for b in row]  # noqa: E731
    assert ui.BTN_FEED in labels(db.user(COORD)) and ui.BTN_MY not in labels(db.user(COORD))
    await say(COORD, ui.BTN_TO_VOLUNTEER)
    assert ui.BTN_TO_COORD in labels(db.user(COORD)) and ui.BTN_FEED not in labels(db.user(COORD))
    await say(COORD, ui.BTN_TO_COORD)
    assert ui.BTN_FEED in labels(db.user(COORD))

    # новый человек: бот ведёт на анкету, регистрации в чате нет
    calls = await say(ANNA, "/start")
    out = texts(calls)
    assert any("Впервые у нас?" in t for t in out), out
    welcome = [c for c in calls if "Впервые у нас?" in (getattr(c, "text", "") or "")][0]
    assert [b.text for row in welcome.reply_markup.inline_keyboard for b in row][:2] == [ui.BTN_ANKETA, ui.BTN_LOGIN]
    assert not any(type(c.reply_markup).__name__ == "ReplyKeyboardMarkup" for c in calls if getattr(c, "reply_markup", None)), \
        "клавиатуры под строкой ввода нет"
    assert db.user(ANNA)["status"] == "new"

    # вход по почте: проверка адреса, код из письма (тестовый режим Unisender Go), неверный и верный код
    await say(ANNA, ui.BTN_LOGIN)
    assert any("ошибка" in t for t in texts(await say(ANNA, "anna-mail.ru")))
    out = texts(await say(ANNA, "Anna@Mail.ru"))
    m = [re.search(r"Ваш код: <b>(\d{6})</b>", t) for t in out]
    code = next(x.group(1) for x in m if x)
    assert any("Отправили код на a•••a@mail.ru" in t for t in out), out
    sent = list(unisender.DRY_DIR.glob("*.html"))
    assert sent and code in sent[0].read_text() and "{{" not in sent[0].read_text(), "письмо отрендерено с кодом"
    assert any("Слишком" in t or "через минуту" in t for t in texts(await press(ANNA, ui.StepCB(name="resend")))), "повтор не чаще раза в минуту"
    wrong = "000000" if code != "000000" else "111111"
    assert any("Осталось попыток: 4" in t for t in texts(await say(ANNA, wrong)))
    calls = await say(ANNA, code[:3] + " " + code[3:])
    u = db.user(ANNA)
    assert u["email"] == "anna@mail.ru" and u["status"] == "candidate", dict(u)
    assert not texts(calls, COORD), "вход — в ленту, не сообщением координатору"
    assert db.one("SELECT 1 FROM activity WHERE kind='login' AND user_id=? AND text LIKE '%anna@mail.ru%'", ANNA)
    # человек уже записан на собеседование на сайте: бот подтверждает дату и время, слоты не предлагает
    hello = [t for t in texts(calls, ANNA) if "собеседование с координатором пройдёт" in t]
    assert hello and "за 15 минут" in hello[0] and "Выберите время" not in " ".join(texts(calls, ANNA)), texts(calls, ANNA)
    m = db.one("SELECT * FROM meetings WHERE user_id=?", ANNA)
    assert m["status"] == "booked" and datetime.fromisoformat(m["starts_at"]).strftime("%H:%M") == "18:30"
    assert not texts(calls, COORD) and db.one("SELECT 1 FROM activity WHERE kind='meeting' AND user_id=?", ANNA)
    # меню сразу не выводится: под сообщением о входе — плашка «Меню», по ней сообщение убирается и открывается меню
    to_anna = [c for c in calls if getattr(c, "chat_id", None) == ANNA and type(c).__name__ == "SendMessage"]
    assert len(to_anna) == 1, texts(calls, ANNA)
    assert ui.BTN_HOME in [b.text for row in to_anna[0].reply_markup.inline_keyboard for b in row]
    calls = await press(ANNA, ui.MenuCB(item="home"))
    assert any(type(c).__name__ == "DeleteMessage" for c in calls)
    shown = [c for c in calls if type(c).__name__ == "SendMessage"]
    assert len(shown) == 1 and any(b.text == ui.BTN_MEETING for row in shown[0].reply_markup.inline_keyboard for b in row)
    # раздел открывается на месте меню, под ним — «Меню»; по ней раздел убирается, меню возвращается
    menu_id = ui.SCREENS[ANNA][-1]
    calls = await press(ANNA, ui.MenuCB(item="meeting"))
    gone = {c.message_id for c in calls if type(c).__name__ == "DeleteMessage"}
    assert menu_id in gone, "меню убрано"
    edits = [c for c in calls if type(c).__name__ == "EditMessageReplyMarkup"]
    assert edits and edits[-1].reply_markup.inline_keyboard[-1][0].text == ui.BTN_HOME
    section_id = edits[-1].message_id
    calls = await press(ANNA, ui.MenuCB(item="home"))
    assert section_id in {c.message_id for c in calls if type(c).__name__ == "DeleteMessage"}, "раздел убран"
    assert [c for c in calls if type(c).__name__ == "SendMessage"], "меню показано снова"
    assert auth.check(ANNA, code)[0] == "none", "код одноразовый"
    db.update_user(ANNA, roles="assistant", days="5")  # из анкеты на сайте, когда появится API

    # запрос к Unisender Go собирается по формату email/send.json
    body = unisender.payload("anna@mail.ru", {"code": "123456"}, "login-1")["message"]
    assert body["recipients"] == [{"email": "anna@mail.ru", "substitutions": {"code": "123456"}}]
    assert "{{code}}" in body["body"]["html"] and body["track_links"] == 0 and body["subject"]

    # экран «Собеседование» показывает запись, перенос — через координатора
    assert any("Собеседование с координатором" in t for t in texts(await say(ANNA, ui.BTN_MEETING), ANNA))

    # не координатор не видит кнопки координатора
    assert not any("События на" in t for t in texts(await say(ANNA, ui.BTN_EVENTS), ANNA))

    # допуск только после встречи: до встречи кнопка не срабатывает
    calls = await press(COORD, ui.AdmitCB(uid=ANNA, action="yes"), text="Вошла в бот")
    alerts = [c for c in calls if isinstance(c, AnswerCallbackQuery) and c.show_alert]
    assert alerts and "после собеседования" in alerts[0].text and db.user(ANNA)["status"] == "candidate"
    card_text, card_kb = coordinator.card(ANNA)
    assert "собеседование" in card_text and "Из анкеты" in card_text and not any("Допустить" in b.text for row in card_kb.inline_keyboard for b in row)
    # встреча прошла → через час в ленте «Как прошла встреча?» с кнопками итога
    db.run("UPDATE meetings SET starts_at=? WHERE user_id=?", datetime(2026, 10, 21, 10, 0, tzinfo=config.TZ).isoformat(), ANNA)
    session.calls.clear()
    await jobs.meeting_followup(bot, db.now())
    assert not session.calls, "итог встречи — в ленту, без отдельного сообщения"
    calls = await press(COORD, ui.MenuCB(item="feed"))
    outcome = [c for c in calls if "Как прошло собеседование" in (getattr(c, "text", "") or "")]
    assert outcome and any(b.text == "Допустить к занятиям" for row in outcome[0].reply_markup.inline_keyboard for b in row)
    calls = await press(COORD, ui.AdmitCB(uid=ANNA, action="yes"), text="Как прошло собеседование?")
    assert db.user(ANNA)["status"] == "active" and any("допустил" in t for t in texts(calls, ANNA))
    assert db.one("SELECT status FROM meetings WHERE user_id=?", ANNA)["status"] == "done"
    assert not [a for a in db.open_actions() if a["action"] == "outcome"], "задача в ленте закрыта"

    # приглашение → согласие → подтверждение
    # события: сначала выбор месяца, потом события месяца, из события — назад к месяцу
    months = await say(COORD, ui.BTN_EVENTS)
    mkb = [b for c in months if getattr(c, "reply_markup", None) for row in c.reply_markup.inline_keyboard for b in row]
    assert mkb and mkb[0].text.startswith("Октябрь") and any(b.text.startswith("Ноябрь") for b in mkb), [b.text for b in mkb]
    calls = await press(COORD, ui.EvCB(action="month", d="202610"))
    lst = [b.text for c in calls if getattr(c, "reply_markup", None) for row in c.reply_markup.inline_keyboard for b in row]
    assert any("24.10" in x and "Арт-суббота" in x for x in lst) and not any(x.startswith("05.11") for x in lst)
    assert lst[-1] == "← Месяцы"
    calls = await press(COORD, ui.EvCB(action="open", eid="art", d="20261024"))
    assert any(b.text == "← Октябрь" for c in calls if getattr(c, "reply_markup", None) for row in c.reply_markup.inline_keyboard for b in row)
    await press(COORD, ui.EvCB(action="call", eid="art", d="20261024"))
    await press(COORD, ui.PickCB(uid=ANNA))
    calls = await press(COORD, ui.StepCB(name="send_invites"))
    inv_msgs = [c for c in calls if getattr(c, "chat_id", None) == ANNA]
    assert inv_msgs and "Арт-суббота" in inv_msgs[0].text and db.invite("art", "2026-10-24", ANNA)["status"] == "invited"
    calls = await press(ANNA, ui.InvCB(action="yes", eid="art", d="20261024"))
    assert db.invite("art", "2026-10-24", ANNA)["status"] == "accepted"
    assert not texts(calls, COORD)
    feed_calls = await say(COORD, ui.BTN_FEED)
    assert any("готов(а) прийти" in (getattr(c, "text", "") or "") and c.reply_markup for c in feed_calls)
    # карточка из ленты открывается на месте ленты: лента удаляется, под карточкой — «Меню»
    calls = await press(COORD, ui.MenuCB(item="feed"))
    feed_ids = set(ui.SCREENS[COORD])
    calls = await press(COORD, ui.CardCB(uid=ANNA), mid=max(feed_ids))  # кнопка под последним сообщением ленты
    gone = {c.message_id for c in calls if type(c).__name__ == "DeleteMessage"}
    assert feed_ids <= gone, (feed_ids, gone)
    edits = [c for c in calls if type(c).__name__ == "EditMessageReplyMarkup"]
    assert edits and edits[-1].reply_markup.inline_keyboard[-1][0].text == ui.BTN_HOME
    assert any(b.text.startswith("Карточка: ") for c in feed_calls if c.reply_markup for row in c.reply_markup.inline_keyboard for b in row)
    calls = await press(COORD, ui.InvCB(action="conf", eid="art", d="20261024", uid=ANNA), text="Анна готова прийти")
    assert not [a for a in db.open_actions() if a["action"] == "confirm"]
    assert db.invite("art", "2026-10-24", ANNA)["status"] == "confirmed"
    assert any("Ждём вас" in t for t in texts(calls, ANNA))

    # мои занятия, .ics, материалы с группой — через кнопку меню под сообщением
    calls = await press(ANNA, ui.MenuCB(item="my"))
    assert any("Арт-суббота" in t for t in texts(calls, ANNA)) and docs(calls, ANNA)
    assert any("Саша" in t for t in texts(await say(ANNA, ui.BTN_MATERIALS), ANNA))

    # вопрос → ответ
    await say(ANNA, ui.BTN_ASK)
    calls = await say(ANNA, "Во сколько сбор в субботу?")
    assert any("Во сколько сбор" in t for t in texts(calls, COORD))
    qid = db.one("SELECT id FROM questions")["id"]
    await press(COORD, ui.AnswerCB(qid=qid))
    calls = await say(COORD, "В 13:00 у метро")
    assert any("В 13:00 у метро" in t for t in texts(calls, ANNA))

    # отказ меньше чем за сутки помечается «Срочно» (подменяем время на 23.10 вечер)
    db.now = lambda: datetime(2026, 10, 23, 20, 0, tzinfo=config.TZ)
    calls = await press(ANNA, ui.InvCB(action="no", eid="art", d="20261024"))
    db.now = lambda: datetime(2026, 10, 21, 12, 0, tzinfo=config.TZ)
    assert any("<b>Срочно:</b>" in t for t in texts(calls, COORD)), texts(calls, COORD)

    # новое событие координатором
    await say(COORD, ui.BTN_NEW_EVENT)
    await say(COORD, "Открытый МК по керамике")
    await say(COORD, "31.10")
    await say(COORD, "16:00-18:00")
    await say(COORD, "Новинский б-р, 25")
    await say(COORD, "2")
    await press(COORD, ui.NewRoleCB(key="teacher"))
    calls = await press(COORD, ui.StepCB(name="once"))
    ev = db.one("SELECT * FROM events WHERE title='Открытый МК по керамике'")
    assert ev and ev["start_date"] == "2026-10-31" and ev["need"] == 2 and ev["role"] == "teacher"
    assert any("Событие добавлено" in t for t in texts(calls))

    # отмена создания события: словом посреди ввода даты и кнопкой под вопросом
    before = db.one("SELECT COUNT(*) AS n FROM events")["n"]
    calls = await say(COORD, ui.BTN_NEW_EVENT)
    assert any(b.text == "Отмена" for c in calls if getattr(c, "reply_markup", None) and hasattr(c.reply_markup, "inline_keyboard")
               for row in c.reply_markup.inline_keyboard for b in row)
    await say(COORD, "Тестовое событие")
    assert any("Отменено" in t for t in texts(await say(COORD, "отмена")))
    assert any("Дата" in t for t in texts(await say(COORD, "31.10"))) is False, "после отмены мастер не продолжается"
    await say(COORD, ui.BTN_NEW_EVENT)
    await press(COORD, ui.StepCB(name="cancel_fsm"))
    await say(COORD, "Ещё одно")
    assert db.one("SELECT COUNT(*) AS n FROM events")["n"] == before

    # карточка волонтёра: участие, ближайшее, вопрос; личное сообщение
    card_text, _ = coordinator.card(ANNA)
    assert "Участие" in card_text and "Во сколько сбор" in card_text and "Из анкеты" in card_text, card_text
    await press(COORD, ui.StepCB(name=f"dm{ANNA}"))
    assert any("Захватите фартук" in t for t in texts(await say(COORD, "Захватите фартук"), ANNA))

    # рассылка: кому → тип → текст → предпросмотр → отправка → история
    assert any("Рассылки" in t for t in texts(await say(COORD, ui.BTN_BROADCASTS)))
    await press(COORD, ui.BcCB(step="new"))
    await press(COORD, ui.BcCB(step="role"))
    await press(COORD, ui.BcCB(step="aud", val="role.assistant"))
    await press(COORD, ui.BcCB(step="kind", val="important"))
    preview = texts(await say(COORD, "Суббота переносится на 15:00"))
    assert any("Проверьте" in t and "1 чел." in t for t in preview), preview
    calls = await press(COORD, ui.BcCB(step="send"))
    assert any("Важное от фонда" in t and "15:00" in t for t in texts(calls, ANNA))
    assert db.one("SELECT recipients FROM broadcasts")["recipients"] == 1
    # рассылка с картинкой и подписью
    await press(COORD, ui.BcCB(step="new"))
    await press(COORD, ui.BcCB(step="aud", val="active"))
    await press(COORD, ui.BcCB(step="kind", val="news"))
    preview = await say(COORD, photo="PHOTO-AFISHA", caption="Афиша выставки «Невидимый труд»")
    assert any(type(c).__name__ == "SendPhoto" and c.photo == "PHOTO-AFISHA" and c.chat_id == COORD for c in preview)
    calls = await press(COORD, ui.BcCB(step="send"))
    pics = [c for c in calls if type(c).__name__ == "SendPhoto" and c.chat_id == ANNA]
    assert pics and pics[0].photo == "PHOTO-AFISHA" and "Невидимый труд" in pics[0].caption and "Новости фонда" in pics[0].caption
    assert db.one("SELECT photo FROM broadcasts ORDER BY id DESC")["photo"] == "PHOTO-AFISHA"
    assert len(coordinator_bc.recipients("active", "news")) == 1
    await press(ANNA, ui.PrefCB(key="news"))  # волонтёр отключил новости
    assert not coordinator_bc.recipients("active", "news") and coordinator_bc.recipients("active", "important")

    # выгрузки и итоги
    for kind in ("people", "teams", "hours"):
        assert docs(await press(COORD, ui.ExportCB(kind=kind)), COORD), kind
    assert any("Итоги" in t for t in texts(await press(COORD, ui.ExportCB(kind="summary")), COORD))

    # пауза: волонтёра на паузе не предлагают
    await press(ANNA, ui.PrefCB(key="paused"))
    assert ANNA not in [u["id"] for u, _ in coordinator.candidates(db.event("art"), datetime(2026, 10, 31).date())]

    # тестовый сброс: работает даже посреди ввода почты; волонтёр — с нуля, координатор сохраняет вход
    await say(ANNA, ui.BTN_LOGIN)
    assert any("сбросить диалог" in t for t in texts(await say(ANNA, ui.BTN_RESET)))
    out = texts(await press(ANNA, ui.StepCB(name="reset_yes")))
    assert any("Впервые у нас?" in t for t in out), out
    assert db.user(ANNA)["status"] == "new" and not db.user(ANNA)["email"]
    assert not db.all_("SELECT * FROM invites WHERE user_id=?", ANNA) and not db.all_("SELECT * FROM meetings WHERE user_id=?", ANNA)
    await say(COORD, "/reset")
    await press(COORD, ui.StepCB(name="reset_yes"))
    assert db.user(COORD)["is_coordinator"] == 1 and db.user(COORD)["status"] == "new"
    assert any(b.text == ui.BTN_RESET for row in ui.menu(db.user(ANNA)).inline_keyboard for b in row)
    assert ui.BTN_TO_COORD in labels(db.user(COORD)), "после сброса координатор видит путь волонтёра и может вернуться"

    print("PASS: меню кнопками под сообщениями, без нижней клавиатуры, вход координатора, режимы, лента вместо уведомлений, карточка волонтёра, рассылки с текстом и картинкой, анкета для новых, вход по почте и коду (Unisender Go, тестовый режим), запись на собеседование с сайта, плашка «Меню» после входа, допуск только после собеседования, приглашение → согласие → подтверждение, "
          "мои занятия и .ics, материалы с группой, вопрос и ответ, срочный отказ, новое событие и его отмена, выгрузки, пауза, тестовый сброс диалога")


asyncio.run(main())
