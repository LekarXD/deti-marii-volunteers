"""Координатор: вход по коду, режимы, лента «Нужно решить», карточка волонтёра, события и команда, итог встречи, ответы, новое событие, выгрузки."""
import json
import secrets
from datetime import date, datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import BaseFilter
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import db, exports, platform, ui
from .config import COORDINATOR_CODE
from .notify import send
from .schedule import WEEKDAYS, human, occurrences, occurs, parse_day
from .seed import ROLES

class IsCoordinator(BaseFilter):
    """Хендлеры координатора видят только координаторы; остальные события уходят дальше, волонтёрскому роутеру."""

    async def __call__(self, event) -> bool:
        chat = event.message.chat if isinstance(event, CallbackQuery) else event.chat
        u = db.user(chat.id)
        return bool(u and u["is_coordinator"])


login_router = Router(name="coordinator-login")
router = Router(name="coordinator")
router.message.filter(IsCoordinator())
router.callback_query.filter(IsCoordinator())
# С платформой разделы координатора — в pcoordinator; старые кнопки из истории чата сюда не попадают.
router.message.filter(lambda _: not platform.enabled())
router.callback_query.filter(lambda _: not platform.enabled())


class NewEvent(StatesGroup):
    title = State()
    day = State()
    time = State()
    place = State()
    need = State()


class Reply(StatesGroup):
    text = State()


@login_router.message(Command("coordinator"))
async def login(msg: Message, command: CommandObject):
    u = db.ensure_user(msg.chat.id, msg.from_user.username)
    if not COORDINATOR_CODE or (command.args or "").strip() != COORDINATOR_CODE:
        await msg.answer("Код не подошёл. Код координатора выдаёт администратор бота.")
        return
    p = db.prefs(u)
    p["mode"] = "coord"
    db.update_user(u["id"], is_coordinator=1, name=u["name"] or msg.from_user.full_name, prefs=json.dumps(p))
    await ui.send_menu(msg, db.user(u["id"]), "Вы вошли как координатор.\n\nСразу сообщением придут только вопросы "
                       "волонтёров и отказы меньше чем за сутки. Остальное — в «Нужно решить», а утром в 10:00 — "
                       "короткая сводка: что решить и где не хватает людей.")


# --- события ------------------------------------------------------------------------

MONTHS_NOM = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь",
              "Ноябрь", "Декабрь"]
MONTHS_AHEAD = 4  # текущий месяц и три следующих


def month_bounds(year: int, month: int) -> tuple[date, date]:
    first = date(year, month, 1)
    nxt = date(year + month // 12, month % 12 + 1, 1)
    return max(first, db.now().date()), nxt - timedelta(days=1)


def month_events(year: int, month: int):
    start, end = month_bounds(year, month)
    return occurrences(db.events(), start, end) if start <= end else []


def plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return f"{n} {one}"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return f"{n} {few}"
    return f"{n} {many}"


def short_of_people(items) -> int:
    return sum(1 for ev, day in items if ev["need"] and db.confirmed_count(ev["id"], day.isoformat()) < ev["need"])


def months_kb():
    """Выбор месяца: только месяцы, где есть события. Рядом — сколько событий и где ещё не хватает людей."""
    today = db.now().date()
    b = InlineKeyboardBuilder()
    y, m = today.year, today.month
    for _ in range(MONTHS_AHEAD):
        items = month_events(y, m)
        if items:
            short = short_of_people(items)
            year = f" {y}" if y != today.year else ""
            tail = f" · не хватает людей на {short}" if short else " · все укомплектованы"
            b.button(text=f"{MONTHS_NOM[m - 1]}{year} · {plural(len(items), 'событие', 'события', 'событий')}{tail}",
                     callback_data=ui.EvCB(action="month", d=f"{y}{m:02d}"))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    b.adjust(1)
    return b.as_markup()


MONTHS_TEXT = "🗓 <b>События</b>\nВыберите месяц. Рядом — сколько событий и где ещё не хватает волонтёров."


def event_list_kb(year: int, month: int):
    b = InlineKeyboardBuilder()
    for ev, day in month_events(year, month)[:60]:
        cov = ui.coverage(ev, day) if ev["need"] else "—"
        b.button(text=f"{day:%d.%m} {WEEKDAYS[day.weekday()]} · {ev['title'][:28]} · {cov}",
                 callback_data=ui.EvCB(action="open", eid=ev["id"], d=ui.dkey(day)))
    b.button(text="← Месяцы", callback_data=ui.EvCB(action="months"))
    b.adjust(1)
    return b.as_markup()


def month_title(year: int, month: int) -> str:
    year_txt = f" {year}" if year != db.now().year else ""
    return (f"🗓 <b>{MONTHS_NOM[month - 1]}{year_txt}</b>\n"
            "Рядом — сколько людей подтверждено из нужных.")


@router.message(F.text == ui.BTN_EVENTS)
async def events_list(msg: Message, state: FSMContext):
    await state.clear()
    kb = months_kb()
    if not kb.inline_keyboard:
        await msg.answer("🗓 <b>События</b>\nВ ближайшие месяцы событий нет. Добавьте — кнопка «Новое событие» в меню.")
        return
    await msg.answer(MONTHS_TEXT, reply_markup=kb)


def event_detail(ev, day):
    lines = [ui.event_head(ev, day), "", f"<b>Команда: {ui.coverage(ev, day)}</b>"]
    team = db.team(ev["id"], day.isoformat())
    lines += [f"• {escape(r['name'] or 'Без имени')} — {ui.STATUS_RU.get(r['status'], r['status'])}" for r in team] or ["Пока никого не звали."]
    b = InlineKeyboardBuilder()
    if ev["need"] and day >= db.now().date():
        b.button(text="Позвать людей", callback_data=ui.EvCB(action="call", eid=ev["id"], d=ui.dkey(day)))
    for r in team[:6]:
        b.button(text=f"Карточка: {r['name'] or 'без имени'}", callback_data=ui.CardCB(uid=r["user_id"]))
    if team:
        b.button(text="Команда в Excel", callback_data=ui.EvCB(action="xls", eid=ev["id"], d=ui.dkey(day)))
    if day >= db.now().date():
        b.button(text="Отменить эту дату", callback_data=ui.EvCB(action="cancel", eid=ev["id"], d=ui.dkey(day)))
    b.button(text=f"← {MONTHS_NOM[day.month - 1]}", callback_data=ui.EvCB(action="month", d=f"{day:%Y%m}"))
    b.adjust(1)
    return "\n".join(lines), b.as_markup()


@router.callback_query(ui.EvCB.filter())
async def event_action(cb: CallbackQuery, callback_data: ui.EvCB, state: FSMContext, bot: Bot):
    if callback_data.action == "months":
        await cb.message.edit_text(MONTHS_TEXT, reply_markup=months_kb())
        await cb.answer()
        return
    if callback_data.action == "month":
        y, m = int(callback_data.d[:4]), int(callback_data.d[4:6])
        await cb.message.edit_text(month_title(y, m), reply_markup=event_list_kb(y, m))
        await cb.answer()
        return
    ev, day = db.event(callback_data.eid), ui.dparse(callback_data.d)
    if not ev:
        await cb.answer("Событие не найдено.")
        return
    if callback_data.action == "open":
        text, kb = event_detail(ev, day)
        await cb.message.edit_text(text, reply_markup=kb)
    elif callback_data.action == "xls":
        await cb.message.answer_document(BufferedInputFile(exports.team_xlsx(ev, day), filename=f"team-{ev['id']}-{day}.xlsx"),
                                         caption=f"Команда: {ev['title']}, {human(day)}")
    elif callback_data.action == "cancel":
        b = InlineKeyboardBuilder()
        b.button(text="Да, отменить", callback_data=ui.EvCB(action="cancel_yes", eid=ev["id"], d=callback_data.d))
        b.button(text="Нет", callback_data=ui.EvCB(action="open", eid=ev["id"], d=callback_data.d))
        await cb.message.edit_text(f"Отменить «{escape(ev['title'])}» {human(day)}? Всем, кого звали, придёт сообщение.",
                                   reply_markup=b.as_markup())
    elif callback_data.action == "cancel_yes":
        dates = json.loads(ev["cancelled_dates"] or "[]") + [day.isoformat()]
        db.run("UPDATE events SET cancelled_dates=? WHERE id=?", json.dumps(dates), ev["id"])
        told = 0
        for r in db.team(ev["id"], day.isoformat()):
            if r["status"] in ("invited", "accepted", "confirmed"):
                urgent = day <= db.now().date() + timedelta(days=1)
                await send(bot, r["user_id"], f"❗️ <b>Отменено:</b> {escape(ev['title'])}, {human(day)}. "
                                              "Извините за изменения — позовём в следующий раз.", urgent=urgent)
                told += 1
        await cb.message.edit_text(f"«{escape(ev['title'])}» {human(day)} отменено. Сообщили: {told}.")
    elif callback_data.action == "call":
        await state.update_data(pick_eid=ev["id"], pick_d=callback_data.d, picked=[])
        text, kb = pick_view(ev, day, [])
        await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


# --- позвать людей --------------------------------------------------------------------

def candidates(ev, day):
    """Допущенные волонтёры не на паузе, которых ещё не звали. Сначала те, кому подходят роль и день."""
    already = {r["user_id"] for r in db.team(ev["id"], day.isoformat())}
    out = []
    for u in db.all_("SELECT * FROM users WHERE status='active' AND blocked=0"):
        if u["id"] in already or db.prefs(u).get("paused"):
            continue
        why, score = [], 0
        if ev["role"] and ev["role"] in (u["roles"] or "").split(","):
            score += 2
            why.append(ROLES.get(ev["role"], ""))
        if str(day.weekday()) in (u["days"] or "").split(","):
            score += 1
            why.append(f"свободен(на) в {WEEKDAYS[day.weekday()].lower()}")
        was = db.one("SELECT COUNT(*) AS n FROM invites WHERE user_id=? AND event_id=? AND status='attended'", u["id"], ev["id"])["n"]
        if was:
            score += 2
            why.append(f"уже был(а) здесь {was} раз")
        out.append((score, u, ", ".join(why)))
    return [(u, why) for score, u, why in sorted(out, key=lambda x: -x[0])][:15]


def pick_view(ev, day, picked):
    people = candidates(ev, day)
    b = InlineKeyboardBuilder()
    for u, why in people:
        mark = "☑" if u["id"] in picked else "☐"
        b.button(text=f"{mark} {u['name'] or 'Без имени'}" + (f" · {why}" if why else ""), callback_data=ui.PickCB(uid=u["id"]))
    if picked:
        b.button(text=f"Отправить приглашения ({len(picked)})", callback_data=ui.StepCB(name="send_invites"))
    b.button(text="← Назад", callback_data=ui.EvCB(action="open", eid=ev["id"], d=ui.dkey(day)))
    b.adjust(1)
    head = f"<b>Кого позвать</b> на «{escape(ev['title'])}», {human(day)}. Сейчас {ui.coverage(ev, day)}."
    if not people:
        head += "\n\nНекого звать: все допущенные волонтёры уже приглашены или на паузе."
    return head, b.as_markup()


@router.callback_query(ui.PickCB.filter())
async def pick(cb: CallbackQuery, callback_data: ui.PickCB, state: FSMContext):
    data = await state.get_data()
    if "pick_eid" not in data:
        await cb.answer("Откройте событие заново.")
        return
    picked = data.get("picked", [])
    picked = [x for x in picked if x != callback_data.uid] if callback_data.uid in picked else picked + [callback_data.uid]
    await state.update_data(picked=picked)
    ev, day = db.event(data["pick_eid"]), ui.dparse(data["pick_d"])
    text, kb = pick_view(ev, day, picked)
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(ui.StepCB.filter(F.name == "send_invites"))
async def send_invites(cb: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    ev, day = db.event(data["pick_eid"]), ui.dparse(data["pick_d"])
    for uid in data.get("picked", []):
        db.set_invite(ev["id"], day.isoformat(), uid, "invited")
        await send(bot, uid, "🎨 <b>Приглашаем помочь</b>\n" + ui.event_head(ev, day), ui.invite_kb(ev, day))
    await state.update_data(picked=[])
    text, kb = event_detail(ev, day)
    await cb.message.edit_text(f"Приглашения отправлены: {len(data.get('picked', []))}. "
                               "Ночью они ждут до 9 утра.\n\n" + text, reply_markup=kb)
    await cb.answer()


@router.callback_query(ui.InvCB.filter(F.action.in_({"conf", "drop"})))
async def confirm(cb: CallbackQuery, callback_data: ui.InvCB, bot: Bot):
    ev, day = db.event(callback_data.eid), ui.dparse(callback_data.d)
    inv = db.invite(callback_data.eid, day.isoformat(), callback_data.uid)
    if not ev or not inv or inv["status"] != "accepted":
        await cb.answer("Уже обработано.")
        await cb.message.edit_reply_markup(reply_markup=None)
        return
    u = db.user(callback_data.uid)
    db.resolve("confirm", u["id"], ev["id"], day.isoformat())
    if callback_data.action == "conf":
        db.set_invite(ev["id"], day.isoformat(), u["id"], "confirmed")
        b = InlineKeyboardBuilder()
        b.button(text="Материалы", callback_data=ui.InvCB(action="mat", eid=ev["id"], d=callback_data.d))
        b.button(text="Не смогу", callback_data=ui.InvCB(action="no", eid=ev["id"], d=callback_data.d))
        await send(bot, u["id"], f"✅ <b>Ждём вас!</b>\n{ui.event_head(ev, day)}\n\nНакануне и утром придут напоминания.",
                   b.as_markup())
        note = f"Подтверждено: {ui.person(u)}. Теперь {ui.coverage(ev, day)}."
    else:
        db.set_invite(ev["id"], day.isoformat(), u["id"], "removed")
        await send(bot, u["id"], f"Спасибо, что откликнулись! На «{escape(ev['title'])}» {human(day)} команда уже собрана — позовём в следующий раз.")
        note = f"{ui.person(u)} не нужен(на) в этот раз — ему(ей) сообщили."
    await cb.message.edit_text(cb.message.html_text + "\n\n" + note)
    await cb.answer()


# --- допуск, ответы ---------------------------------------------------------------------

def past_meeting(uid: int):
    """Встреча, которая уже началась и ещё не закрыта (или закрыта как состоявшаяся)."""
    return db.one("SELECT * FROM meetings WHERE user_id=? AND status IN ('booked','done') AND starts_at<=? "
                  "ORDER BY starts_at DESC", uid, db.stamp())


def outcome_kb(uid: int):
    b = InlineKeyboardBuilder()
    b.button(text="Допустить к занятиям", callback_data=ui.AdmitCB(uid=uid, action="yes"))
    b.button(text="Не допускать", callback_data=ui.AdmitCB(uid=uid, action="no"))
    b.button(text="Не пришёл(ла)", callback_data=ui.AdmitCB(uid=uid, action="noshow"))
    b.adjust(1, 2)
    return b.as_markup()


@router.callback_query(ui.AdmitCB.filter())
async def meeting_outcome(cb: CallbackQuery, callback_data: ui.AdmitCB, bot: Bot):
    """Итог собеседования с кандидатом. Допуск к занятиям — только после собеседования."""
    u = db.user(callback_data.uid)
    if not u:
        await cb.answer()
        return
    if u["status"] == "active":
        await cb.answer("Уже допущен(а).")
        await cb.message.edit_reply_markup(reply_markup=None)
        return
    m = past_meeting(u["id"])
    if not m:
        await cb.answer("Допустить можно после собеседования — оно ещё не прошло.", show_alert=True)
        return
    db.resolve("outcome", u["id"])
    if callback_data.action == "yes":
        db.update_user(u["id"], status="active")
        db.run("UPDATE meetings SET status='done' WHERE id=?", m["id"])
        await send(bot, u["id"], "🎉 Спасибо за собеседование! Координатор допустил вас к занятиям фонда. Теперь сюда будут "
                                 "приходить приглашения — отвечайте кнопками «Приду» или «Не смогу».")
        note = "Допущен(а) к занятиям."
    elif callback_data.action == "no":
        db.run("UPDATE meetings SET status='done' WHERE id=?", m["id"])
        note = "Не допущен(а). Бот ничего не отправил — сообщите человеку лично."
    else:
        db.run("UPDATE meetings SET status='missed' WHERE id=?", m["id"])
        await send(bot, u["id"], "Похоже, собеседование не состоялось. Координатор свяжется с вами и предложит другое время, "
                                 "или запишитесь заново в личном кабинете на сайте фонда.")
        note = "Отмечено: не пришёл(ла). Человеку предложили записаться заново."
    await cb.message.edit_text(cb.message.html_text + "\n\n" + note)
    await cb.answer()


@router.callback_query(ui.AnswerCB.filter())
async def answer_start(cb: CallbackQuery, callback_data: ui.AnswerCB, state: FSMContext):
    await state.set_state(Reply.text)
    await state.update_data(qid=callback_data.qid)
    await cb.message.answer("Напишите ответ — он уйдёт волонтёру.", reply_markup=ui.cancel_kb())
    await cb.answer()


@router.message(Reply.text, F.text)
async def answer_send(msg: Message, state: FSMContext, bot: Bot):
    qid = (await state.get_data())["qid"]
    await state.clear()
    q = db.one("SELECT * FROM questions WHERE id=?", qid)
    db.run("UPDATE questions SET answer=? WHERE id=?", msg.text[:2000], qid)
    db.resolve("answer", ref=str(qid))
    await send(bot, q["user_id"], f"💬 <b>Ответ координатора</b>\n<i>{escape(q['text'][:300])}</i>\n\n{escape(msg.text)}", urgent=True)
    await msg.answer("Ответ отправлен.")


# --- режимы ------------------------------------------------------------------------------

@router.message(F.text == ui.BTN_TO_VOLUNTEER)
async def to_volunteer_mode(msg: Message, state: FSMContext):
    await state.clear()
    u = db.user(msg.chat.id)
    p = db.prefs(u)
    p["mode"] = "vol"
    db.update_user(u["id"], prefs=json.dumps(p))
    await ui.send_menu(msg, db.user(u["id"]), "Режим волонтёра: так бот выглядит для волонтёра. "
                                              "Вернуться — «Режим координатора».")


# --- новые события: лента того, что сделали волонтёры --------------------------------------

def action_kb(a):
    b = InlineKeyboardBuilder()
    if a["action"] == "confirm":
        d = (a["date"] or "").replace("-", "")
        b.button(text="Подтвердить", callback_data=ui.InvCB(action="conf", eid=a["ref"], d=d, uid=a["user_id"]))
        b.button(text="Не нужно", callback_data=ui.InvCB(action="drop", eid=a["ref"], d=d, uid=a["user_id"]))
    elif a["action"] == "outcome":
        b.attach(InlineKeyboardBuilder.from_markup(outcome_kb(a["user_id"])))
    elif a["action"] == "answer":
        b.button(text="Ответить", callback_data=ui.AnswerCB(qid=int(a["ref"])))
    if a["user_id"]:
        b.button(text="Карточка волонтёра", callback_data=ui.CardCB(uid=a["user_id"]))
    b.adjust(2, 1)
    return b.as_markup()


def when(stamp: str) -> str:
    t = datetime.fromisoformat(stamp)
    return f"{t:%H:%M}" if t.date() == db.now().date() else f"{t:%d.%m %H:%M}"


def card_label(u) -> str:
    """Имя для кнопки карточки. После тестового сброса имени нет — тогда ник или почта."""
    if u["name"]:
        return u["name"]
    if u["username"]:
        return "@" + u["username"]
    return u["email"] or f"id {u['id']}"


async def show_feed(target: Message):
    actions = db.open_actions()
    recent = db.all_("SELECT * FROM activity ORDER BY id DESC LIMIT 15")
    unseen = db.one("SELECT COUNT(*) AS n FROM activity WHERE seen=0")["n"]
    db.run("UPDATE activity SET seen=1 WHERE seen=0")
    head = f"🔔 <b>Нужно решить: {len(actions) or 'ничего'}</b>\nНепрочитанных уведомлений: {unseen}"
    await target.answer(head)
    for a in actions[:5]:
        await target.answer(f"{when(a['at'])} · {a['text']}", reply_markup=action_kb(a))
    if len(actions) > 5:
        await target.answer(f"…и ещё {len(actions) - 5}. Решите эти — откроются следующие.")
    if recent:
        lines = ["<b>Недавно</b>"] + [f"{'• ' if r['seen'] else '🆕 '}{when(r['at'])} — {r['text']}" for r in recent]
        b = InlineKeyboardBuilder()
        people = []
        for r in recent:
            if r["user_id"] and r["user_id"] not in people:
                people.append(r["user_id"])
        for uid in people[:6]:
            u = db.user(uid)
            if u:
                b.button(text=f"Карточка: {card_label(u)}", callback_data=ui.CardCB(uid=uid))
        b.adjust(1)
        await target.answer("\n".join(lines), reply_markup=b.as_markup())
    else:
        await target.answer("🌿 Пока ничего не произошло.")


@router.message(F.text == ui.BTN_FEED)
async def feed(msg: Message, state: FSMContext):
    await state.clear()
    await show_feed(msg)


@router.callback_query(ui.FeedCB.filter())
async def feed_cb(cb: CallbackQuery):
    await show_feed(cb.message)
    await cb.answer()


# --- карточка волонтёра -----------------------------------------------------------------

class Direct(StatesGroup):
    text = State()


def card(uid: int):
    u = db.user(uid)
    if not u:
        return "Волонтёр не найден.", None
    today = db.now().date().isoformat()
    st = ui.USER_STATUS_RU.get(u["status"], u["status"]) + (" · на паузе" if db.prefs(u).get("paused") else "")
    if u["status"] == "candidate":
        nxt = db.one("SELECT * FROM meetings WHERE user_id=? AND status='booked' AND starts_at>? ORDER BY starts_at", uid, db.stamp())
        if past_meeting(uid):
            st += " · собеседование прошло, ждёт решения"
        elif nxt:
            st += f" · собеседование {datetime.fromisoformat(nxt['starts_at']):%d.%m в %H:%M}"
        else:
            st += " · на собеседование не записан(а)"
    contacts = " · ".join(x for x in [escape(u["phone"] or ""), f"@{escape(u['username'])}" if u["username"] else "",
                                       escape(u["email"] or "")] if x) or "нет"
    done = db.one("SELECT COUNT(*) AS n, COALESCE(SUM(hours),0) AS h, MAX(date) AS last FROM invites "
                  "WHERE user_id=? AND status='attended'", uid)
    declined = db.one("SELECT COUNT(*) AS n FROM invites WHERE user_id=? AND status='declined'", uid)["n"]
    absent = db.one("SELECT COUNT(*) AS n FROM invites WHERE user_id=? AND status='absent'", uid)["n"]
    upcoming = db.all_("SELECT * FROM invites WHERE user_id=? AND date>=? AND status IN ('invited','accepted','confirmed') "
                       "ORDER BY date LIMIT 3", uid, today)
    q = db.one("SELECT * FROM questions WHERE user_id=? ORDER BY id DESC LIMIT 1", uid)
    fb = db.one("SELECT * FROM invites WHERE user_id=? AND feedback IS NOT NULL ORDER BY date DESC LIMIT 1", uid)
    lines = [f"👤 <b>{escape(u['name'] or 'Без имени')}</b>", f"Статус: {st}", f"Контакты: {contacts}",
             f"Интересы: {ui.roles_text(u['roles'])}", f"Удобные дни: {ui.days_text(u['days'])}",
             f"В боте с {(u['created_at'] or '')[:10] or '—'}", "",
             f"<b>Участие</b>: был(а) {done['n']} раз, {done['h']:g} ч" + (f", последний — {done['last']}" if done["last"] else ""),
             f"Отказов: {declined} · не пришёл(ла): {absent}"]
    if upcoming:
        lines.append("<b>Ближайшие</b>")
        for r in upcoming:
            ev = db.event(r["event_id"])
            lines.append(f"• {r['date'][8:]}.{r['date'][5:7]} {escape(ev['title'] if ev else r['event_id'])} — "
                         f"{ui.STATUS_RU.get(r['status'], r['status'])}")
    if q:
        lines.append(f"\n<b>Последний вопрос</b>: {escape(q['text'][:200])}" + ("" if q["answer"] else " <i>(без ответа)</i>"))
    if fb:
        lines.append(f"<b>Сложности на занятии</b>: {escape(fb['feedback'][:200])}")
    lines += ["", "<b>Из анкеты</b>", "<i>Здесь будут ответы из анкеты на сайте: опыт и навыки, с кем удобно работать, "
                                      "ограничения, как связываться. Появятся, когда подключим API сайта.</i>"]
    b = InlineKeyboardBuilder()
    if u["status"] == "candidate" and past_meeting(uid):
        b.attach(InlineKeyboardBuilder.from_markup(outcome_kb(uid)))
    b.button(text="Написать в бот", callback_data=ui.StepCB(name=f"dm{uid}"))
    b.button(text="← Уведомления", callback_data=ui.FeedCB())
    b.adjust(2, 1, 1, 1)
    return "\n".join(lines), b.as_markup()


@router.callback_query(ui.CardCB.filter())
async def open_card(cb: CallbackQuery, callback_data: ui.CardCB):
    text, kb = card(callback_data.uid)
    await cb.message.answer(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(ui.StepCB.filter(F.name.startswith("dm")))
async def direct_start(cb: CallbackQuery, callback_data: ui.StepCB, state: FSMContext):
    await state.set_state(Direct.text)
    await state.update_data(dm=int(callback_data.name[2:]))
    await cb.message.answer("Напишите сообщение — оно придёт волонтёру от имени координатора.", reply_markup=ui.cancel_kb())
    await cb.answer()


@router.message(Direct.text, F.text)
async def direct_send(msg: Message, state: FSMContext, bot: Bot):
    uid = (await state.get_data())["dm"]
    await state.clear()
    await send(bot, uid, f"💬 <b>Сообщение от координатора</b>\n{escape(msg.text)}", urgent=True)
    await msg.answer("Отправлено.")


# --- выгрузки ---------------------------------------------------------------------

@router.message(F.text == ui.BTN_EXPORTS)
async def exports_menu(msg: Message, state: FSMContext):
    await state.clear()
    b = InlineKeyboardBuilder()
    b.button(text="Волонтёры — Excel", callback_data=ui.ExportCB(kind="people"))
    b.button(text="Команды на 2 недели — Excel", callback_data=ui.ExportCB(kind="teams"))
    b.button(text="Часы за месяц — Excel", callback_data=ui.ExportCB(kind="hours"))
    b.button(text="Итоги месяца", callback_data=ui.ExportCB(kind="summary"))
    b.adjust(1)
    await msg.answer("📊 <b>Выгрузки</b>\nФайлы с контактами приходят только сюда, в личный чат координатора.",
                     reply_markup=b.as_markup())


@router.callback_query(ui.ExportCB.filter())
async def export(cb: CallbackQuery, callback_data: ui.ExportCB):
    today = db.now().date()
    if callback_data.kind == "people":
        await cb.message.answer_document(BufferedInputFile(exports.volunteers_xlsx(), filename=f"volunteers-{today}.xlsx"))
    elif callback_data.kind == "teams":
        await cb.message.answer_document(BufferedInputFile(exports.teams_xlsx(), filename=f"teams-{today}.xlsx"))
    elif callback_data.kind == "hours":
        await cb.message.answer_document(BufferedInputFile(exports.hours_xlsx(today), filename=f"hours-{today:%Y-%m}.xlsx"))
    elif callback_data.kind == "summary":
        await cb.message.answer(exports.month_summary(today))
    await cb.answer()


# --- новое событие -----------------------------------------------------------------

@router.message(F.text == ui.BTN_NEW_EVENT)
async def new_event(msg: Message, state: FSMContext):
    await state.clear()
    await state.set_state(NewEvent.title)
    await msg.answer("Как называется событие? Например: «Открытый МК по керамике».", reply_markup=ui.cancel_kb())


@router.message(NewEvent.title, F.text)
async def ne_title(msg: Message, state: FSMContext):
    await state.update_data(title=msg.text.strip()[:80])
    await state.set_state(NewEvent.day)
    await msg.answer("Дата? Например: 31.10", reply_markup=ui.cancel_kb())


@router.message(NewEvent.day, F.text)
async def ne_day(msg: Message, state: FSMContext):
    day = parse_day(msg.text, db.now().date())
    if not day:
        await msg.answer("Не получилось разобрать дату. Напишите в виде 31.10 или 31.10.2026", reply_markup=ui.cancel_kb())
        return
    await state.update_data(day=day.isoformat())
    await state.set_state(NewEvent.time)
    await msg.answer("Время? Например: 14:00-18:00. Если ещё не известно — напишите «-».", reply_markup=ui.cancel_kb())


@router.message(NewEvent.time, F.text)
async def ne_time(msg: Message, state: FSMContext):
    text = msg.text.replace("—", "-").replace("–", "-").replace(" ", "")
    start = end = ""
    if text != "-":
        parts = text.split("-")
        ok = all(len(p) == 5 and p[2] == ":" and p[:2].isdigit() and p[3:].isdigit() for p in parts if p)
        if not ok or not parts[0] or (len(parts) > 1 and parts[1] and parts[1] <= parts[0]):
            await msg.answer("Напишите время как 14:00-18:00 или 14:00, либо «-», если пока неизвестно.", reply_markup=ui.cancel_kb())
            return
        start, end = parts[0], parts[1] if len(parts) > 1 else ""
    await state.update_data(time=start, end_time=end)
    await state.set_state(NewEvent.place)
    await msg.answer("Где проходит? Адрес или название площадки.", reply_markup=ui.cancel_kb())


@router.message(NewEvent.place, F.text)
async def ne_place(msg: Message, state: FSMContext):
    await state.update_data(place=msg.text.strip()[:200])
    await state.set_state(NewEvent.need)
    await msg.answer("Сколько волонтёров нужно? Число, 0 — если не нужны.", reply_markup=ui.cancel_kb())


@router.message(NewEvent.need, F.text)
async def ne_need(msg: Message, state: FSMContext):
    if not msg.text.strip().isdigit():
        await msg.answer("Напишите число, например 2.", reply_markup=ui.cancel_kb())
        return
    await state.update_data(need=int(msg.text.strip()))
    b = InlineKeyboardBuilder()
    for key, title in ROLES.items():
        b.button(text=title, callback_data=ui.NewRoleCB(key=key))
    b.button(text="Отмена", callback_data=ui.StepCB(name="cancel_fsm"))
    b.adjust(1)
    await state.set_state(None)
    await state.update_data(new_event=True)
    await msg.answer("Какая роль у волонтёров?", reply_markup=b.as_markup())


@router.callback_query(ui.NewRoleCB.filter())
async def ne_role(cb: CallbackQuery, callback_data: ui.NewRoleCB, state: FSMContext):
    data = await state.get_data()
    if not data.get("new_event"):
        await cb.answer()
        return
    await state.update_data(role=callback_data.key)
    b = InlineKeyboardBuilder()
    b.button(text="Один раз", callback_data=ui.StepCB(name="once"))
    weekday = WEEKDAYS[ui.dparse(data["day"].replace("-", "")).weekday()].lower()
    b.button(text=f"Каждую неделю ({weekday})", callback_data=ui.StepCB(name="weekly"))
    b.button(text="Отмена", callback_data=ui.StepCB(name="cancel_fsm"))
    b.adjust(1)
    await cb.message.edit_text(f"Роль: {ROLES[callback_data.key]}. Повторять?", reply_markup=b.as_markup())
    await cb.answer()


@router.callback_query(ui.StepCB.filter(F.name.in_({"once", "weekly"})))
async def ne_save(cb: CallbackQuery, callback_data: ui.StepCB, state: FSMContext):
    data = await state.get_data()
    if not data.get("new_event"):
        await cb.answer()
        return
    await state.clear()
    eid = "e" + secrets.token_hex(3)
    day = ui.dparse(data["day"].replace("-", ""))
    weekly = callback_data.name == "weekly"
    db.run("INSERT INTO events (id, title, kind, format, place, role, start_date, time, end_time, need, repeat, weekdays) "
           "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
           eid, data["title"], "занятие" if weekly else "мероприятие", "регулярное занятие" if weekly else "разовое",
           data["place"], data["role"], day.isoformat(), data["time"], data["end_time"], data["need"],
           "weekly" if weekly else "none", str(day.weekday()) if weekly else "")
    ev = db.event(eid)
    assert occurs(ev, day)
    text, kb = event_detail(ev, day)
    await cb.message.edit_text("✨ Событие добавлено.\n\n" + text, reply_markup=kb)
    await cb.answer()
