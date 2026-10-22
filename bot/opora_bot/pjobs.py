"""Фоновые задачи, когда бот подключён к платформе «Опора» (вместо jobs.py).

Раз в минуту для каждого, кто подключил Telegram в профиле:
- новое в «Сообщениях» на сайте приходит в бот: по одному сообщению на разговор с кнопкой «Ответить»,
  уведомления фонда — одним сообщением на всё новое;
- раз в 5 минут: новые приглашения с кнопками «Приду / Не смогу», напоминание накануне в 18:00, вопрос
  «Как прошло?» через пару часов после занятия, напоминания о собеседовании за сутки и за 15 минут;
- координатору в 10:00 — сводка «Нужно решить», если есть что решать.

Бот пишет так же, как сайт: не пишет тем, кто просил не беспокоить или выключил тему, а в тихие часы
человека (настройки на сайте) и ночью (QUIET_HOURS) откладывает сообщение до утра.
Что уже отправлено, помним в таблицах sent и conv_seen, поэтому после перезапуска бот не повторяется.
"""
import asyncio
import logging
import time
from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiogram import Bot
from aiogram.utils.keyboard import InlineKeyboardBuilder

from . import db, pcoordinator, platform, pvolunteer, ui
from .config import TZ
from .notify import flush_outbox, send
from .platform import NotLinked, PlatformError
from .pvolunteer import PA, local, short, when

log = logging.getLogger(__name__)
SLOW_EVERY = 5  # минут между проверками расписания и собеседований
# Уведомления сайта о занятиях, которые бот уже показал своей карточкой с кнопками или которые человек вызвал
# сам («Приду», «Не смогу»): переслать их — значит написать то же самое второй раз.
SKIP_NOTICES = ("Приглашение на занятие.", "Участие согласовано координатором.", "Участие подтверждено.",
                "Отказ от участия сохранён.", "Освободилось место на занятии")
PREFS_TTL = 300
_prefs: dict[int, tuple[float, dict]] = {}


def linked_users():
    return db.all_("SELECT * FROM users WHERE COALESCE(site_id,'')<>'' AND blocked=0 AND status<>'new'")


def seen(uid: int, cid: str) -> int | None:
    row = db.one("SELECT seq FROM conv_seen WHERE user_id=? AND conversation_id=?", uid, cid)
    return row["seq"] if row else None


def mark_seen(uid: int, cid: str, seq: int) -> None:
    db.run("INSERT INTO conv_seen (user_id, conversation_id, seq) VALUES (?,?,?) "
           "ON CONFLICT(user_id, conversation_id) DO UPDATE SET seq=excluded.seq", uid, cid, seq)


# --- согласия и тихие часы человека (настройки уведомлений на сайте) ------------------------------

async def prefs(uid: int) -> dict:
    hit = _prefs.get(uid)
    if hit and hit[0] > time.time():
        return hit[1]
    p = await platform.get(uid, "/me/notification-preferences")
    _prefs[uid] = (time.time() + PREFS_TTL, p)
    return p


def wants(p: dict, topic: str | None = None) -> bool:
    if p.get("effective_no_contact", p.get("no_contact")):
        return False
    return topic is None or bool(p["topics"].get(topic, True))


def quiet_until(p: dict) -> datetime | None:
    """Конец тихих часов человека, если они идут сейчас."""
    if not p.get("quiet_enabled") or p["quiet_from"] == p["quiet_to"]:
        return None
    try:
        zone = ZoneInfo(p.get("timezone") or "Europe/Moscow")
    except (ZoneInfoNotFoundError, ValueError):
        zone = TZ
    n = datetime.now(zone)
    m, a, b = n.hour * 60 + n.minute, p["quiet_from"], p["quiet_to"]
    if not (a <= m < b if a < b else m >= a or m < b):
        return None
    end = n.replace(hour=b // 60, minute=b % 60, second=0, microsecond=0)
    return (end if end > n else end + timedelta(days=1)).astimezone(TZ)


# --- сообщения с сайта -----------------------------------------------------------------------------

def body(m: dict) -> str:
    text = escape(m["text"] or "")
    if m["assets"]:
        text += ("\n" if text else "") + "📎 Есть вложение, оно на сайте в «Сообщениях»."
    return text


def echo(uid: int, text: str) -> bool:
    """Уведомление сайта о том, что человек сам только что сделал в боте (см. pvolunteer.echo_key)."""
    head = text.split(" МСК", 1)[0]
    return " МСК" in text and db.was_sent(f"p:echo:{uid}:{head} МСК")


async def messages(bot: Bot, u, p: dict) -> None:
    """Новое из «Сообщений» сайта → Telegram. Историю до подключения не пересылаем, только новое."""
    uid = u["id"]
    page = await platform.get(uid, "/conversations", limit=50)
    notices = []
    later = quiet_until(p)
    for conv in page["items"]:
        last = seen(uid, conv["id"])
        if last is None:
            mark_seen(uid, conv["id"], conv["last_seq"])
            continue
        new, after = [], last
        while conv["last_seq"] > after:
            batch = await platform.get(uid, f"/conversations/{conv['id']}/sync", after_seq=after)
            new += [m for m in batch["messages"] if m["author_user_id"] != u["site_id"] and (m["text"] or m["assets"])]
            after = batch["next_after_seq"] if batch["messages"] else conv["last_seq"]
            if not batch.get("has_more"):
                break
        mark_seen(uid, conv["id"], after)
        if not new:
            continue
        if conv["kind"] == "system" or not new[0]["author_user_id"]:
            notices += [m["text"] for m in new if m["text"] and not m["text"].startswith(SKIP_NOTICES) and not echo(uid, m["text"])]
            continue
        if not wants(p, "messages"):
            continue
        if conv["kind"] == "group" or len({m["author_user_id"] for m in new}) > 1:
            head = f"💬 <b>{escape(conv.get('title') or 'Новые сообщения')}</b>"
            text = "\n\n".join(f"<b>{escape(m['author_name'])}:</b> {body(m)}" for m in new)
        else:
            head = f"💬 <b>{escape(new[0]['author_name'])}</b>"
            text = "\n\n".join(body(m) for m in new)
        await send(bot, uid, short(f"{head}\n{text}", 4000), pvolunteer.reply_kb(conv["id"]), until=later)
    if notices:  # уведомления фонда: сайт уже проверил согласие и тихие часы, шлём одним сообщением
        text = f"🔔 {escape(notices[0])}" if len(notices) == 1 else "🔔 <b>Новое от фонда</b>\n\n" + "\n\n".join(escape(t) for t in notices)
        await send(bot, uid, short(text, 4000), pvolunteer.site_kb("Открыть сообщения", "/messages"), until=later)


# --- занятия и собеседования -----------------------------------------------------------------------

async def schedule(bot: Bot, u, p: dict) -> None:
    uid, n = u["id"], db.now()
    if not wants(p, "assignments"):
        return
    later = quiet_until(p)
    items = await pvolunteer.schedule(uid, days=90, state="all")  # приглашения бывают и на месяц-два вперёд
    fresh = []
    for a in items:
        if a["status"] == "invited" and local(a["starts_at"]) > n and not db.was_sent(f"p:inv:{a['id']}") \
                and await pvolunteer.answerable(uid, a):
            a["answerable"] = True
            db.mark_sent(f"p:inv:{a['id']}")
            fresh.append(a)
    if len(fresh) == 1:
        await send(bot, uid, pvolunteer.invite_text(fresh[0]), pvolunteer.invite_kb(fresh[0]), until=later)
    elif fresh:  # несколько приглашений сразу — одно сообщение со списком, а не пачка карточек
        b = InlineKeyboardBuilder()
        for a in fresh[:10]:
            b.button(text=short(f"Ответить: {local(a['starts_at']):%d.%m} {a['title']}", 60), callback_data=PA(action="open", aid=a["id"]))
        b.adjust(1)
        lines = [f"<b>{escape(a['title'])}</b>\n{when(a['starts_at'], a['ends_at'])}, {pvolunteer.place(a)}" for a in fresh[:10]]
        await send(bot, uid, short(f"Вас приглашают на занятия ({len(fresh)}):\n\n" + "\n\n".join(lines), 4000), b.as_markup(), until=later)
    for a in items:
        if a["status"] != "confirmed" or a["occurrence_status"] != "scheduled":
            continue
        start, end, evening = local(a["starts_at"]), local(a["ends_at"]), pvolunteer.evening_before(a)
        # кто подтвердил участие в последний момент, только что получил всё в ответ на «Приду»
        late = a.get("confirmed_at") and local(a["confirmed_at"]) >= evening - timedelta(hours=6)
        if evening <= n < start and not late and db.mark_sent(f"p:rem:{a['id']}"):
            await send(bot, uid, f"Завтра ждём вас: <b>{escape(a['title'])}</b>, {when(a['starts_at'], a['ends_at'])}, "
                                 f"{pvolunteer.place(a)}.", pvolunteer.invite_kb(a), until=later)
        if end + timedelta(hours=2) <= n < end + timedelta(days=2) and not db.was_sent(f"p:after:{a['id']}"):
            r = await platform.get(uid, f"/me/assignments/{a['id']}/reflection")
            if r["can_submit"] and not r["submitted_at"] and db.mark_sent(f"p:after:{a['id']}"):
                await send(bot, uid, f"Как прошло «{escape(a['title'])}»? Ответ увидит только координатор.",
                           pvolunteer.mood_kb(a["id"]), until=later)


async def interviews(bot: Bot, u, p: dict) -> None:
    uid, n = u["id"], db.now()
    if not wants(p):
        return
    for m in await platform.get(uid, "/me/interviews"):
        if m["status"] != "booked":
            continue
        left = local(m["starts_at"]) - n
        where = escape(m["venue"] or "онлайн")
        if timedelta(minutes=0) < left <= timedelta(minutes=20) and db.mark_sent(f"p:mt15:{m['id']}:{m['starts_at']}"):
            kb = None
            if m.get("join_url"):
                b = InlineKeyboardBuilder()
                b.button(text="Подключиться", url=m["join_url"])
                kb = b.as_markup()
            await send(bot, uid, f"Через {max(1, int(left.total_seconds() // 60))} мин собеседование с координатором. {where}.",
                       kb, urgent=True)
        elif timedelta(hours=2) < left <= timedelta(hours=24) and db.mark_sent(f"p:mt24:{m['id']}:{m['starts_at']}"):
            await send(bot, uid, f"🤝 Напоминаем о собеседовании с координатором: {when(m['starts_at'], m['ends_at'])}, {where}.\n"
                                 "Если планы поменялись, перенести или отменить можно в разделе «Собеседование».",
                       until=quiet_until(p))


async def digest(bot: Bot, u, p: dict) -> None:
    n = db.now()
    if not (u["is_coordinator"] and platform.is_staff(u["id"])) or n.hour < 10:
        return
    if not db.mark_sent(f"p:digest:{u['id']}:{n.date().isoformat()}"):
        return
    d = await pcoordinator.collect(u["id"])
    count = pcoordinator.todo_count(d)
    pcoordinator.remember_todo(u["id"], count)
    if not (count or d["upcoming"]):
        return
    text = f"☀️ Доброе утро! Нужно решить: {count}." if count else "☀️ Доброе утро! Решать сегодня ничего не нужно."
    if d["upcoming"]:
        text += f" Собеседований в ближайшие два дня: {len(d['upcoming'])}."
    b = InlineKeyboardBuilder()
    b.button(text="Открыть ленту", callback_data=ui.MenuCB(item="feed"))
    await send(bot, u["id"], text, b.as_markup())


async def tick(bot: Bot, minute: int) -> None:
    try:
        await flush_outbox(bot)
    except Exception:  # noqa: BLE001
        log.exception("outbox failed")
    for u in linked_users():
        jobs = [messages, digest] + ([schedule, interviews] if minute % SLOW_EVERY == 0 else [])
        try:
            p = await prefs(u["id"])
        except NotLinked:
            p = None
        except PlatformError as e:
            log.warning("настройки для %s: %s", u["id"], e)
            continue
        for job in jobs if p is not None else []:
            try:
                await job(bot, u, p)
            except NotLinked:
                p = None
                break
            except PlatformError as e:  # сайт недоступен или не принял запрос — попробуем в следующую минуту
                log.warning("%s для %s: %s", job.__name__, u["id"], e)
            except Exception:  # noqa: BLE001 — одна сломанная проверка не должна останавливать остальные
                log.exception("job %s failed", job.__name__)
        if p is None:
            db.update_user(u["id"], status="new", is_coordinator=0)
            platform.forget(u["id"])
            _prefs.pop(u["id"], None)


async def loop(bot: Bot) -> None:
    minute = 0
    while True:
        await tick(bot, minute)
        minute += 1
        await asyncio.sleep(60)
