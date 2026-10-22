"""Волонтёр, когда бот подключён к платформе «Опора»: все данные — с сайта, бот только показывает и передаёт.

Те же разделы меню, что и без платформы (Мои занятия, Материалы, Собеседование, Написать координатору,
Настройки), но занятия, приглашения, собеседования, переписка и «Как прошло?» живут на сайте: бот читает
их через API от имени человека и отправляет туда его ответы. Своей базы событий бот в этом режиме не ведёт.
"""
import time
from datetime import datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import db, platform, ui
from .config import TZ
from .platform import ApiFailure, NotLinked, PlatformError
from .schedule import human

router = Router(name="platform_volunteer")
router.message.filter(lambda _: platform.enabled(), F.chat.type == "private")
router.callback_query.filter(lambda _: platform.enabled(), F.message.chat.type == "private")
# Ввод в шагах диалога — любой текст, кроме команд: /start bind_… и /menu уходят своим обработчикам.
TEXT = F.text & ~F.text.startswith("/")

SITE_DOWN = "Сайт фонда сейчас не отвечает. Попробуйте через пару минут."
STALE = "Пока вы смотрели, на сайте что-то поменялось. Откройте раздел ещё раз."
FAILED = "Не получилось. Попробуйте ещё раз чуть позже или откройте сайт."
STATUS = {"invited": "ждём вашего ответа", "pending": "координатор ещё согласует участие", "confirmed": "вы идёте",
          "declined": "вы отказались", "cancelled": "отменено", "expired": "приглашение истекло"}
# Сайт сохраняет профиль и черновик «Как прошло?» целиком: при записи передаём все поля, меняя только нужные.
PROFILE_FIELDS = ("display_name", "about", "tags", "lifecycle", "paused_until", "photo_asset_id", "ai_about", "ai_skills", "ai_interests")
REFLECTION_FIELDS = ("mood", "text", "unexpected", "help", "help_text", "continuation", "restricted")
MSK = ZoneInfo("Europe/Moscow")  # в этом поясе сайт пишет время в своих уведомлениях


class PA(CallbackData, prefix="pa"):
    action: str  # open, yes, no, cancel, cancel_yes, ask, ics
    aid: str = ""


class PM(CallbackData, prefix="pm"):
    action: str  # cancel, cancel_yes
    bid: str


class PR(CallbackData, prefix="pr"):
    cid: str  # ответить в разговор на сайте


class PF(CallbackData, prefix="pf"):
    step: str  # mood, cont
    aid: str
    val: str


class PS(CallbackData, prefix="ps"):
    key: str  # news, quiet, pause


class Ask(StatesGroup):
    text = State()


class Reply(StatesGroup):
    text = State()


class AskAssignment(StatesGroup):
    text = State()


# --- общее ----------------------------------------------------------------------------

def local(iso: str) -> datetime:
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(TZ)


def when(start: str, end: str | None = None) -> str:
    s = local(start)
    text = f"{human(s.date())}, {s:%H:%M}"
    if end:
        e = local(end)
        text += f"–{e:%H:%M}" if e.date() == s.date() else f" — {human(e.date())}, {e:%H:%M}"
    return text


def short(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


def place(a: dict) -> str:
    return escape(a.get("location") or a.get("venue") or "место уточним")


def site_kb(text: str, path: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, url=platform.site(path))]])


async def not_linked(target: Message) -> None:
    """Привязку отключили на сайте — человек снова «новый», показываем приветствие."""
    platform.forget(target.chat.id)
    db.update_user(target.chat.id, status="new", is_coordinator=0)
    await target.answer("Telegram больше не подключён к вашему профилю. Чтобы снова получать приглашения, "
                        "нажмите «Подключить Telegram» в профиле на сайте.", reply_markup=site_kb("Открыть профиль", "/profile"))


async def run(target: Message, coro):
    """Запрос к сайту с понятными ответами на ошибки. Возвращает результат или None."""
    try:
        return await coro
    except NotLinked:
        await not_linked(target)
    except ApiFailure as e:
        # 409 бывает и по делу (не пройдена подготовка, пересечение по времени) — тогда показываем объяснение сайта
        await target.answer(STALE if e.code == "version_conflict" else e.message or FAILED)
    except PlatformError:
        await target.answer(SITE_DOWN)
    return None


async def schedule(uid: int, days: int = 45, state: str = "active") -> list[dict]:
    today = db.now().date()
    page = await platform.get(uid, "/me/schedule", **{"from": today.isoformat(), "to": (today + timedelta(days=days)).isoformat(),
                                                       "timezone": str(TZ), "state": state, "limit": 100})
    return sorted(page["items"], key=lambda a: a["starts_at"])


_policy: dict[str, tuple[float, str]] = {}  # потребность события → (до когда помним, кто подтверждает участие)


async def answerable(uid: int, a: dict) -> bool:
    """Можно ли ответить «Приду». Сайт ждёт согласования координатора, только если так настроена роль."""
    if "confirm" not in a["allowed_actions"]:
        return False
    if a.get("approved_at"):
        return True
    need = a["staffing_need_id"]
    hit = _policy.get(need)
    if not hit or hit[0] < time.time():
        try:
            event = await platform.get(uid, f"/me/events/{a['occurrence_id']}")
            policy = next((n["approval_policy"] for n in event["needs"] if n["id"] == need), "coordinator")
        except ApiFailure:
            policy = "coordinator"
        hit = _policy[need] = (time.time() + 600, policy)
    return hit[1] == "self_confirmation"


async def with_answers(uid: int, items: list[dict]) -> list[dict]:
    for a in items:
        a["answerable"] = await answerable(uid, a)
    return items


def status_text(a: dict) -> str:
    if a["status"] == "invited" and not a.get("answerable"):
        return STATUS["pending"]
    return STATUS.get(a["status"], a["status"])


def assignment_line(a: dict) -> str:
    return f"<b>{escape(a['title'])}</b>\n{when(a['starts_at'], a['ends_at'])}, {place(a)}\n{escape(a['role_title'])}: {status_text(a)}"


def invite_kb(a: dict) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if a.get("answerable"):
        b.button(text="Приду", callback_data=PA(action="yes", aid=a["id"]))
        b.button(text="Не смогу", callback_data=PA(action="no", aid=a["id"]))
    b.button(text="Подробнее", callback_data=PA(action="open", aid=a["id"]))
    b.adjust(2, 1)
    return b.as_markup()


def invite_text(a: dict) -> str:
    return (f"Вас приглашают на занятие\n\n<b>{escape(a['title'])}</b>\n{when(a['starts_at'], a['ends_at'])}\n{place(a)}\n"
            f"Роль: {escape(a['role_title'])}\n\nПридёте?")


def evening_before(a: dict) -> datetime:
    """Когда напоминаем: в 18:00 накануне."""
    return (local(a["starts_at"]) - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)


def echo_key(uid: int, label: str, a: dict) -> str:
    """Начало уведомления, которое сайт сам пришлёт об этом действии: его не пересылаем (см. pjobs)."""
    start = datetime.fromisoformat(a["starts_at"].replace("Z", "+00:00")).astimezone(MSK)
    return f"p:echo:{uid}:{label}. {a['title']}. {start:%d.%m.%Y в %H:%M} МСК"


# --- Мои занятия ------------------------------------------------------------------------

async def my_events(msg: Message) -> None:
    uid = msg.chat.id

    async def load():
        return await with_answers(uid, await schedule(uid)), await platform.get(uid, "/me/hours")

    res = await run(msg, load())
    if res is None:
        return
    items, hours = res
    head = "📅 <b>Мои занятия</b>"
    if hours["total_minutes"]:
        head += f"\nВы уже провели с фондом {hours['total_minutes'] // 60} ч {hours['total_minutes'] % 60:02d} мин."
    if hours.get("pending_minutes"):
        head += f" Ещё {hours['pending_minutes'] // 60} ч {hours['pending_minutes'] % 60:02d} мин ждут подтверждения."
    if not items:
        await msg.answer(head + "\n\nБлижайших занятий нет. Приглашения придут сюда, а выбрать занятие самим можно на сайте.",
                         reply_markup=site_kb("Выбрать на сайте", "/opportunities"))
        return
    b = InlineKeyboardBuilder()
    for a in items[:8]:
        label = short(f"{local(a['starts_at']):%d.%m} {a['title']}", 40)
        b.button(text=f"Ответить: {label}" if a["answerable"] else label, callback_data=PA(action="open", aid=a["id"]))
    if any(a["status"] == "confirmed" for a in items):
        b.button(text="🗓 Добавить в календарь", callback_data=PA(action="ics"))
    b.adjust(1)
    more = f"\n\nИ ещё {len(items) - 8} — на сайте." if len(items) > 8 else ""
    await msg.answer(head + "\n\n" + "\n\n".join(assignment_line(a) for a in items[:8]) + more, reply_markup=b.as_markup())


def link(href: str) -> str:
    """Ссылки сайта в подготовке относительные — в Telegram нужен полный адрес."""
    return platform.site(href) if href.startswith("/") else href


async def assignment_view(uid: int, aid: str) -> tuple[str, InlineKeyboardMarkup]:
    a = await platform.get(uid, f"/assignments/{aid}")
    a["answerable"] = await answerable(uid, a)
    lines = [f"<b>{escape(a['title'])}</b>", when(a["starts_at"], a["ends_at"]), place(a),
             f"Роль: {escape(a['role_title'])}", f"Статус: {status_text(a)}"]
    if a["occurrence_status"] == "cancelled":
        lines.append("\n❗️ Занятие отменили.")
    pending = [r["title"] for r in a.get("readiness", []) if r["state"] == "pending" and r["level"] == "mandatory"]
    if pending:
        lines.append("\nДо занятия нужно: " + "; ".join(escape(x) for x in pending))
    if a["status"] == "confirmed":
        try:
            prep = await platform.get(uid, f"/me/assignments/{aid}/preparation")
        except ApiFailure:
            prep = None
        if prep:
            if prep.get("tasks"):
                lines.append(f"\n📝 <b>Что делать</b>\n{escape(short(prep['tasks'], 1200))}")
            if prep.get("checklist"):
                lines.append("\n📎 <b>Подготовка</b>")
                lines += [("☑️ " if c["checked"] else "▫️ ")
                          + (f"<a href=\"{escape(link(c['href']))}\">{escape(c['title'])}</a>" if c.get("href") else escape(c["title"]))
                          for c in prep["checklist"][:15]]
            if prep.get("contacts"):
                lines.append("\n🙋 <b>Кто вас встретит</b>")
                lines += [f"{escape(c['display_name'])}, {escape(c['role'])}" for c in prep["contacts"][:5]]
            answered = [q for q in prep.get("questions", []) if q.get("public_answer")]
            if answered:
                lines.append("\n💬 <b>Ответы координатора</b>")
                lines += [f"— {escape(short(q['text'], 200))}\n{escape(short(q['public_answer'], 500))}" for q in answered[-3:]]
    b = InlineKeyboardBuilder()
    if a["answerable"]:
        b.button(text="Приду", callback_data=PA(action="yes", aid=aid))
        b.button(text="Не смогу", callback_data=PA(action="no", aid=aid))
    if a["status"] == "confirmed" and "cancel" in a["allowed_actions"]:
        b.button(text="Не получится прийти", callback_data=PA(action="cancel", aid=aid))
    if a["status"] in ("invited", "confirmed"):
        b.button(text="Задать вопрос", callback_data=PA(action="ask", aid=aid))
    b.row(InlineKeyboardButton(text="Открыть на сайте", url=platform.site("/my/assignments")))
    b.adjust(2 if a["answerable"] else 1, 1, 1, 1)
    return short("\n".join(lines), 4000), b.as_markup()


@router.callback_query(PA.filter(F.action == "open"))
async def open_assignment(cb: CallbackQuery, callback_data: PA):
    await cb.answer()
    res = await run(cb.message, assignment_view(cb.message.chat.id, callback_data.aid))
    if res:
        await cb.message.answer(res[0], reply_markup=res[1], disable_web_page_preview=True)


@router.callback_query(PA.filter(F.action.in_({"yes", "no", "cancel_yes"})))
async def answer_assignment(cb: CallbackQuery, callback_data: PA):
    uid, aid = cb.message.chat.id, callback_data.aid
    command = {"yes": "confirm", "no": "decline", "cancel_yes": "cancel"}[callback_data.action]

    async def act():
        a = await platform.get(uid, f"/assignments/{aid}")
        if command not in a["allowed_actions"]:
            return a, False
        return await platform.post(uid, f"/assignments/{aid}/{command}", {"expected_version": a["version"]}), True

    await cb.answer()
    res = await run(cb.message, act())
    if not res:
        return
    a, done = res
    if not done:
        await cb.message.answer(f"Ответ уже есть: {STATUS.get(a['status'], a['status'])}.")
        return
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001 — старое сообщение могли удалить
        pass
    if command == "confirm":
        text = f"Записали, ждём вас: <b>{escape(a['title'])}</b>, {when(a['starts_at'], a['ends_at'])}."
        if db.now() < evening_before(a) - timedelta(hours=6):
            text += " Накануне вечером напомним."
    elif command == "decline":
        text = "Поняли, в этот раз без вас. Спасибо, что ответили."
    else:
        db.mark_sent(echo_key(uid, "Участие отменено", a))
        text = "Отменили. Координатор уже видит, что вы не придёте. Спасибо, что предупредили."
    await cb.message.answer(text)


@router.callback_query(PA.filter(F.action == "cancel"))
async def cancel_ask(cb: CallbackQuery, callback_data: PA):
    b = InlineKeyboardBuilder()
    b.button(text="Да, отменить", callback_data=PA(action="cancel_yes", aid=callback_data.aid))
    b.button(text="Нет, приду", callback_data=ui.MenuCB(item="home"))
    await cb.message.answer("Точно не получится? Координатор увидит отмену и поищет замену.", reply_markup=b.as_markup())
    await cb.answer()


@router.callback_query(PA.filter(F.action == "ics"))
async def calendar_file(cb: CallbackQuery):
    await cb.answer()
    items = await run(cb.message, schedule(cb.message.chat.id))
    if items is None:
        return
    mine = [a for a in items if a["status"] == "confirmed"]
    await cb.message.answer_document(BufferedInputFile(ics(mine), filename="detimarie.ics"),
                                     caption="Откройте файл, и занятия появятся в календаре телефона.")


def ics(items: list[dict]) -> bytes:
    fmt = "%Y%m%dT%H%M%SZ"
    utc = lambda iso: datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(timezone.utc).strftime(fmt)  # noqa: E731
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Deti Marii//Opora bot//RU", "CALSCALE:GREGORIAN"]
    for a in items:
        out += ["BEGIN:VEVENT", f"UID:{a['id']}@detimarie_bot", f"DTSTAMP:{datetime.now(timezone.utc).strftime(fmt)}",
                f"DTSTART:{utc(a['starts_at'])}", f"DTEND:{utc(a['ends_at'])}",
                f"SUMMARY:{a['title']} — фонд «Дети Марии»", "LOCATION:" + (a["location"] or "").replace(",", "\\,"),
                f"DESCRIPTION:{a['role_title']}", "END:VEVENT"]
    out.append("END:VCALENDAR")
    return "\r\n".join(out).encode("utf-8")


# --- вопрос по занятию -------------------------------------------------------------------

@router.callback_query(PA.filter(F.action == "ask"))
async def ask_assignment(cb: CallbackQuery, callback_data: PA, state: FSMContext):
    await state.set_state(AskAssignment.text)
    await state.update_data(aid=callback_data.aid)
    await cb.message.answer("Напишите вопрос одним сообщением. Ответ координатора придёт сюда.", reply_markup=ui.cancel_kb())
    await cb.answer()


@router.message(AskAssignment.text, TEXT)
async def ask_assignment_text(msg: Message, state: FSMContext):
    aid = (await state.get_data()).get("aid")
    await state.clear()
    if await run(msg, platform.post(msg.chat.id, f"/me/assignments/{aid}/questions", {"text": msg.text[:2000]})) is not None:
        await msg.answer("Отправили координатору. Ответ придёт сюда.")


# --- Материалы -------------------------------------------------------------------------

async def materials(msg: Message) -> None:
    items = await run(msg, schedule(msg.chat.id))
    if items is None:
        return
    confirmed = [a for a in items if a["status"] == "confirmed"]
    if not confirmed:
        await msg.answer("📎 Материалы появятся здесь, когда вы подтвердите участие в занятии.")
        return
    res = await run(msg, assignment_view(msg.chat.id, confirmed[0]["id"]))
    if res:
        await msg.answer(short("📎 <b>Ближайшее занятие</b>\n\n" + res[0], 4000), reply_markup=res[1], disable_web_page_preview=True)


# --- Собеседование -----------------------------------------------------------------------

async def meeting(msg: Message) -> None:
    rows = await run(msg, platform.get(msg.chat.id, "/me/interviews"))
    if rows is None:
        return
    soon = db.now() - timedelta(hours=2)
    booked = sorted((m for m in rows if m["status"] == "booked" and local(m["ends_at"]) >= soon), key=lambda m: m["starts_at"])
    if not booked:
        await msg.answer("🤝 Вы пока не записаны на собеседование. Время можно выбрать в личном кабинете на сайте.",
                         reply_markup=site_kb("Выбрать время", "/application"))
        return
    m = booked[0]
    text = (f"🤝 <b>Собеседование с координатором</b>\n{when(m['starts_at'], m['ends_at'])}\n{escape(m['venue'] or 'онлайн')}\n\n"
            "Напомним за день и за 15 минут.")
    b = InlineKeyboardBuilder()
    if m.get("join_url"):
        b.row(InlineKeyboardButton(text="Подключиться к встрече", url=m["join_url"]))
    b.row(InlineKeyboardButton(text="Перенести", url=platform.site("/application")),
          InlineKeyboardButton(text="Отменить", callback_data=PM(action="cancel", bid=m["id"]).pack()))
    await msg.answer(text, reply_markup=b.as_markup())


@router.callback_query(PM.filter(F.action == "cancel"))
async def meeting_cancel_ask(cb: CallbackQuery, callback_data: PM):
    b = InlineKeyboardBuilder()
    b.button(text="Да, отменить", callback_data=PM(action="cancel_yes", bid=callback_data.bid))
    b.button(text="Нет, приду", callback_data=ui.MenuCB(item="home"))
    await cb.message.answer("Отменить запись на собеседование? Новое время потом можно выбрать в кабинете.",
                            reply_markup=b.as_markup())
    await cb.answer()


@router.callback_query(PM.filter(F.action == "cancel_yes"))
async def meeting_cancel(cb: CallbackQuery, callback_data: PM):
    uid = cb.message.chat.id

    async def act():
        rows = await platform.get(uid, "/me/interviews")
        m = next((r for r in rows if r["id"] == callback_data.bid), None)
        if not m or m["status"] != "booked":
            return "gone"
        return await platform.post(uid, f"/interviews/{m['id']}/cancel",
                                   {"expected_version": m["version"], "reason": "Не смогу прийти, отменено в Telegram"})

    await cb.answer()
    res = await run(cb.message, act())
    if res == "gone":
        await cb.message.answer("Эта запись уже отменена или перенесена.")
    elif res:
        await cb.message.answer("Запись отменена. Когда будете готовы, выберите новое время в кабинете.",
                                reply_markup=site_kb("Выбрать время", "/application"))


# --- переписка с координатором -----------------------------------------------------------

async def ask(msg: Message, state: FSMContext) -> None:
    await state.set_state(Ask.text)
    await msg.answer("💬 Напишите координатору одним сообщением.", reply_markup=ui.cancel_kb())


async def coordinator_conversation(uid: int) -> str:
    """Личный разговор с координатором: того, кто ведёт собеседование, или первого координатора фонда.
    Пустая строка — координатора для переписки нет."""
    preferred = None
    try:
        rows = await platform.get(uid, "/me/interviews")
        preferred = next((m["coordinator_id"] for m in rows if m["status"] == "booked"), None)
    except ApiFailure:
        pass
    contacts = (await platform.get(uid, "/conversations/contacts", limit=50))["items"]
    coords = [c for c in contacts if c["is_coordinator"]]
    target = next((c["user_id"] for c in coords if c["user_id"] == preferred), coords[0]["user_id"] if coords else None)
    if not target:
        return ""
    return (await platform.post(uid, "/conversations/direct", {"recipient_id": target}))["id"]


@router.message(Ask.text, TEXT)
async def ask_text(msg: Message, state: FSMContext):
    await state.clear()
    cid = await run(msg, coordinator_conversation(msg.chat.id))
    if cid is None:
        return
    if not cid:
        await msg.answer("Не нашли, кому из координаторов отправить. Напишите в «Сообщениях» на сайте.",
                         reply_markup=site_kb("Сообщения на сайте", "/messages"))
        return
    if await run(msg, platform.post(msg.chat.id, f"/conversations/{cid}/messages", {"text": msg.text[:4000]})) is not None:
        await msg.answer("Отправили координатору. Ответ придёт сюда.")


@router.callback_query(PR.filter())
async def reply_start(cb: CallbackQuery, callback_data: PR, state: FSMContext):
    await state.set_state(Reply.text)
    await state.update_data(cid=callback_data.cid)
    await cb.message.answer("Напишите ответ одним сообщением.", reply_markup=ui.cancel_kb())
    await cb.answer()


@router.message(Reply.text, TEXT)
async def reply_text(msg: Message, state: FSMContext):
    cid = (await state.get_data()).get("cid")
    await state.clear()
    if await run(msg, platform.post(msg.chat.id, f"/conversations/{cid}/messages", {"text": msg.text[:4000]})) is not None:
        await msg.answer("Отправлено.")


def reply_kb(cid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Ответить", callback_data=PR(cid=cid).pack())]])


# --- «Как прошло?» -----------------------------------------------------------------------
# Один вопрос — одно сообщение: ответы меняют его на месте, а не добавляют новые.

MOODS = [("great", "😍 Отлично"), ("good", "🙂 Хорошо"), ("ok", "😐 Нормально"), ("hard", "😟 Было трудно")]
# как на сайте; «Хочу поговорить» — это ещё и просьба о разговоре (help=yes), по ней координатор свяжется
CONTINUE = [("yes", "Хочу продолжать"), ("other", "Хочу другую роль"), ("pause", "Нужна пауза"),
            ("talk", "Хочу поговорить"), ("finish", "Не планирую продолжать")]


def mood_kb(aid: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, label in MOODS:
        b.button(text=label, callback_data=PF(step="mood", aid=aid, val=key))
    b.adjust(2, 2)
    return b.as_markup()


async def save_reflection(uid: int, aid: str, **changes) -> dict | None:
    """Черновик «Как прошло?» с сайта плюс изменения: настроение из первого шага и текст с сайта не теряются."""
    r = await platform.get(uid, f"/me/assignments/{aid}/reflection")
    if not r["can_submit"]:
        return None
    body = {k: r[k] for k in REFLECTION_FIELDS}
    body.update(changes, expected_version=r["version"])
    return await platform.put(uid, f"/me/assignments/{aid}/reflection", body)


async def edit(cb: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    try:
        await cb.message.edit_text(text, reply_markup=markup)
    except Exception:  # noqa: BLE001 — сообщение старше 48 часов или уже такое
        await cb.message.answer(text, reply_markup=markup)


@router.callback_query(PF.filter(F.step == "mood"))
async def after_mood(cb: CallbackQuery, callback_data: PF):
    uid, aid = cb.message.chat.id, callback_data.aid

    async def act():
        return await save_reflection(uid, aid, mood=callback_data.val) or "done"

    await cb.answer()
    r = await run(cb.message, act())
    if r is None:
        return
    if r == "done":
        await edit(cb, cb.message.html_text + "\n\nОтвет уже у координатора, спасибо!")
        return
    b = InlineKeyboardBuilder()
    for key, label in CONTINUE:
        b.button(text=label, callback_data=PF(step="cont", aid=aid, val=key))
    b.adjust(2, 2, 1)
    await edit(cb, f"{cb.message.html_text}\n{dict(MOODS)[callback_data.val]}\n\nА дальше как?", b.as_markup())


@router.callback_query(PF.filter(F.step == "cont"))
async def after_continue(cb: CallbackQuery, callback_data: PF):
    uid, aid, val = cb.message.chat.id, callback_data.aid, callback_data.val
    change = {"continuation": "discuss", "help": "yes"} if val == "talk" else {"continuation": val}

    async def act():
        r = await save_reflection(uid, aid, **change)
        if r is None:
            return "done"
        return await platform.post(uid, f"/me/assignments/{aid}/reflection/submit", {"expected_version": r["version"]})

    await cb.answer()
    r = await run(cb.message, act())
    if r is None:
        return
    text = f"{cb.message.html_text}\n{dict(CONTINUE)[val]}\n\nСпасибо, передали координатору."
    if r != "done" and (r.get("mood") == "hard" or val in ("talk", "other", "pause", "finish")):
        text += " Он свяжется с вами."
    await edit(cb, text, site_kb("Рассказать подробнее", "/my/assignments"))


# --- Настройки ---------------------------------------------------------------------------

def minutes(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


async def settings_view(uid: int) -> tuple[str, InlineKeyboardMarkup]:
    prefs = await platform.get(uid, "/me/notification-preferences")
    profile = await platform.get(uid, "/me/profile")
    news = bool(prefs["topics"].get("news")) and prefs.get("news_consent", True)
    quiet, paused = prefs["quiet_enabled"], profile["lifecycle"] == "paused"
    text = ("⚙️ <b>Настройки</b>\n\n"
            f"Новости фонда: {'присылаем' if news else 'не присылаем'}\n"
            f"Тихие часы {minutes(prefs['quiet_from'])}–{minutes(prefs['quiet_to'])}: {'включены' if quiet else 'выключены'}\n"
            f"Приглашения: {'на паузе' if paused else 'присылаем'}\n\n"
            "В тихие часы бот не пишет, сообщения придут утром. Эти же настройки есть в профиле на сайте.")
    b = InlineKeyboardBuilder()
    if prefs.get("news_consent", True):
        b.button(text=("Не присылать новости" if news else "Присылать новости"), callback_data=PS(key="news"))
    else:  # без согласия на новости сайт их не пришлёт: согласие даётся на сайте
        b.button(text="Новости: включить на сайте", url=platform.site("/profile?tab=notif"))
    b.button(text=("Выключить тихие часы" if quiet else "Включить тихие часы"), callback_data=PS(key="quiet"))
    b.button(text=("Снять паузу" if paused else "Поставить приглашения на паузу"), callback_data=PS(key="pause"))
    b.adjust(1)
    return text, b.as_markup()


async def settings(msg: Message) -> None:
    res = await run(msg, settings_view(msg.chat.id))
    if res:
        await msg.answer(res[0], reply_markup=res[1])


@router.callback_query(PS.filter())
async def toggle(cb: CallbackQuery, callback_data: PS):
    uid = cb.message.chat.id

    async def act():
        if callback_data.key == "pause":
            # PUT /me/profile заменяет профиль целиком: всё, что не передали, сайт сбросит (о себе, навыки, фото)
            p = await platform.get(uid, "/me/profile")
            body = {k: p[k] for k in PROFILE_FIELDS}
            body.update(expected_version=p["version"], paused_until=None,
                        lifecycle="active" if p["lifecycle"] == "paused" else "paused")
            await platform.put(uid, "/me/profile", body)
        else:
            p = await platform.get(uid, "/me/notification-preferences")
            body = {"email_enabled": p["email_enabled"], "in_app_enabled": p["in_app_enabled"], "no_contact": p["no_contact"],
                    "expected_version": p["version"], "quiet_enabled": p["quiet_enabled"], "topics": p["topics"]}
            if callback_data.key == "news":
                body["topics"] = {**p["topics"], "news": not p["topics"].get("news")}
            else:
                body["quiet_enabled"] = not p["quiet_enabled"]
            await platform.put(uid, "/me/notification-preferences", body)
        return await settings_view(uid)

    await cb.answer()
    res = await run(cb.message, act())
    if res:
        try:
            await cb.message.edit_text(res[0], reply_markup=res[1])
        except Exception:  # noqa: BLE001 — текст не изменился или сообщение старое
            await cb.message.answer(res[0], reply_markup=res[1])


# --- кнопки меню и старые текстовые кнопки -----------------------------------------------

ITEMS = {
    "my": lambda m, s: my_events(m),
    "materials": lambda m, s: materials(m),
    "meeting": lambda m, s: meeting(m),
    "ask": lambda m, s: ask(m, s),
    "settings": lambda m, s: settings(m),
}


@router.message(F.text == ui.BTN_MY)
async def my_text(msg: Message):
    await my_events(msg)


@router.message(F.text == ui.BTN_MATERIALS)
async def materials_text(msg: Message):
    await materials(msg)


@router.message(F.text == ui.BTN_MEETING)
async def meeting_text(msg: Message):
    await meeting(msg)


@router.message(F.text == ui.BTN_ASK)
async def ask_button(msg: Message, state: FSMContext):
    await ask(msg, state)


@router.message(F.text == ui.BTN_SETTINGS)
async def settings_text(msg: Message):
    await settings(msg)
