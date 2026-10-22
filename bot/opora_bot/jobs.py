"""Фоновые проверки раз в минуту: напоминания, вопросы после занятия, сигналы координатору."""
import asyncio
import logging
from datetime import datetime, timedelta
from html import escape

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import db, exports, ui
from .notify import flush_outbox, send, to_coordinators
from .schedule import ends_at, human, occurrences, starts_at
from .volunteer import meeting_kb, meeting_text

log = logging.getLogger(__name__)


async def meeting_reminders(bot: Bot, n: datetime) -> None:
    """Два напоминания о собеседовании: за сутки (с кнопками) и за 15 минут (срочно — даже в тихие часы)."""
    for m in db.all_("SELECT * FROM meetings WHERE status='booked' AND starts_at>?", n.isoformat()):
        s = datetime.fromisoformat(m["starts_at"])
        place = escape(m["place"])
        if s - timedelta(hours=24) <= n < s - timedelta(hours=1) and db.mark_sent(f"m24:{m['id']}"):
            b = InlineKeyboardBuilder()
            b.button(text="Буду", callback_data=ui.MeetCB(action="yes", mid=m["id"]))
            b.attach(InlineKeyboardBuilder.from_markup(meeting_kb(m["id"])))
            b.adjust(1)
            day = "Сегодня" if s.date() == n.date() else "Завтра"
            await send(bot, m["user_id"], f"🔔 <b>Напоминаем о собеседовании</b>\n{day} в {s:%H:%M} — собеседование "
                                          f"с координатором.\n📍 {place}", b.as_markup())
        if s - timedelta(minutes=15) <= n < s and db.mark_sent(f"m15:{m['id']}"):
            await send(bot, m["user_id"], f"⏰ Через 15 минут, в {s:%H:%M}, собеседование с координатором.\n📍 {place}",
                       urgent=True)


async def meeting_followup(bot: Bot, n: datetime) -> None:
    """Через час после начала собеседования — в ленту координатора «Как прошла встреча?». Допуск к занятиям только отсюда."""
    for m in db.all_("SELECT * FROM meetings WHERE status='booked' AND starts_at<=?", (n - timedelta(hours=1)).isoformat()):
        s = datetime.fromisoformat(m["starts_at"])
        u = db.user(m["user_id"])
        if u and u["status"] == "candidate" and n - s < timedelta(days=3) and db.mark_sent(f"mfollow:{m['id']}"):
            db.log("outcome", u["id"], f"Как прошло собеседование с {ui.person(u)}, {human(s.date())}, {s:%H:%M}?",
                   ref=str(m["id"]), action="outcome")


async def event_reminders(bot: Bot, n: datetime) -> None:
    """Волонтёру: одно напоминание накануне в 18:00 и вопрос «Как прошло?» после события."""
    today = n.date()
    for ev, day in occurrences(db.events(), today - timedelta(days=1), today + timedelta(days=1)):
        try:
            await remind_event(bot, n, ev, day)
        except Exception:  # событие с битым временем не должно оставить без напоминаний те, что идут после него
            log.exception("reminders for event %s on %s failed", ev["id"], day)


async def remind_event(bot: Bot, n: datetime, ev, day) -> None:
    today = n.date()
    for r in db.team(ev["id"], day.isoformat()):
        if r["status"] != "confirmed":
            continue
        uid, key = r["user_id"], f"{ev['id']}:{day}:{r['user_id']}"
        if day == today + timedelta(days=1) and n.hour >= 18 and db.mark_sent("e1:" + key):
            b = InlineKeyboardBuilder()
            b.button(text="Материалы", callback_data=ui.InvCB(action="mat", eid=ev["id"], d=ui.dkey(day)))
            b.button(text="Не смогу", callback_data=ui.InvCB(action="no", eid=ev["id"], d=ui.dkey(day)))
            await send(bot, uid, "🔔 <b>Завтра</b>\n" + ui.event_head(ev, day), b.as_markup())
        # после занятия: через час после окончания, либо в 20:00, а если поздно — утром следующего дня
        end = ends_at(ev, day) or starts_at(ev, day).replace(hour=19, minute=0)
        due = end + timedelta(hours=1)
        if due.hour >= 22:
            due = (due + timedelta(days=1)).replace(hour=10, minute=0)
        if due <= n < due + timedelta(days=2) and db.mark_sent("after:" + key):
            a = InlineKeyboardBuilder()
            a.button(text="Всё хорошо", callback_data=ui.AfterCB(action="ok", eid=ev["id"], d=ui.dkey(day)))
            a.button(text="Были сложности", callback_data=ui.AfterCB(action="hard", eid=ev["id"], d=ui.dkey(day)))
            a.button(text="Не смог(ла) прийти", callback_data=ui.AfterCB(action="absent", eid=ev["id"], d=ui.dkey(day)))
            a.adjust(2, 1)
            await send(bot, uid, f"💭 Как прошло «{escape(ev['title'])}», {human(day, False)}?", a.as_markup())


def gaps(today, days: int = 7):
    out = []
    for ev, d in occurrences(db.events(), today, today + timedelta(days=days)):
        have = db.confirmed_count(ev["id"], d.isoformat())
        if ev["need"] and have < ev["need"]:
            out.append((ev, d, have))
    return out


async def coordinator_signals(bot: Bot, n: datetime) -> None:
    """Вместо отдельных сигналов — молчание в ленту и одна сводка в 10:00."""
    today = n.date()
    limit = (n - timedelta(hours=48)).isoformat()
    for r in db.all_("SELECT i.*, u.name, u.username FROM invites i JOIN users u ON u.id=i.user_id "
                     "WHERE i.status='invited' AND i.invited_at<=? AND i.date>=?", limit, today.isoformat()):
        ev = db.event(r["event_id"])
        if ev and db.mark_sent(f"noans:{r['event_id']}:{r['date']}:{r['user_id']}"):
            db.log("noanswer", r["user_id"], f"{ui.person(r)} не ответил(а) 48 часов: {escape(ev['title'])}, "
                                             f"{human(ui.dparse(r['date'].replace('-', '')))}", ref=ev["id"], date=r["date"])
    if n.hour < 10 or not db.coordinators():
        return
    actions = len(db.open_actions())
    unseen = db.one("SELECT COUNT(*) AS n FROM activity WHERE seen=0")["n"]
    short = gaps(today)
    if not (actions or unseen or short) or not db.mark_sent(f"digest:{today}"):
        return
    lines = [f"☀️ <b>Сводка на {human(today)}</b>", f"Нужно решить: {actions} · новых событий: {unseen}"]
    if short:
        lines.append("\n<b>Не хватает людей на неделе</b>")
        lines += [f"• {d:%d.%m} {escape(ev['title'])} — {have} из {ev['need']}" for ev, d, have in short[:8]]
    b = InlineKeyboardBuilder()
    b.button(text="Открыть новые события", callback_data=ui.FeedCB())
    for ev, d, _ in short[:3]:
        b.button(text=f"Позвать: {d:%d.%m} {ev['title'][:24]}", callback_data=ui.EvCB(action="call", eid=ev["id"], d=ui.dkey(d)))
    b.adjust(1)
    await to_coordinators(bot, "\n".join(lines), b.as_markup(), urgent=False)


async def monthly_thanks(bot: Bot, n: datetime) -> None:
    if n.day != 1 or n.hour < 12:
        return
    prev = n.date() - timedelta(days=1)
    first, last = exports.month_bounds(prev)
    for r in db.all_("SELECT user_id, COUNT(*) AS c, SUM(hours) AS h FROM invites WHERE status='attended' "
                     "AND date BETWEEN ? AND ? GROUP BY user_id", first.isoformat(), last.isoformat()):
        u = db.user(r["user_id"])
        if u and db.prefs(u)["thanks"] and db.mark_sent(f"thanks:{prev:%Y-%m}:{u['id']}"):
            await send(bot, u["id"], f"🤍 Спасибо! За прошлый месяц вы были на {r['c']} занятиях — {r['h'] or 0:g} ч с ребятами.")


async def tick(bot: Bot) -> None:
    n = db.now()
    for job in (flush_outbox, meeting_reminders, meeting_followup, event_reminders, coordinator_signals, monthly_thanks):
        try:
            await (job(bot) if job is flush_outbox else job(bot, n))
        except Exception:  # одна сломанная проверка не должна останавливать остальные
            log.exception("job %s failed", job.__name__)


async def loop(bot: Bot) -> None:
    while True:
        await tick(bot)
        await asyncio.sleep(60)
