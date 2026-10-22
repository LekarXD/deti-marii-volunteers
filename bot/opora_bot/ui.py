"""Кнопки, данные колбэков и тексты, которые нужны и волонтёру, и координатору."""
import json
from contextvars import ContextVar
from datetime import date
from html import escape

from aiogram.exceptions import TelegramAPIError
from aiogram.filters.callback_data import CallbackData

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, ReplyKeyboardRemove
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import db, platform
from .config import TEST_MODE
from .schedule import WEEKDAYS, human, time_range
from .seed import GROUPS, ROLES

# --- колбэки (до 64 байт) ------------------------------------------------------


class RoleCB(CallbackData, prefix="role"):
    key: str


class NewRoleCB(CallbackData, prefix="nrole"):
    key: str


class DayCB(CallbackData, prefix="day"):
    day: int


class StepCB(CallbackData, prefix="step"):
    name: str


class MeetCB(CallbackData, prefix="meet"):
    action: str  # yes · cancel
    mid: int = 0


class InvCB(CallbackData, prefix="inv"):
    action: str  # yes · no · more · mat (волонтёр) | conf · drop (координатор)
    eid: str
    d: str  # YYYYMMDD
    uid: int = 0


class EvCB(CallbackData, prefix="ev"):
    action: str  # months · month (d=ГГГГММ) · open · call · xls · cancel · cancel_yes
    eid: str = ""
    d: str = ""


class PickCB(CallbackData, prefix="pick"):
    uid: int


class AdmitCB(CallbackData, prefix="adm"):
    uid: int
    action: str  # итог встречи: yes (допустить) · no (не допускать) · noshow (не пришёл)


class AnswerCB(CallbackData, prefix="ans"):
    qid: int


class AfterCB(CallbackData, prefix="aft"):
    action: str  # ok · hard · absent · hours · other
    eid: str
    d: str
    h: float = 0


class CardCB(CallbackData, prefix="card"):
    uid: int


class FeedCB(CallbackData, prefix="feed"):
    action: str = "open"


class BcCB(CallbackData, prefix="bc"):
    step: str   # aud · role · day · kind · send · cancel · new
    val: str = ""


class MenuCB(CallbackData, prefix="menu"):
    item: str


class PrefCB(CallbackData, prefix="pref"):
    key: str


class ExportCB(CallbackData, prefix="exp"):
    kind: str


def dkey(day: date) -> str:
    return day.strftime("%Y%m%d")


def dparse(s: str) -> date:
    return date(int(s[:4]), int(s[4:6]), int(s[6:8]))


# --- меню -----------------------------------------------------------------------

BTN_MY = "📅 Мои занятия"
BTN_MATERIALS = "📎 Материалы"
BTN_MEETING = "🤝 Собеседование"
BTN_HOME = "🏠 Меню"
BTN_ASK = "💬 Написать координатору"
BTN_SETTINGS = "⚙️ Настройки"
BTN_EVENTS = "🗓 События"
BTN_FEED = "🔔 Новые уведомления"
BTN_BROADCASTS = "📣 Рассылки"
BTN_TO_VOLUNTEER = "🙋 Режим волонтёра"
BTN_TO_COORD = "🧭 Режим координатора"
BTN_NEW_EVENT = "✨ Новое событие"
BTN_EXPORTS = "📊 Выгрузки"
BTN_LOGIN = "✉️ Войти по почте"
BTN_ANKETA = "📝 Заполнить анкету"
BTN_CONNECT = "🔗 Подключить из профиля на сайте"
BTN_RESET = "🧪 Сбросить диалог (тест)"


def coord_mode(u) -> bool:
    return bool(u and u["is_coordinator"] and db.prefs(u).get("mode", "coord") == "coord")


LABELS = {
    "feed": BTN_FEED, "events": BTN_EVENTS, "broadcasts": BTN_BROADCASTS, "new_event": BTN_NEW_EVENT,
    "exports": BTN_EXPORTS, "to_vol": BTN_TO_VOLUNTEER, "my": BTN_MY, "materials": BTN_MATERIALS,
    "meeting": BTN_MEETING, "ask": BTN_ASK, "settings": BTN_SETTINGS, "to_coord": BTN_TO_COORD,
    "login": BTN_LOGIN, "reset": BTN_RESET,
}


def menu(u) -> InlineKeyboardMarkup:
    """Меню — кнопки под сообщением бота. Два режима: координатор видит свои кнопки, волонтёр — свои."""
    b = InlineKeyboardBuilder()
    item = lambda key: b.button(text=LABELS[key], callback_data=MenuCB(item=key))  # noqa: E731
    sizes = []
    if coord_mode(u):
        for key in ("feed", "events", "broadcasts", "new_event", "exports", "to_vol"):
            item(key)
        sizes = [2, 2, 2]
    elif u["status"] == "new":
        b.button(text=BTN_ANKETA, url=platform.anketa_url())
        if platform.enabled():
            # Вход — только ссылкой из профиля на сайте: так платформа знает, чей это Telegram.
            b.button(text=BTN_CONNECT, url=platform.profile_url())
        else:
            item("login")
        sizes = [1, 1]
    else:
        for key in ("my", "materials", "meeting", "ask", "settings"):
            item(key)
        sizes = [2, 2, 1]
    if u["is_coordinator"] and not coord_mode(u):
        item("to_coord")
        sizes.append(1)
    if TEST_MODE:
        item("reset")
        sizes.append(1)
    b.adjust(*sizes)
    return b.as_markup()


def menu_text(u) -> str:
    if coord_mode(u) and platform.enabled():
        n = db.prefs(u).get("todo")  # обновляется лентой и утренней сводкой (pcoordinator, pjobs)
        return "🧭 <b>Меню координатора</b>" + (f"\nНужно решить: {n or 'ничего'}" if n is not None else "")
    if coord_mode(u):
        n = len(db.open_actions())
        return f"🧭 <b>Меню координатора</b>\nНужно решить: {n or 'ничего'}"
    return "🏠 <b>Меню</b>"


async def drop_old_keyboard(target: Message, u) -> None:
    """Раньше меню было клавиатурой внизу. Один раз убираем её и объясняем, где теперь меню."""
    p = db.prefs(u)
    if p.get("inline_menu"):
        return
    await target.answer("Кнопки теперь — в сообщениях бота. Меню всегда под рукой: кнопка «Меню» слева от поля ввода "
                        "или команда /menu.", reply_markup=ReplyKeyboardRemove())
    p["inline_menu"] = True
    db.update_user(u["id"], prefs=json.dumps(p))


# --- экран: меню и разделы, открытые из него. Новый экран убирает старый, чтобы сообщения не копились в чате.
# Помним в памяти процесса: после перезапуска старые сообщения просто останутся, ничего не сломается.
# Как экраны сменяют друг друга — в screen.py.
SCREENS: dict[int, list[int]] = {}
# пока обрабатывается нажатие на кнопку экрана — что успели показать (см. screen.py)
TRACK: ContextVar[dict | None] = ContextVar("screen_track", default=None)


def remember(chat_id: int, message_id: int) -> None:
    ids = SCREENS.setdefault(chat_id, [])
    if message_id not in ids:
        ids.append(message_id)


async def clear_screen(bot, chat_id: int) -> None:
    for mid in SCREENS.pop(chat_id, []):
        try:
            await bot.delete_message(chat_id, mid)
        except TelegramAPIError:  # уже удалено или старше 48 часов
            pass


def home_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text=BTN_HOME, callback_data=MenuCB(item="home").pack())


async def send_menu(target: Message, u, text: str | None = None) -> None:
    await drop_old_keyboard(target, u)
    await clear_screen(target.bot, target.chat.id)
    sent = await target.answer(text or menu_text(u), reply_markup=menu(u))
    remember(sent.chat.id, sent.message_id)
    st = TRACK.get()
    if st is not None:  # меню само себе экран: кнопку «Меню» под ним не добавляем
        st["menu"] = True


# --- тексты -----------------------------------------------------------------------

STATUS_RU = {
    "invited": "приглашён(а)", "accepted": "согласился(лась), ждёт подтверждения", "declined": "не сможет",
    "confirmed": "подтверждён(а)", "attended": "был(а)", "absent": "не пришёл(ла)", "removed": "снят(а)",
}
USER_STATUS_RU = {"new": "не подключился", "candidate": "кандидат", "active": "допущен(а)"}


def person(u) -> str:
    name = escape(u["name"] or "Без имени")
    return f"{name} (@{escape(u['username'])})" if u["username"] else name


def roles_text(keys: str) -> str:
    return ", ".join(ROLES[k] for k in keys.split(",") if k in ROLES) or "не указаны"


def days_text(keys: str) -> str:
    return ", ".join(WEEKDAYS[int(k)] for k in keys.split(",") if k != "") or "не указаны"


def event_head(ev, day: date) -> str:
    lines = [f"<b>{escape(ev['title'])}</b>", f"📅 {human(day)}, {time_range(ev)}",
             f"📍 {escape(ev['place'])}" if ev["place"] else ""]
    if ev["role"]:
        lines.append(f"Роль: {ROLES.get(ev['role'], ev['role'])}")
    if ev["memo"]:
        lines.append(f"<i>{escape(ev['memo'])}</i>")
    return "\n".join(x for x in lines if x)


def materials_text(ev, day: date, with_group: bool) -> str:
    parts = [event_head(ev, day)]
    mats = json.loads(ev["materials"] or "[]")
    if mats:
        parts.append("\n📎 <b>Материалы</b>")
        for m in mats:
            if m.get("url"):
                parts.append(f"• <a href=\"{escape(m['url'])}\">{escape(m['title'])}</a>")
            else:
                parts.append(f"• <b>{escape(m['title'])}.</b> {escape(m.get('text', ''))}")
    if with_group and ev["group_name"] in GROUPS:
        parts.append(f"\n👧 <b>Группа «{escape(ev['group_name'])}»</b> <i>(демо-участники)</i>")
        for name, tip in GROUPS[ev["group_name"]]:
            parts.append(f"• <b>{name}.</b> {escape(tip)}")
    team = [r for r in db.team(ev["id"], day.isoformat()) if r["status"] in ("confirmed", "attended")]
    if team:
        parts.append("\n🙌 <b>Команда</b>")
        parts += [f"• {escape(r['name'] or 'Волонтёр')}" for r in team]
    return "\n".join(parts)


def coverage(ev, day: date) -> str:
    if not ev["need"]:
        return "волонтёры не нужны"
    return f"{db.confirmed_count(ev['id'], day.isoformat())} из {ev['need']}"


def cancel_kb() -> InlineKeyboardMarkup:
    """Кнопка «Отмена» под вопросом, на который бот ждёт ответа текстом."""
    b = InlineKeyboardBuilder()
    b.button(text="Отмена", callback_data=StepCB(name="cancel_fsm"))
    return b.as_markup()


def invite_kb(ev, day: date) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Приду", callback_data=InvCB(action="yes", eid=ev["id"], d=dkey(day)))
    b.button(text="Не смогу", callback_data=InvCB(action="no", eid=ev["id"], d=dkey(day)))
    b.button(text="Подробнее", callback_data=InvCB(action="more", eid=ev["id"], d=dkey(day)))
    b.adjust(2, 1)
    return b.as_markup()
