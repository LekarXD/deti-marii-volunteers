"""Фоновые задачи, когда бот подключён к платформе «Опора» (вместо jobs.py).

Раз в минуту для каждого, кто подключил Telegram в профиле:
- новые сообщения из «Сообщений» на сайте (координатор, системные уведомления) приходят в бот с кнопкой «Ответить»;
- раз в 5 минут: новые приглашения с кнопками «Приду / Не смогу», напоминание накануне в 18:00, вопрос
  «Как прошло?» после занятия, напоминания о собеседовании за сутки и за 15 минут;
- координатору в 10:00 — сводка «Нужно решить», если есть что решать.
Что уже отправлено, помним в таблицах sent и conv_seen, поэтому после перезапуска бот не повторяется.
"""
import asyncio
import logging
from datetime import timedelta
from html import escape

from aiogram import Bot

from . import db, pcoordinator, platform, pvolunteer
from .notify import flush_outbox, send
from .platform import NotLinked, PlatformError
from .pvolunteer import local, when

log = logging.getLogger(__name__)
SLOW_EVERY = 5  # минут между проверками расписания и собеседований


def linked_users():
    return db.all_("SELECT * FROM users WHERE COALESCE(site_id,'')<>'' AND blocked=0 AND status<>'new'")


def seen(uid: int, cid: str) -> int | None:
    row = db.one("SELECT seq FROM conv_seen WHERE user_id=? AND conversation_id=?", uid, cid)
    return row["seq"] if row else None


def mark_seen(uid: int, cid: str, seq: int) -> None:
    db.run("INSERT INTO conv_seen (user_id, conversation_id, seq) VALUES (?,?,?) "
           "ON CONFLICT(user_id, conversation_id) DO UPDATE SET seq=excluded.seq", uid, cid, seq)


async def messages(bot: Bot, u) -> None:
    """Сообщения с сайта → Telegram. Историю до подключения не пересылаем, только новое."""
    uid = u["id"]
    page = await platform.get(uid, "/conversations", limit=50)
    for conv in page["items"]:
        last = seen(uid, conv["id"])
        if last is None:
            mark_seen(uid, conv["id"], conv["last_seq"])
            continue
        after = last
        while conv["last_seq"] > after:
            batch = await platform.get(uid, f"/conversations/{conv['id']}/sync", after_seq=after)
            for m in batch["messages"]:
                if m["author_user_id"] != u["site_id"] and (m["text"] or m["assets"]):
                    who = "🔔" if conv["kind"] == "system" or not m["author_user_id"] else f"💬 <b>{escape(m['author_name'])}</b>:"
                    text = f"{who} {escape(m['text'] or '')}" + ("\n📎 Вложение — откройте «Сообщения» на сайте." if m["assets"] else "")
                    markup = None if conv["kind"] == "system" else pvolunteer.reply_kb(conv["id"])
                    await send(bot, uid, text[:4000], markup, urgent=conv["kind"] != "system")
            after = batch["next_after_seq"] if batch["messages"] else conv["last_seq"]
            mark_seen(uid, conv["id"], after)
            if not batch.get("has_more"):
                break


async def schedule(bot: Bot, u) -> None:
    uid, n = u["id"], db.now()
    items = await pvolunteer.schedule(uid, days=90, state="all")  # приглашения бывают и на месяц-два вперёд
    for a in items:
        start, end = local(a["starts_at"]), local(a["ends_at"])
        if a["status"] == "invited" and pvolunteer.can_answer(a) and start > n:
            if db.mark_sent(f"p:inv:{a['id']}"):
                await send(bot, uid, pvolunteer.invite_text(a), pvolunteer.invite_kb(a))
        if a["status"] != "confirmed" or a["occurrence_status"] != "scheduled":
            continue
        evening = (start - timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
        if evening <= n < start and db.mark_sent(f"p:rem:{a['id']}"):
            await send(bot, uid, f"⏰ Завтра: <b>{escape(a['title'])}</b>, {when(a['starts_at'], a['ends_at'])}\n"
                                 f"📍 {escape(a['location'] or 'место уточняется')}. Ждём вас!", pvolunteer.invite_kb(a))
        if end <= n < end + timedelta(days=2) and db.mark_sent(f"p:after:{a['id']}"):
            try:
                r = await platform.get(uid, f"/me/assignments/{a['id']}/reflection")
            except platform.ApiFailure:
                continue
            if r["can_submit"] and not r["submitted_at"]:
                await send(bot, uid, f"Как прошло «{escape(a['title'])}»?", pvolunteer.mood_kb(a["id"]))


async def interviews(bot: Bot, u) -> None:
    uid, n = u["id"], db.now()
    for m in await platform.get(uid, "/me/interviews"):
        if m["status"] != "booked":
            continue
        left = local(m["starts_at"]) - n
        place = escape(m["venue"] or "онлайн")
        if timedelta(minutes=0) < left <= timedelta(minutes=20) and db.mark_sent(f"p:mt15:{m['id']}:{m['starts_at']}"):
            await send(bot, uid, f"⏰ Через {max(1, int(left.total_seconds() // 60))} мин — собеседование с координатором. 📍 {place}",
                       pvolunteer.site_kb("Подключиться", "/application") if not m.get("join_url") else None, urgent=True)
        elif timedelta(hours=2) < left <= timedelta(hours=24) and db.mark_sent(f"p:mt24:{m['id']}:{m['starts_at']}"):
            await send(bot, uid, f"🤝 Завтра собеседование с координатором: {when(m['starts_at'], m['ends_at'])}. 📍 {place}\n"
                                 "Если не получится — откройте «Собеседование» в меню.")


async def digest(bot: Bot, u) -> None:
    n = db.now()
    if not (u["is_coordinator"] and platform.is_staff(u["id"])) or n.hour < 10:
        return
    if not db.mark_sent(f"p:digest:{u['id']}:{n.date().isoformat()}"):
        return
    d = await pcoordinator.collect(u["id"])
    count = pcoordinator.todo_count(d)
    pcoordinator.remember_todo(u["id"], count)
    if count or d["upcoming"]:
        await send(bot, u["id"], f"☀️ Доброе утро! Нужно решить: {count or 'ничего'}"
                                 + (f", собеседований в ближайшие 2 дня: {len(d['upcoming'])}" if d["upcoming"] else "")
                                 + ".\nОткройте «Новые уведомления» в меню.")


async def tick(bot: Bot, minute: int) -> None:
    try:
        await flush_outbox(bot)
    except Exception:  # noqa: BLE001
        log.exception("outbox failed")
    for u in linked_users():
        jobs = [messages, digest] + ([schedule, interviews] if minute % SLOW_EVERY == 0 else [])
        for job in jobs:
            try:
                await job(bot, u)
            except NotLinked:
                db.update_user(u["id"], status="new", is_coordinator=0)
                platform.forget(u["id"])
                break
            except PlatformError as e:  # сайт недоступен или не принял запрос — попробуем в следующую минуту
                log.warning("%s для %s: %s", job.__name__, u["id"], e)
            except Exception:  # noqa: BLE001 — одна сломанная проверка не должна останавливать остальные
                log.exception("job %s failed", job.__name__)


async def loop(bot: Bot) -> None:
    minute = 0
    while True:
        await tick(bot, minute)
        minute += 1
        await asyncio.sleep(60)
