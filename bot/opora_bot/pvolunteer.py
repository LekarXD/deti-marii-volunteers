"""Волонтёр, когда бот подключён к платформе «Опора»: все данные — с сайта, бот только показывает и передаёт.

Те же разделы меню, что и без платформы (Мои занятия, Материалы, Собеседование, Написать координатору,
Настройки), но занятия, приглашения, собеседования, переписка и «Как прошло?» живут на сайте: бот читает
их через API от имени человека и отправляет туда его ответы. Своей базы событий бот в этом режиме не ведёт.
"""
from datetime import datetime, timedelta, timezone
from html import escape

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
router.message.filter(lambda _: platform.enabled())
router.callback_query.filter(lambda _: platform.enabled())

SITE_DOWN = "Сайт фонда сейчас не отвечает. Попробуйте через пару минут."
STALE = "Пока вы смотрели, данные на сайте изменились. Откройте раздел ещё раз."
STATUS = {"invited": "ждём ответа — придёте?", "pending": "ждём согласования координатора", "confirmed": "вы идёте ✅", "declined": "вы отказались",
          "cancelled": "отменено", "expired": "приглашение истекло"}


class PA(CallbackData, prefix="pa"):
    action: str  # open · yes · no · cancel · cancel_yes · ask · ics
    aid: str = ""


class PM(CallbackData, prefix="pm"):
    action: str  # cancel · cancel_yes
    bid: str


class PR(CallbackData, prefix="pr"):
    cid: str  # ответить в разговор на сайте


class PF(CallbackData, prefix="pf"):
    step: str  # mood · cont
    aid: str
    val: str


class PS(CallbackData, prefix="ps"):
    key: str  # news · quiet · pause


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


def site_kb(text: str, path: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=text, url=platform.site(path))]])


async def not_linked(target: Message) -> None:
    """Привязку отключили на сайте — человек снова «новый», показываем приветствие."""
    platform.forget(target.chat.id)
    db.update_user(target.chat.id, status="new", is_coordinator=0)
    await target.answer("Telegram больше не подключён к профилю на сайте. Чтобы снова получать приглашения, "
                        "откройте профиль и нажмите «Подключить Telegram».", reply_markup=site_kb("Открыть профиль", "/profile"))


async def run(target: Message, coro):
    """Запрос к сайту с понятными ответами на ошибки. Возвращает результат или None."""
    try:
        return await coro
    except NotLinked:
        await not_linked(target)
    except ApiFailure as e:
        # 409 бывает и по делу (не пройдена подготовка, пересечение по времени) — тогда показываем объяснение сайта
        await target.answer(STALE if e.code == "version_conflict" or not e.message else e.message)
    except PlatformError:
        await target.answer(SITE_DOWN)
    return None


async def schedule(uid: int, days: int = 45, state: str = "active") -> list[dict]:
    today = db.now().date()
    page = await platform.get(uid, "/me/schedule", **{"from": today.isoformat(), "to": (today + timedelta(days=days)).isoformat(),
                                                       "timezone": str(TZ), "state": state, "limit": 100})
    return sorted(page["items"], key=lambda a: a["starts_at"])


def can_answer(a: dict) -> bool:
    """Ответить «Приду» можно, когда участие согласовал координатор (так требует сайт)."""
    return "confirm" in a["allowed_actions"] and bool(a.get("approved_at"))


def status_text(a: dict) -> str:
    return STATUS["pending"] if a["status"] == "invited" and not a.get("approved_at") else STATUS.get(a["status"], a["status"])


def assignment_line(a: dict) -> str:
    return (f"• <b>{escape(a['title'])}</b> — {when(a['starts_at'], a['ends_at'])}\n"
            f"  {escape(a['role_title'])}, {escape(a['location'] or 'место уточняется')} · {status_text(a)}")


def invite_kb(a: dict) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if can_answer(a):
        b.button(text="Приду", callback_data=PA(action="yes", aid=a["id"]))
        b.button(text="Не смогу", callback_data=PA(action="no", aid=a["id"]))
    b.button(text="Подробнее", callback_data=PA(action="open", aid=a["id"]))
    b.adjust(2, 1)
    return b.as_markup()


def invite_text(a: dict) -> str:
    return (f"🎨 Приглашаем: <b>{escape(a['title'])}</b>\n📅 {when(a['starts_at'], a['ends_at'])}\n"
            f"📍 {escape(a['location'] or 'место уточняется')}\nРоль: {escape(a['role_title'])}\n\nПридёте?")


# --- Мои занятия ------------------------------------------------------------------------

async def my_events(msg: Message) -> None:
    uid = msg.chat.id
    items = await run(msg, schedule(uid))
    if items is None:
        return
    hours = await run(msg, platform.get(uid, "/me/hours"))
    if hours is None:
        return
    total = hours["total_minutes"]
    head = f"📅 <b>Мои занятия</b>\nВы уже помогли фонду: {total // 60} ч {total % 60:02d} мин."
    if hours.get("pending_minutes"):
        head += f" Ещё {hours['pending_minutes'] // 60} ч {hours['pending_minutes'] % 60:02d} мин ждут подтверждения координатора."
    b = InlineKeyboardBuilder()
    if not items:
        await msg.answer(head + "\n\nБлижайших занятий пока нет. Приглашения придут сюда, а выбрать занятие можно на сайте.",
                         reply_markup=site_kb("Возможности на сайте", "/opportunities"))
        return
    for a in items[:8]:
        label = f"{local(a['starts_at']):%d.%m} {a['title']}"[:40]
        if can_answer(a):
            b.button(text=f"✋ Ответить: {label}", callback_data=PA(action="open", aid=a["id"]))
        else:
            b.button(text=f"Подробнее: {label}", callback_data=PA(action="open", aid=a["id"]))
    if any(a["status"] == "confirmed" for a in items):
        b.button(text="🗓 Добавить в календарь телефона", callback_data=PA(action="ics"))
    b.adjust(1)
    await msg.answer(head + "\n\n" + "\n\n".join(assignment_line(a) for a in items[:8]), reply_markup=b.as_markup())


async def assignment_view(uid: int, aid: str) -> tuple[str, InlineKeyboardMarkup]:
    a = await platform.get(uid, f"/assignments/{aid}")
    lines = [f"<b>{escape(a['title'])}</b>", f"📅 {when(a['starts_at'], a['ends_at'])}",
             f"📍 {escape(a['location'] or 'место уточняется')}", f"Роль: {escape(a['role_title'])}",
             f"Статус: {status_text(a)}"]
    if a["occurrence_status"] == "cancelled":
        lines.append("❗️ Занятие отменено.")
    pending = [r["title"] for r in a.get("readiness", []) if r["state"] == "pending" and r["level"] == "mandatory"]
    if pending:
        lines.append("\nДо выхода нужно: " + "; ".join(escape(x) for x in pending))
    if a["status"] == "confirmed":
        try:
            prep = await platform.get(uid, f"/me/assignments/{aid}/preparation")
        except ApiFailure:
            prep = None
        if prep:
            if prep.get("tasks"):
                lines.append(f"\n📝 <b>Что делать</b>\n{escape(prep['tasks'])}")
            if prep.get("checklist"):
                lines.append("\n📎 <b>Подготовка</b>")
                lines += [f"{'☑️' if c['checked'] else '▫️'} " + (f"<a href=\"{escape(c['href'])}\">{escape(c['title'])}</a>" if c.get("href") else escape(c["title"]))
                          for c in prep["checklist"]]
            if prep.get("contacts"):
                lines.append("\n🙋 <b>Кто вас встретит</b>")
                lines += [f"• {escape(c['display_name'])} — {escape(c['role'])}" for c in prep["contacts"]]
            answered = [q for q in prep.get("questions", []) if q.get("public_answer")]
            if answered:
                lines.append("\n💬 <b>Ответы координатора</b>")
                lines += [f"• {escape(q['text'])}\n  — {escape(q['public_answer'])}" for q in answered[-3:]]
    b = InlineKeyboardBuilder()
    if can_answer(a):
        b.button(text="Приду", callback_data=PA(action="yes", aid=aid))
        b.button(text="Не смогу", callback_data=PA(action="no", aid=aid))
    if a["status"] == "confirmed" and "cancel" in a["allowed_actions"]:
        b.button(text="Не получится прийти", callback_data=PA(action="cancel", aid=aid))
    if a["status"] in ("invited", "confirmed"):
        b.button(text="❓ Вопрос по занятию", callback_data=PA(action="ask", aid=aid))
    b.row(InlineKeyboardButton(text="Открыть на сайте", url=platform.site("/my/assignments")))
    b.adjust(2, 1, 1, 1)
    return "\n".join(lines), b.as_markup()


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

    res = await run(cb.message, act())
    await cb.answer()
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
    text = {"confirm": f"Отлично, ждём вас! {escape(a['title'])}, {when(a['starts_at'], a['ends_at'])}. "
                       "Накануне в 18:00 пришлём напоминание.",
            "decline": "Поняли, спасибо, что предупредили. Позовём в другой раз.",
            "cancel": "Отменили ваше участие и предупредили координатора. Спасибо, что сообщили заранее."}[command]
    await cb.message.answer(text)


@router.callback_query(PA.filter(F.action == "cancel"))
async def cancel_ask(cb: CallbackQuery, callback_data: PA):
    b = InlineKeyboardBuilder()
    b.button(text="Да, не смогу", callback_data=PA(action="cancel_yes", aid=callback_data.aid))
    b.button(text="Нет, приду", callback_data=ui.MenuCB(item="home"))
    await cb.message.answer("Точно не получится прийти? Координатор увидит отказ и поищет замену.", reply_markup=b.as_markup())
    await cb.answer()


@router.callback_query(PA.filter(F.action == "ics"))
async def calendar_file(cb: CallbackQuery):
    await cb.answer()
    items = await run(cb.message, schedule(cb.message.chat.id))
    if items is None:
        return
    mine = [a for a in items if a["status"] == "confirmed"]
    await cb.message.answer_document(BufferedInputFile(ics(mine), filename="detimarie.ics"),
                                     caption="Откройте файл — занятия добавятся в календарь телефона.")


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
    await cb.message.answer("Напишите вопрос про это занятие одним сообщением. Ответ координатора придёт сюда.",
                            reply_markup=ui.cancel_kb())
    await cb.answer()


@router.message(AskAssignment.text, F.text)
async def ask_assignment_text(msg: Message, state: FSMContext):
    aid = (await state.get_data()).get("aid")
    await state.clear()
    if await run(msg, platform.post(msg.chat.id, f"/me/assignments/{aid}/questions", {"text": msg.text[:2000]})) is not None:
        await msg.answer("Вопрос отправлен координатору. Ответ придёт сюда и появится на сайте.")


# --- Материалы -------------------------------------------------------------------------

async def materials(msg: Message) -> None:
    items = await run(msg, schedule(msg.chat.id))
    if items is None:
        return
    confirmed = [a for a in items if a["status"] == "confirmed"]
    if not confirmed:
        await msg.answer("📎 Материалы к занятию появятся здесь, когда вы подтвердите участие.")
        return
    res = await run(msg, assignment_view(msg.chat.id, confirmed[0]["id"]))
    if res:
        await msg.answer("📎 <b>Ближайшее занятие</b>\n\n" + res[0], reply_markup=res[1], disable_web_page_preview=True)


# --- Собеседование -----------------------------------------------------------------------

async def meeting(msg: Message) -> None:
    rows = await run(msg, platform.get(msg.chat.id, "/me/interviews"))
    if rows is None:
        return
    soon = db.now() - timedelta(hours=2)
    booked = sorted((m for m in rows if m["status"] == "booked" and local(m["ends_at"]) >= soon), key=lambda m: m["starts_at"])
    if not booked:
        await msg.answer("🤝 Записи на собеседование сейчас нет. Выбрать время можно в личном кабинете на сайте.",
                         reply_markup=site_kb("Выбрать время", "/application"))
        return
    m = booked[0]
    text = (f"🤝 <b>Собеседование с координатором</b>\n📅 {when(m['starts_at'], m['ends_at'])}\n"
            f"📍 {escape(m['venue'] or 'онлайн')}\n\n🔔 Напомним за сутки и за 15 минут до начала.")
    b = InlineKeyboardBuilder()
    if m.get("join_url"):
        b.row(InlineKeyboardButton(text="Подключиться к встрече", url=m["join_url"]))
    b.row(InlineKeyboardButton(text="Не смогу прийти", callback_data=PM(action="cancel", bid=m["id"]).pack()))
    b.row(InlineKeyboardButton(text="Перенести на сайте", url=platform.site("/application")))
    await msg.answer(text, reply_markup=b.as_markup())


@router.callback_query(PM.filter(F.action == "cancel"))
async def meeting_cancel_ask(cb: CallbackQuery, callback_data: PM):
    b = InlineKeyboardBuilder()
    b.button(text="Да, отменить", callback_data=PM(action="cancel_yes", bid=callback_data.bid))
    b.button(text="Нет, приду", callback_data=ui.MenuCB(item="home"))
    await cb.message.answer("Отменить запись на собеседование? Новое время можно выбрать в кабинете на сайте.",
                            reply_markup=b.as_markup())
    await cb.answer()


@router.callback_query(PM.filter(F.action == "cancel_yes"))
async def meeting_cancel(cb: CallbackQuery, callback_data: PM):
    uid = cb.message.chat.id

    async def act():
        rows = await platform.get(uid, "/me/interviews")
        m = next((r for r in rows if r["id"] == callback_data.bid), None)
        if not m or m["status"] != "booked":
            return None
        return await platform.post(uid, f"/interviews/{m['id']}/cancel",
                                   {"expected_version": m["version"], "reason": "Не смогу прийти — отмечено в Telegram"})

    await cb.answer()
    res = await run(cb.message, act())
    if res:
        await cb.message.answer("Запись отменена, координатор увидит это. Выберите новое время на сайте, когда будет удобно.",
                                reply_markup=site_kb("Выбрать время", "/application"))


# --- переписка с координатором -----------------------------------------------------------

async def ask(msg: Message, state: FSMContext) -> None:
    await state.set_state(Ask.text)
    await msg.answer("💬 Напишите сообщение координатору одним сообщением. Ответ придёт сюда и будет виден на сайте в «Сообщениях».",
                     reply_markup=ui.cancel_kb())


async def coordinator_conversation(uid: int) -> str | None:
    """Личный разговор с координатором: того, кто ведёт собеседование, или первого координатора фонда."""
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
        return None
    return (await platform.post(uid, "/conversations/direct", {"recipient_id": target}))["id"]


@router.message(Ask.text, F.text)
async def ask_text(msg: Message, state: FSMContext):
    await state.clear()
    cid = await run(msg, coordinator_conversation(msg.chat.id))
    if cid is None:
        await msg.answer("Не нашли координатора для переписки. Напишите в «Сообщениях» на сайте.",
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


@router.message(Reply.text, F.text)
async def reply_text(msg: Message, state: FSMContext):
    cid = (await state.get_data()).get("cid")
    await state.clear()
    if await run(msg, platform.post(msg.chat.id, f"/conversations/{cid}/messages", {"text": msg.text[:4000]})) is not None:
        await msg.answer("Отправлено.")


def reply_kb(cid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Ответить", callback_data=PR(cid=cid).pack())]])


# --- «Как прошло?» -----------------------------------------------------------------------

MOODS = [("great", "😍 Отлично"), ("good", "🙂 Хорошо"), ("ok", "😐 Нормально"), ("hard", "😟 Было трудно")]
CONTINUE = [("yes", "Хочу продолжать"), ("pause", "Нужна пауза"), ("discuss", "Хочу обсудить"), ("finish", "Больше не смогу")]


def mood_kb(aid: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, label in MOODS:
        b.button(text=label, callback_data=PF(step="mood", aid=aid, val=key))
    b.adjust(2, 2)
    return b.as_markup()


@router.callback_query(PF.filter(F.step == "mood"))
async def after_mood(cb: CallbackQuery, callback_data: PF):
    uid, aid = cb.message.chat.id, callback_data.aid

    async def act():
        r = await platform.get(uid, f"/me/assignments/{aid}/reflection")
        if not r["can_submit"]:
            return None
        return await platform.put(uid, f"/me/assignments/{aid}/reflection", {"expected_version": r["version"], "mood": callback_data.val})

    await cb.answer()
    r = await run(cb.message, act())
    if r is None:
        return
    b = InlineKeyboardBuilder()
    for key, label in CONTINUE:
        b.button(text=label, callback_data=PF(step="cont", aid=aid, val=key))
    b.adjust(2, 2)
    await cb.message.answer("Спасибо! А дальше?", reply_markup=b.as_markup())


@router.callback_query(PF.filter(F.step == "cont"))
async def after_continue(cb: CallbackQuery, callback_data: PF):
    uid, aid = cb.message.chat.id, callback_data.aid

    async def act():
        r = await platform.put(uid, f"/me/assignments/{aid}/reflection",
                               {"expected_version": (await platform.get(uid, f"/me/assignments/{aid}/reflection"))["version"],
                                "continuation": callback_data.val})
        return await platform.post(uid, f"/me/assignments/{aid}/reflection/submit", {"expected_version": r["version"]})

    await cb.answer()
    if await run(cb.message, act()) is not None:
        await cb.message.answer("Ответ у координатора. Подробнее рассказать о выходе можно на сайте в разделе занятия.",
                                reply_markup=site_kb("Открыть на сайте", "/my/assignments"))


# --- Настройки ---------------------------------------------------------------------------

async def settings_view(uid: int) -> tuple[str, InlineKeyboardMarkup]:
    prefs = await platform.get(uid, "/me/notification-preferences")
    profile = await platform.get(uid, "/me/profile")
    news = bool(prefs["topics"].get("news"))
    quiet, paused = prefs["quiet_enabled"], profile["lifecycle"] == "paused"
    text = ("⚙️ <b>Настройки</b>\n"
            f"Новости фонда: {'да' if news else 'нет'}\n"
            f"Тихие часы ({prefs['quiet_from'] // 60}:00–{prefs['quiet_to'] // 60}:00): {'включены' if quiet else 'выключены'}\n"
            f"Пауза в приглашениях: {'да' if paused else 'нет'}\n\n"
            "Те же настройки — в профиле на сайте.")
    b = InlineKeyboardBuilder()
    b.button(text=("Не присылать новости" if news else "Присылать новости"), callback_data=PS(key="news"))
    b.button(text=("Выключить тихие часы" if quiet else "Включить тихие часы"), callback_data=PS(key="quiet"))
    b.button(text=("Снять паузу" if paused else "Взять паузу"), callback_data=PS(key="pause"))
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
            p = await platform.get(uid, "/me/profile")
            await platform.put(uid, "/me/profile", {"display_name": p["display_name"], "expected_version": p["version"],
                                                    "lifecycle": "active" if p["lifecycle"] == "paused" else "paused"})
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
