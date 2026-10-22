"""Координатор, когда бот подключён к платформе «Опора».

Вход: /coordinator → код из приложения-аутентификатора (как на сайте; на демо-стенде код не нужен). Дальше
та же клавиатура, что и без платформы — лента «Нужно решить», события, рассылки, новое событие, выгрузки, —
но всё читается и меняется на сайте через его API с правами этого сотрудника. Права проверяет сайт: если
у сотрудника нет доступа к разделу, бот так и скажет.

Лента — одно сообщение со списком: пункт открывается своей карточкой с кнопками, из карточки — обратно в ленту.
"""
import asyncio
import json
from datetime import date, datetime, timedelta
from html import escape

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.filters.callback_data import CallbackData
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import db, exports, platform, ui
from .config import TZ
from .platform import ApiFailure, NotLinked, PlatformError
from .pvolunteer import local, run, short, site_kb, when  # noqa: F401 — run нужен тестам и pjobs
from .schedule import human

router = Router(name="platform_coordinator")
router.message.filter(lambda _: platform.enabled(), F.chat.type == "private")
router.callback_query.filter(lambda _: platform.enabled(), F.message.chat.type == "private")
# Ввод в шагах диалога — любой текст, кроме команд: /start bind_… и /menu уходят своим обработчикам.
TEXT = F.text & ~F.text.startswith("/")

OUTCOMES = ["Подобрать первое занятие", "Обсудить подходящую роль", "Вернуться к разговору позже", "Не пришёл"]
REASON = "Решение координатора в Telegram"
ONLINE = {"онлайн", "online", "zoom", "зум", "дистанционно"}
SITE_DOWN = "Сайт фонда сейчас не отвечает. Попробуйте через пару минут."
EXPIRED = "Режим координатора выключился. Чтобы продолжить, отправьте /coordinator и код из приложения."
MONTHS_NOM = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]
MAX_BROADCAST = 500  # столько получателей сайт принимает в одной рассылке


class PC(CallbackData, prefix="pc"):
    action: str  # o (открыть пункт ленты), io (итог встречи), ans, req (ответить), rsp (отклик), asg, att
    id: str
    v: str = ""


class PE(CallbackData, prefix="pe"):
    action: str  # month, open, call, pick, send, cancel, cancel_yes, xls
    id: str = ""
    v: str = ""


class PB(CallbackData, prefix="pb"):
    step: str  # tpl, send
    id: str = ""


class PN(CallbackData, prefix="pn"):
    step: str  # role (once, weekly — только у старых кнопок)
    id: str = ""


class PX(CallbackData, prefix="px"):
    kind: str  # volunteers, teams


class Code(StatesGroup):
    text = State()


class Answer(StatesGroup):
    text = State()


class NewEvent(StatesGroup):
    title = State()
    day = State()
    time = State()
    place = State()
    need = State()


def feed_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="← К ленте", callback_data=ui.MenuCB(item="feed").pack())


def back_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[feed_button()]])


# --- вход и права ---------------------------------------------------------------------------

async def enter(msg: Message, code: str, state: FSMContext) -> None:
    uid = msg.chat.id
    try:
        res = await platform.coordinator(uid, code)
    except NotLinked:
        await msg.answer("Сначала подключите Telegram в своём профиле на сайте, потом снова отправьте /coordinator.",
                         reply_markup=site_kb("Открыть профиль", "/profile"))
        return
    except ApiFailure as e:
        if e.code == "mfa_invalid" and not code:
            await state.set_state(Code.text)
            await msg.answer("🔐 Введите 6 цифр из приложения-аутентификатора, как при входе на сайт.", reply_markup=ui.cancel_kb())
        elif e.code == "mfa_invalid":
            await state.set_state(Code.text)
            await msg.answer("Код не подошёл. Введите новый из приложения.", reply_markup=ui.cancel_kb())
        elif e.code == "staff_required":
            await msg.answer("Этот профиль на сайте не сотрудник фонда, режим координатора недоступен.")
        elif e.code == "mfa_enrollment_required":
            await msg.answer("Сначала включите вход по коду в профиле сотрудника на сайте, потом снова отправьте /coordinator.")
        else:
            await msg.answer(e.message or "Сайт не пустил в режим координатора.")
        return
    except PlatformError:
        await msg.answer(SITE_DOWN)
        return
    if not res or not res.get("is_staff"):
        await msg.answer("Сайт не выдал права координатора.")
        return
    await state.clear()
    u = db.ensure_user(uid, msg.from_user.username if msg.from_user else None)
    p = db.prefs(u)
    p["mode"] = "coord"
    db.update_user(uid, is_coordinator=1, prefs=json.dumps(p))
    await ui.send_menu(msg, db.user(uid), "✅ Вы вошли как координатор. Всё, что вы здесь делаете, сразу видно на сайте.\n\n"
                       + ui.menu_text(db.user(uid)))


@router.message(Command("coordinator"))
async def login(msg: Message, command: CommandObject, state: FSMContext):
    db.ensure_user(msg.chat.id, msg.from_user.username)
    await enter(msg, (command.args or "").strip(), state)


@router.message(Code.text, TEXT)
async def login_code(msg: Message, state: FSMContext):
    await enter(msg, msg.text.strip().replace(" ", ""), state)


def error_text(e: ApiFailure, uid: int) -> str:
    if e.status == 403:
        return EXPIRED if not platform.is_staff(uid) else "У вашего профиля на сайте нет доступа к этому разделу."
    if e.code == "version_conflict" or (e.status == 409 and not e.message):
        return "Пока вы смотрели, на сайте что-то поменялось. Откройте ещё раз."
    return e.message or "Сайт не принял действие."


async def staff_call(target: Message, coro):
    """Как run(), но без прав координатора объясняет, что делать."""
    try:
        return await coro
    except ApiFailure as e:
        await target.answer(error_text(e, target.chat.id))
    except NotLinked:
        platform.forget(target.chat.id)
        db.update_user(target.chat.id, status="new", is_coordinator=0)
        await target.answer("Telegram больше не подключён к вашему профилю. Подключите его снова в профиле на сайте.",
                            reply_markup=site_kb("Открыть профиль", "/profile"))
    except PlatformError:
        await target.answer(SITE_DOWN)
    return None


async def optional(uid: int, path: str, **params):
    """Раздел ленты: нет прав на него — просто не показываем."""
    try:
        return await platform.get(uid, path, **params)
    except ApiFailure as e:
        if e.status == 403 and platform.is_staff(uid):
            return None
        raise


# --- лента «Нужно решить» ---------------------------------------------------------------------

async def collect(uid: int) -> dict:
    now = db.now()
    interviews, signals, requests, responses, candidates, hours = await asyncio.gather(
        optional(uid, "/coord/interviews"), optional(uid, "/coord/signals", state="open", limit=50),
        optional(uid, "/coord/candidate-requests"), optional(uid, "/coord/responses", limit=100),
        optional(uid, "/coord/candidates", review_state="new", limit=5), optional(uid, "/coord/hours/requests"))
    me = (db.user(uid) or {"site_id": ""})["site_id"]
    # свои собеседования: о чужих встречах спрашивать «как прошло» незачем
    mine = [m for m in interviews or [] if m["status"] == "booked" and m.get("coordinator_id") in (None, me)]
    return {
        "outcome": [m for m in mine if local(m["ends_at"]) <= now][:5],
        "upcoming": [m for m in mine if now < local(m["starts_at"]) <= now + timedelta(days=2)],
        "questions": [s for s in (signals or {"items": []})["items"] if s.get("question_id")][:5],
        "requests": [r for r in (requests or []) if r["state"] not in ("resolved", "closed", "answered")][:5],
        "responses": [r for r in (responses or {"items": []})["items"] if "approve" in r["allowed_actions"]][:5],
        "candidates": candidates or {"items": [], "total": 0},
        "hours": [h for h in (hours or []) if h["state"] in ("pending", "submitted")],
    }


def todo_count(d: dict) -> int:
    return len(d["outcome"]) + len(d["questions"]) + len(d["requests"]) + len(d["responses"])


def remember_todo(uid: int, n: int) -> None:
    u = db.user(uid)
    if u:
        p = db.prefs(u)
        p["todo"] = n
        db.update_user(uid, prefs=json.dumps(p))


_feed: dict[int, dict[str, tuple[str, dict]]] = {}  # координатор → пункты последней показанной ленты: id → (вид, данные)


def item_label(kind: str, x: dict) -> str:
    return short({"io": f"🤝 Как прошла встреча: {x.get('candidate_name', '')}",
                  "ans": f"❓ {x.get('display_name', '')}: {x.get('summary', '')}",
                  "req": f"✉️ Обращение: {x.get('text', '')}",
                  "rsp": f"🙋 {x.get('display_name', '')}: {x.get('opportunity_title', '')}"}[kind], 60)


async def feed(msg: Message, state: FSMContext | None = None) -> None:
    uid = msg.chat.id
    if state:
        await state.clear()
    d = await staff_call(msg, collect(uid))
    if d is None:
        return
    items = ([("io", m) for m in d["outcome"]] + [("ans", s) for s in d["questions"]]
             + [("req", r) for r in d["requests"]] + [("rsp", r) for r in d["responses"]])
    _feed[uid] = {x["id"]: (kind, x) for kind, x in items}
    remember_todo(uid, len(items))
    lines = [f"🔔 <b>Нужно решить: {len(items)}</b>" if items else "🔔 <b>Нужно решить: ничего</b>\nВсё разобрано."]
    if items:
        lines.append("Нажмите на пункт, чтобы ответить.")
    if d["upcoming"]:
        lines.append("\n<b>Ближайшие собеседования</b>")
        lines += [f"{escape(m['candidate_name'])}, {when(m['starts_at'], m['ends_at'])}, {escape(m['venue'] or 'онлайн')}"
                  for m in d["upcoming"]]
    extra = ([f"новых анкет: {d['candidates']['total']}"] if d["candidates"]["total"] else []) \
        + ([f"заявок на часы: {len(d['hours'])}"] if d["hours"] else [])
    if extra:
        lines.append("\nНа сайте ждут: " + ", ".join(extra) + ".")
    b = InlineKeyboardBuilder()
    for kind, x in items:
        b.button(text=item_label(kind, x), callback_data=PC(action="o", id=x["id"]))
    b.button(text="Кандидаты на сайте", url=platform.site("/fund/candidates"))
    b.adjust(1)
    await msg.answer("\n".join(lines), reply_markup=b.as_markup())


def card_view(kind: str, x: dict) -> tuple[str, InlineKeyboardMarkup]:
    b = InlineKeyboardBuilder()
    if kind == "io":
        text = f"🤝 Как прошло собеседование?\n<b>{escape(x['candidate_name'])}</b>, {when(x['starts_at'], x['ends_at'])}"
        for i, label in enumerate(OUTCOMES):
            b.button(text=label, callback_data=PC(action="io", id=x["id"], v=str(i)))
    elif kind == "ans":
        text = f"❓ <b>{escape(x['display_name'])}</b>\n{escape(x['summary'])}" + (f"\n\n{escape(short(x['details'], 3000))}" if x.get("details") else "")
        b.button(text="Ответить", callback_data=PC(action="ans", id=x["id"]))
    elif kind == "req":
        text = f"✉️ <b>Обращение кандидата</b>\n\n{escape(short(x['text'], 3500))}"
        b.button(text="Ответить", callback_data=PC(action="req", id=x["id"]))
    else:
        text = f"🙋 <b>{escape(x['display_name'])}</b> хочет участвовать: {escape(x['opportunity_title'])}"
        b.button(text="Одобрить", callback_data=PC(action="rsp", id=x["id"], v="a"))
        b.button(text="Отклонить", callback_data=PC(action="rsp", id=x["id"], v="d"))
    b.adjust(1 if kind == "io" else 2)
    b.row(feed_button())
    return text, b.as_markup()


@router.callback_query(PC.filter(F.action == "o"))
async def open_item(cb: CallbackQuery, callback_data: PC):
    await cb.answer()
    hit = _feed.get(cb.message.chat.id, {}).get(callback_data.id)
    if not hit:
        await cb.message.answer("Лента обновилась, откройте её ещё раз.", reply_markup=back_kb())
        return
    text, kb = card_view(*hit)
    await cb.message.answer(text, reply_markup=kb)


async def done(cb: CallbackQuery, note: str) -> None:
    """Итог действия дописываем в карточку и убираем её кнопки, кроме «К ленте»."""
    _feed.get(cb.message.chat.id, {}).pop(cb.data.split(":")[2] if cb.data.count(":") >= 2 else "", None)
    try:
        await cb.message.edit_text(cb.message.html_text + "\n\n" + note, reply_markup=back_kb())
    except Exception:  # noqa: BLE001 — сообщение старое
        await cb.message.answer(note, reply_markup=back_kb())


@router.callback_query(PC.filter(F.action == "io"))
async def interview_outcome(cb: CallbackQuery, callback_data: PC):
    uid, outcome = cb.message.chat.id, OUTCOMES[int(callback_data.v)]

    async def act():
        m = next((x for x in await platform.get(uid, "/coord/interviews") if x["id"] == callback_data.id), None)
        if not m or m["status"] != "booked":
            return "done"
        path = "mark-missed" if outcome == "Не пришёл" else "complete"
        return await platform.post(uid, f"/interviews/{m['id']}/{path}",
                                   {"expected_version": m["version"], "outcome": outcome, "public_agreement": outcome})

    await cb.answer()
    res = await staff_call(cb.message, act())
    if res == "done":
        await done(cb, "Итог уже записан.")
    elif res:
        await done(cb, f"✅ Записали: {escape(outcome)}. Это видно в карточке кандидата на сайте.")


@router.callback_query(PC.filter(F.action.in_({"ans", "req"})))
async def answer_start(cb: CallbackQuery, callback_data: PC, state: FSMContext):
    await state.set_state(Answer.text)
    await state.update_data(kind=callback_data.action, id=callback_data.id)
    await cb.message.answer("Напишите ответ одним сообщением.", reply_markup=ui.cancel_kb())
    await cb.answer()


@router.message(Answer.text, TEXT)
async def answer_send(msg: Message, state: FSMContext):
    uid, data = msg.chat.id, await state.get_data()
    await state.clear()

    async def act():
        if data["kind"] == "ans":
            s = await platform.get(uid, f"/coord/signals/{data['id']}")
            return await platform.post(uid, f"/coord/assignment-questions/{s['question_id']}/answer",
                                       {"expected_version": s["question_version"], "public_answer": msg.text[:6000]})
        r = next((x for x in await platform.get(uid, "/coord/candidate-requests") if x["id"] == data["id"]), None)
        if r is None:
            return "gone"
        return await platform.post(uid, f"/coord/candidate-requests/{r['id']}/respond",
                                   {"expected_version": r["version"], "text": msg.text[:4000]})

    res = await staff_call(msg, act())
    if res == "gone":
        await msg.answer("Это обращение уже закрыто.", reply_markup=back_kb())
    elif res:
        _feed.get(uid, {}).pop(data["id"], None)
        await msg.answer("Ответ отправлен.", reply_markup=back_kb())


async def find_response(uid: int, rid: str) -> dict | None:
    """Отклик по id: список на сайте постраничный, просматриваем до пяти страниц."""
    cursor = None
    for _ in range(5):
        page = await platform.get(uid, "/coord/responses", limit=100, cursor=cursor)
        hit = next((x for x in page["items"] if x["id"] == rid), None)
        cursor = page.get("next_cursor")
        if hit or not cursor:
            return hit
    return None


@router.callback_query(PC.filter(F.action == "rsp"))
async def response_decision(cb: CallbackQuery, callback_data: PC):
    uid = cb.message.chat.id

    async def act():
        r = await find_response(uid, callback_data.id)
        if not r or "approve" not in r["allowed_actions"]:
            return "gone"
        verb = "approve" if callback_data.v == "a" else "decline"
        return await platform.post(uid, f"/coord/responses/{r['id']}/{verb}", {"expected_version": r["version"], "reason": REASON})

    await cb.answer()
    res = await staff_call(cb.message, act())
    if res == "gone":
        await done(cb, "По этому отклику уже приняли решение.")
    elif res:
        await done(cb, "✅ Одобрено." if callback_data.v == "a" else "Отклонено.")


# --- события ----------------------------------------------------------------------------------

async def occurrences(uid: int, days: int = 45) -> list[dict]:
    today, items, cursor = db.now().date(), [], None
    while True:
        page = await platform.get(uid, "/event-occurrences", **{"from": today.isoformat(), "to": (today + timedelta(days=days)).isoformat(),
                                                                "timezone": str(TZ), "limit": 100, "cursor": cursor})
        items += page["items"]
        cursor = page.get("next_cursor")
        if not cursor:
            return sorted(items, key=lambda o: o["starts_at"])


def coverage(o: dict) -> str:
    need = sum(n["required"] for n in o["staffing_needs"])
    return f"{sum(n['confirmed'] for n in o['staffing_needs'])} из {need}" if need else "без волонтёров"


async def events_list(msg: Message, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    items = await staff_call(msg, occurrences(msg.chat.id))
    if items is None:
        return
    months: dict[str, list] = {}
    for o in items:
        if o["status"] == "scheduled":
            months.setdefault(local(o["starts_at"]).strftime("%Y%m"), []).append(o)
    b = InlineKeyboardBuilder()
    for key, rows in months.items():
        lacking = sum(1 for o in rows if any(n["missing"] for n in o["staffing_needs"]))
        b.button(text=f"{MONTHS_NOM[int(key[4:]) - 1]}: {len(rows)}" + (f", не хватает людей в {lacking}" if lacking else ""),
                 callback_data=PE(action="month", v=key))
    b.row(InlineKeyboardButton(text="Расписание на сайте", url=platform.site("/fund/schedule")))
    b.adjust(1)
    await msg.answer("🗓 <b>События на 45 дней</b>" + ("" if months else "\nЗапланированных событий нет."), reply_markup=b.as_markup())


@router.callback_query(PE.filter(F.action == "month"))
async def month(cb: CallbackQuery, callback_data: PE):
    await cb.answer()
    items = await staff_call(cb.message, occurrences(cb.message.chat.id))
    if items is None:
        return
    rows = [o for o in items if o["status"] == "scheduled" and local(o["starts_at"]).strftime("%Y%m") == callback_data.v]
    b = InlineKeyboardBuilder()
    for o in rows[:40]:
        s = local(o["starts_at"])
        b.button(text=short(f"{s:%d.%m %H:%M} {o['title']}, {coverage(o)}", 60), callback_data=PE(action="open", id=o["id"]))
    if len(rows) > 40:
        b.button(text=f"Ещё {len(rows) - 40} — на сайте", url=platform.site("/fund/schedule"))
    b.adjust(1)
    await cb.message.answer(f"🗓 <b>{MONTHS_NOM[int(callback_data.v[4:]) - 1]}</b>", reply_markup=b.as_markup())


STATUS_TEAM = {"invited": "ждём ответа", "confirmed": "идёт", "declined": "отказ", "cancelled": "отменено", "expired": "без ответа"}
ATTENDANCE = {"attended": "участие отмечено", "absent": "отмечен пропуск"}
TEAM_LINES = 30


def first_name(name: str) -> str:
    return short(name, 22)


async def occurrence_view(uid: int, oid: str):
    o = await platform.get(uid, f"/event-occurrences/{oid}")
    team = (await platform.get(uid, "/coord/assignments", occurrence_id=oid, limit=100))["items"]
    lines = [f"<b>{escape(o['title'])}</b>", when(o["starts_at"], o["ends_at"]), escape(o["location"] or "место уточним")]
    if o["status"] != "scheduled":
        lines.append("❗️ Отменено" if o["status"] == "cancelled" else "Уже прошло")
    rows: list[list[InlineKeyboardButton]] = []
    for n in o["staffing_needs"]:
        lines.append(f"\n👥 {escape(n['role_title'])}: {n['confirmed']} из {n['required']}, приглашено {n['invited']}")
        if o["status"] == "scheduled" and n["missing"]:
            rows.append([InlineKeyboardButton(text=short(f"Позвать: {n['role_title']}", 40), callback_data=PE(action="call", id=n["id"]).pack())])
    marking = [a for a in team if "attendance" in a["allowed_actions"]]
    if team:
        lines.append("\n🙌 <b>Команда</b>")
        for a in team[:TEAM_LINES]:
            att = f", {ATTENDANCE[a['attendance']['outcome']]}" if a.get("attendance") else ""
            lines.append(f"{escape(a['display_name'])}, {escape(a['role_title'])}: {STATUS_TEAM.get(a['status'], a['status'])}{att}")
        if len(team) > TEAM_LINES:
            lines.append(f"И ещё {len(team) - TEAM_LINES} — на сайте.")
        if marking:
            lines.append("\nОтметьте участие: ✅ был на занятии, 🚫 не было.")
    for a in team:
        if "approve" in a["allowed_actions"] and a["status"] == "invited":
            rows.append([InlineKeyboardButton(text=short(f"Подтвердить: {a['display_name']}", 40),
                                              callback_data=PC(action="asg", id=a["id"]).pack())])
    for a in marking[:TEAM_LINES]:  # одна строка на человека, а не две
        rows.append([InlineKeyboardButton(text=f"✅ {first_name(a['display_name'])}", callback_data=PC(action="att", id=a["id"], v="y").pack()),
                     InlineKeyboardButton(text=f"🚫 {first_name(a['display_name'])}", callback_data=PC(action="att", id=a["id"], v="n").pack())])
    if "cancel" in o["allowed_actions"]:
        rows.append([InlineKeyboardButton(text="Отменить эту дату", callback_data=PE(action="cancel", id=oid).pack())])
    tail = [InlineKeyboardButton(text="На сайте", url=platform.site("/fund/schedule"))]
    if team:
        tail.insert(0, InlineKeyboardButton(text="📊 Команда в Excel", callback_data=PE(action="xls", id=oid).pack()))
    rows.append(tail)
    return short("\n".join(lines), 4000), InlineKeyboardMarkup(inline_keyboard=rows)


@router.callback_query(PE.filter(F.action == "open"))
async def open_event(cb: CallbackQuery, callback_data: PE, state: FSMContext):
    await cb.answer()
    await state.update_data(occurrence=callback_data.id)  # «Позвать людей» берёт версию потребности из этого события
    res = await staff_call(cb.message, occurrence_view(cb.message.chat.id, callback_data.id))
    if res:
        await cb.message.answer(res[0], reply_markup=res[1])


@router.callback_query(PC.filter(F.action.in_({"asg", "att"})))
async def team_action(cb: CallbackQuery, callback_data: PC):
    uid, aid = cb.message.chat.id, callback_data.id

    async def act():
        a = await platform.get(uid, f"/assignments/{aid}")
        if callback_data.action == "asg":
            return await platform.post(uid, f"/coord/assignments/{aid}/approve", {"expected_version": a["version"], "reason": REASON})
        minutes = max(0, int((local(a["ends_at"]) - local(a["starts_at"])).total_seconds() // 60)) if callback_data.v == "y" else 0
        return await platform.post(uid, f"/coord/assignments/{aid}/attendance",
                                   {"expected_version": a["version"], "outcome": "attended" if callback_data.v == "y" else "absent",
                                    "minutes": minutes, "reason": REASON})

    await cb.answer()
    a = await staff_call(cb.message, act())
    if a:
        note = ("участие подтверждено, приглашение ушло" if callback_data.action == "asg" else
                "участие отмечено, часы начислены" if callback_data.v == "y" else "отмечен пропуск")
        await cb.message.answer(f"Готово: {escape(a['display_name'])}, {note}.")


@router.callback_query(PE.filter(F.action == "call"))
async def call_people(cb: CallbackQuery, callback_data: PE, state: FSMContext):
    await cb.answer()
    rows = await staff_call(cb.message, platform.get(cb.message.chat.id, f"/coord/staffing-needs/{callback_data.id}/suggestions"))
    if rows is None:
        return
    rows = [r for r in rows if r.get("invitation_status") not in ("invited", "confirmed")]  # этих уже позвали
    if not rows:
        await cb.message.answer("Сейчас некого позвать. Сайт не предлагает тех, кто ещё не прошёл собеседование, "
                                "на паузе или просил не беспокоить. Пригласить вручную можно на сайте.",
                                reply_markup=site_kb("Расписание на сайте", "/fund/schedule"))
        return
    if "occurrence" not in await state.get_data():
        await cb.message.answer("Откройте событие заново.")
        return
    await state.update_data(need=callback_data.id, people=[{"id": r["user_id"], "name": r["display_name"],
                                                            "why": ", ".join(r["reasons"][:2])} for r in rows[:15]], picked=[])
    await cb.message.answer("Кого позвать? Отметьте людей и нажмите «Пригласить».", reply_markup=pick_kb(await state.get_data()))


def pick_kb(data: dict) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for i, p in enumerate(data["people"]):
        mark = "✅ " if i in data["picked"] else ""
        b.button(text=short(f"{mark}{p['name']}" + (f", {p['why']}" if p["why"] else ""), 60), callback_data=PE(action="pick", v=str(i)))
    if data["picked"]:
        b.button(text=f"Пригласить ({len(data['picked'])})", callback_data=PE(action="send"))
    b.adjust(1)
    return b.as_markup()


@router.callback_query(PE.filter(F.action == "pick"))
async def pick(cb: CallbackQuery, callback_data: PE, state: FSMContext):
    data = await state.get_data()
    if not data.get("people"):
        await cb.answer("Список устарел, откройте событие снова.")
        return
    i = int(callback_data.v)
    data["picked"] = [x for x in data["picked"] if x != i] if i in data["picked"] else data["picked"] + [i]
    await state.update_data(picked=data["picked"])
    await cb.message.edit_reply_markup(reply_markup=pick_kb(data))
    await cb.answer()


@router.callback_query(PE.filter(F.action == "send"))
async def send_invites(cb: CallbackQuery, state: FSMContext):
    uid, data = cb.message.chat.id, await state.get_data()
    await state.update_data(picked=[], people=[])
    await cb.answer()
    if not data.get("picked") or "need" not in data:
        await cb.message.answer("Список устарел, откройте событие снова.")
        return
    sent, failed = [], []
    for i in data["picked"]:
        person = data["people"][i]
        try:
            needs = await platform.get(uid, f"/coord/event-occurrences/{data['occurrence']}/staffing-needs")
            need = next((n for n in needs if n["id"] == data["need"]), None)  # после каждого приглашения версия растёт
            if need is None:
                failed.append(f"{person['name']} (откройте событие заново)")
                continue
            await platform.post(uid, f"/coord/staffing-needs/{data['need']}/invitations",
                                {"expected_version": need["version"], "user_id": person["id"]})
            sent.append(person["name"])
        except ApiFailure as e:
            failed.append(f"{person['name']} ({error_text(e, uid).rstrip('.')})")
        except PlatformError:
            failed.append(f"{person['name']} (сайт не ответил)")
    text = ("Приглашения отправлены: " + ", ".join(escape(x) for x in sent) + ". Кто подключил Telegram, получит их здесь, "
            "остальные увидят на сайте.") if sent else ""
    if failed:
        text += ("\n\n" if text else "") + "Не получилось: " + "; ".join(escape(x) for x in failed) + "."
    await cb.message.answer(text)


@router.callback_query(PE.filter(F.action == "cancel"))
async def cancel_ask(cb: CallbackQuery, callback_data: PE):
    b = InlineKeyboardBuilder()
    b.button(text="Да, отменить дату", callback_data=PE(action="cancel_yes", id=callback_data.id))
    b.button(text="Нет", callback_data=ui.MenuCB(item="home"))
    await cb.message.answer("Отменить эту дату? Участники увидят отмену.", reply_markup=b.as_markup())
    await cb.answer()


@router.callback_query(PE.filter(F.action == "cancel_yes"))
async def cancel_event(cb: CallbackQuery, callback_data: PE):
    uid = cb.message.chat.id

    async def act():
        o = await platform.get(uid, f"/event-occurrences/{callback_data.id}")
        return await platform.post(uid, f"/coord/event-occurrences/{o['id']}/cancel", {"expected_version": o["version"]})

    await cb.answer()
    if await staff_call(cb.message, act()):
        await cb.message.answer("Дата отменена. Вернуть её можно в расписании на сайте.")


@router.callback_query(PE.filter(F.action == "xls"))
async def team_excel(cb: CallbackQuery, callback_data: PE):
    uid = cb.message.chat.id
    await cb.answer()

    async def act():
        o = await platform.get(uid, f"/event-occurrences/{callback_data.id}")
        team = (await platform.get(uid, "/coord/assignments", occurrence_id=o["id"], limit=100))["items"]
        return o, team

    res = await staff_call(cb.message, act())
    if not res:
        return
    o, team = res
    data = exports._book(o["title"], ["Имя", "Роль", "Статус", "Участие"],
                         [[a["display_name"], a["role_title"], STATUS_TEAM.get(a["status"], a["status"]),
                           (ATTENDANCE.get(a["attendance"]["outcome"], "") if a.get("attendance") else "")] for a in team])
    await cb.message.answer_document(BufferedInputFile(data, filename=f"team-{local(o['starts_at']):%Y-%m-%d}.xlsx"))


# --- новое событие ------------------------------------------------------------------------------

async def new_event(msg: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(NewEvent.title)
    await msg.answer("✨ <b>Новое событие</b>\nКак назовём? Например: Арт-суббота", reply_markup=ui.cancel_kb())


@router.message(NewEvent.title, TEXT)
async def ne_title(msg: Message, state: FSMContext):
    await state.update_data(title=msg.text.strip()[:200])
    await state.set_state(NewEvent.day)
    await msg.answer("Какого числа? Например: 25.10", reply_markup=ui.cancel_kb())


def parse_day(text: str) -> date | None:
    try:
        parts = [int(x) for x in text.strip().replace("/", ".").split(".") if x]
        today = db.now().date()
        year = parts[2] if len(parts) > 2 else today.year
        day = date(year + (2000 if year < 100 else 0), parts[1], parts[0])
        return day if day >= today else (day.replace(year=day.year + 1) if len(parts) == 2 else None)
    except (ValueError, IndexError):
        return None


@router.message(NewEvent.day, TEXT)
async def ne_day(msg: Message, state: FSMContext):
    day = parse_day(msg.text)
    if not day:
        await msg.answer("Не поняли дату. Напишите так: 25.10 или 25.10.2026", reply_markup=ui.cancel_kb())
        return
    await state.update_data(day=day.isoformat())
    await state.set_state(NewEvent.time)
    await msg.answer(f"{human(day)}. Во сколько? Например: 11:00-14:00", reply_markup=ui.cancel_kb())


@router.message(NewEvent.time, TEXT)
async def ne_time(msg: Message, state: FSMContext):
    try:
        a, b = [datetime.strptime(x.strip(), "%H:%M") for x in msg.text.replace("—", "-").replace("–", "-").split("-")]
        minutes = int((b - a).total_seconds() // 60)
        assert minutes > 0
    except (ValueError, AssertionError):
        await msg.answer("Напишите время начала и конца, например: 11:00-14:00", reply_markup=ui.cancel_kb())
        return
    await state.update_data(time=a.strftime("%H:%M"), minutes=minutes)
    await state.set_state(NewEvent.place)
    await msg.answer("Где? Адрес или «онлайн».", reply_markup=ui.cancel_kb())


@router.message(NewEvent.place, TEXT)
async def ne_place(msg: Message, state: FSMContext):
    await state.update_data(place=msg.text.strip()[:300])
    roles = await staff_call(msg, platform.get(msg.chat.id, "/coord/roles", limit=50))
    if roles is None:
        await state.clear()
        return
    b = InlineKeyboardBuilder()
    for r in roles["items"][:20]:
        b.button(text=short(r["title"], 40), callback_data=PN(step="role", id=r["id"]))
    b.button(text="Волонтёры не нужны", callback_data=PN(step="role"))
    b.adjust(1)
    await msg.answer("Какая роль нужна?", reply_markup=b.as_markup())


@router.callback_query(PN.filter(F.step == "role"))
async def ne_role(cb: CallbackQuery, callback_data: PN, state: FSMContext):
    await state.update_data(role=callback_data.id)
    await cb.answer()
    if callback_data.id:
        await state.set_state(NewEvent.need)
        await cb.message.answer("Сколько волонтёров нужно? Напишите число.", reply_markup=ui.cancel_kb())
    else:
        await save_event(cb.message, state)


@router.message(NewEvent.need, TEXT)
async def ne_need(msg: Message, state: FSMContext):
    if not msg.text.strip().isdigit() or not 0 < int(msg.text.strip()) <= 50:
        await msg.answer("Напишите число от 1 до 50.", reply_markup=ui.cancel_kb())
        return
    await state.update_data(need=int(msg.text.strip()))
    await save_event(msg, state)


async def save_event(target: Message, state: FSMContext) -> None:
    """Событие на одну дату: в боте его можно создать за минуту. Повтор по неделям настраивается на сайте."""
    data = await state.get_data()
    await state.clear()
    if "title" not in data:
        await target.answer("Черновик события потерялся, начните заново.")
        return
    body = {"title": data["title"], "start_date": data["day"], "start_time": data["time"], "duration_minutes": data["minutes"],
            "location": data["place"], "timezone": str(TZ),
            "format": "online" if data["place"].strip().lower() in ONLINE else "onsite",
            "recurrence": {"frequency": "once", "weekdays": []},
            "staffing_needs": [{"role_id": data["role"], "capacity_required": data.get("need", 1)}] if data.get("role") else []}
    o = await staff_call(target, platform.post(target.chat.id, "/coord/event-occurrences", body))
    if o:
        b = InlineKeyboardBuilder()
        b.button(text="Открыть событие", callback_data=PE(action="open", id=o["id"]))
        b.button(text="Повторять: на сайте", url=platform.site("/fund/schedule"))
        b.adjust(1)
        await target.answer(f"✅ Событие создано: <b>{escape(o['title'])}</b>, {when(o['starts_at'], o['ends_at'])}.",
                            reply_markup=b.as_markup())


@router.callback_query(PN.filter(F.step.in_({"once", "weekly"})))
async def ne_old_buttons(cb: CallbackQuery):
    await cb.answer()
    await cb.message.answer("Этот черновик устарел. Начните новое событие из меню.")


# --- рассылки (шаблоны сайта) ---------------------------------------------------------------------

async def broadcasts(msg: Message, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    rows = await staff_call(msg, platform.get(msg.chat.id, "/coord/notification-templates"))
    if rows is None:
        return
    ready = [t for t in rows["items"] if t.get("published_version_id")]
    b = InlineKeyboardBuilder()
    for t in ready[:15]:
        b.button(text=short(t["subject"] or t["key"], 50), callback_data=PB(step="tpl", id=t["id"]))
    b.row(InlineKeyboardButton(text="Шаблоны на сайте", url=platform.site("/fund/notifications")))
    b.adjust(1)
    await msg.answer("📣 <b>Рассылки</b>\nВыберите утверждённый шаблон. Сначала покажем, сколько человек его получат."
                     if ready else "📣 Утверждённых шаблонов пока нет. Создать и утвердить шаблон можно на сайте.",
                     reply_markup=b.as_markup())


async def all_recipients(uid: int) -> list[str]:
    ids, cursor = [], None
    while len(ids) <= MAX_BROADCAST:
        page = await platform.get(uid, "/coord/notifications/recipients", limit=100, cursor=cursor)
        ids += [r["id"] for r in page["items"]]
        cursor = page.get("next_cursor")
        if not cursor:
            break
    return ids


@router.callback_query(PB.filter(F.step == "tpl"))
async def bc_preview(cb: CallbackQuery, callback_data: PB, state: FSMContext):
    uid = cb.message.chat.id
    await cb.answer()

    async def act():
        tpl = next((t for t in (await platform.get(uid, "/coord/notification-templates"))["items"] if t["id"] == callback_data.id), None)
        if tpl is None or not tpl.get("published_version_id"):
            return "gone"
        ids = await all_recipients(uid)
        if len(ids) > MAX_BROADCAST:
            return "big"
        preview = await platform.post(uid, "/coord/notifications/audience-preview",
                                      {"recipient_user_ids": ids, "template_version_id": tpl["published_version_id"]})
        return tpl, preview

    res = await staff_call(cb.message, act())
    if res == "gone":
        await cb.message.answer("Этот шаблон изменили или сняли с публикации. Откройте рассылки заново.")
        return
    if res == "big":
        await cb.message.answer(f"Получателей больше {MAX_BROADCAST}: такую рассылку отправьте с сайта, там можно выбрать аудиторию.",
                                reply_markup=site_kb("Рассылки на сайте", "/fund/notifications"))
        return
    if not res:
        return
    tpl, preview = res
    await state.update_data(preview_id=preview["id"], preview_hash=preview["preview_hash"])
    b = InlineKeyboardBuilder()
    if preview["eligible_count"]:
        b.button(text=f"Отправить ({preview['eligible_count']})", callback_data=PB(step="send"))
    b.button(text="Отмена", callback_data=ui.MenuCB(item="home"))
    b.adjust(1)
    await cb.message.answer(short(f"<b>{escape(tpl['subject'])}</b>\n{escape(tpl['body'])}", 3500)
                            + f"\n\nПолучат {preview['eligible_count']} из {len(preview['members'])}. "
                            "Остальные отказались от таких сообщений или сейчас недоступны.", reply_markup=b.as_markup())


@router.callback_query(PB.filter(F.step == "send"))
async def bc_send(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    await cb.answer()
    if "preview_id" not in data:
        await cb.message.answer("Предпросмотр устарел, выберите шаблон снова.")
        return
    res = await staff_call(cb.message, platform.post(cb.message.chat.id, "/coord/notifications/send",
                                                     {"preview_id": data["preview_id"], "preview_hash": data["preview_hash"], "confirmed": True}))
    if res:
        try:
            await cb.message.edit_reply_markup(reply_markup=None)  # второй раз ту же рассылку не нажать
        except Exception:  # noqa: BLE001
            pass
        await cb.message.answer(f"Рассылка ушла: {res['enqueued']} получателей. Как доставлено, видно на сайте в журнале уведомлений.")


# --- выгрузки ------------------------------------------------------------------------------------

async def exports_menu(msg: Message, state: FSMContext | None = None) -> None:
    if state:
        await state.clear()
    b = InlineKeyboardBuilder()
    b.button(text="Волонтёры", callback_data=PX(kind="volunteers"))
    b.button(text="Команды на 2 недели", callback_data=PX(kind="teams"))
    b.adjust(1)
    await msg.answer("📊 <b>Выгрузки в Excel</b>\nДанные с сайта на эту минуту.", reply_markup=b.as_markup())


@router.callback_query(PX.filter())
async def export(cb: CallbackQuery, callback_data: PX):
    uid = cb.message.chat.id
    await cb.answer("Готовим файл…")

    async def volunteers():
        rows, offset = [], 0
        while True:
            page = await platform.get(uid, "/coord/volunteers", offset=offset, limit=100)
            rows += page["items"]
            offset += len(page["items"])
            if not page["items"] or offset >= page["total"]:
                break
        return exports._book("Волонтёры", ["Имя", "Состояние", "Почта", "Телефон", "Когда удобно", "Не беспокоить"],
                             [[v["display_name"], v["relationship_state"], v["contacts"].get("email", ""), v["contacts"].get("phone", ""),
                               (v["availability"] or {}).get("summary", ""), "да" if v["no_contact"] else ""] for v in rows])

    async def teams():
        out = []
        for o in await occurrences(uid, 14):
            if o["status"] != "scheduled":
                continue
            team = (await platform.get(uid, "/coord/assignments", occurrence_id=o["id"], limit=100))["items"]
            s = local(o["starts_at"])
            out += [[f"{s:%d.%m.%Y %H:%M}", o["title"], a["display_name"], a["role_title"], STATUS_TEAM.get(a["status"], a["status"])] for a in team] \
                or [[f"{s:%d.%m.%Y %H:%M}", o["title"], "никого", "", coverage(o)]]
        return exports._book("Команды", ["Когда", "Событие", "Волонтёр", "Роль", "Статус"], out)

    data = await staff_call(cb.message, volunteers() if callback_data.kind == "volunteers" else teams())
    if data:
        await cb.message.answer_document(BufferedInputFile(data, filename=f"{callback_data.kind}-{db.now():%Y-%m-%d}.xlsx"))


ITEMS = {
    "feed": lambda m, s: feed(m, s),
    "events": lambda m, s: events_list(m, s),
    "broadcasts": lambda m, s: broadcasts(m, s),
    "new_event": lambda m, s: new_event(m, s),
    "exports": lambda m, s: exports_menu(m, s),
}


@router.message(F.text == ui.BTN_FEED)
async def feed_text(msg: Message, state: FSMContext):
    await feed(msg, state)


@router.message(F.text == ui.BTN_EVENTS)
async def events_text(msg: Message, state: FSMContext):
    await events_list(msg, state)


@router.message(F.text == ui.BTN_BROADCASTS)
async def broadcasts_text(msg: Message, state: FSMContext):
    await broadcasts(msg, state)


@router.message(F.text == ui.BTN_NEW_EVENT)
async def new_event_text(msg: Message, state: FSMContext):
    await new_event(msg, state)


@router.message(F.text == ui.BTN_EXPORTS)
async def exports_text(msg: Message, state: FSMContext):
    await exports_menu(msg, state)
