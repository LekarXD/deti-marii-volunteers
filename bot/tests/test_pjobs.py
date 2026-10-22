"""Фоновые задачи с платформой без сети и Telegram: python -m tests.test_pjobs (из папки bot/).

Сайт подменён словарём ответов, отправка в Telegram — списком. Проверяем, что бот не засыпает человека
сообщениями: пачка сообщений разговора — одно сообщение, уведомления сайта о том, что бот уже показал,
не дублируются, несколько приглашений приходят списком, согласия и тихие часы с сайта соблюдаются.
"""
import asyncio
import os
import tempfile
from datetime import datetime, timedelta

os.environ.update(DB_PATH=os.path.join(tempfile.mkdtemp(), "pjobs.db"), BOT_TOKEN="1:test", QUIET_HOURS="off",
                  OPORA_URL="http://platform.test", OPORA_BOT_API_SECRET="s" * 40, OPORA_WEBHOOK_SECRET="h" * 40)

from io import BytesIO  # noqa: E402

from aiogram.types import Chat, Message  # noqa: E402
from openpyxl import load_workbook  # noqa: E402

from opora_bot import db, exports, pjobs, platform, pvolunteer  # noqa: E402
from opora_bot.config import TZ  # noqa: E402

UID, SITE_ID, COORD = 200, "user-anna", "user-maria"
sent: list[tuple[str, object, object]] = []
site: dict[str, object] = {}
puts: list[tuple[str, dict]] = []


async def fake_send(bot, chat_id, text, markup=None, urgent=False, photo=None, until=None):
    sent.append((text, markup, until))
    return True


async def fake_get(uid, path, **params):
    value = site[path]
    return value(params) if callable(value) else value


async def fake_put(uid, path, body):
    puts.append((path, body))
    site[path] = {**site[path], **body, "version": site[path]["version"] + 1}
    return site[path]


pjobs.send = fake_send
platform.get, platform.put = fake_get, fake_put


def iso(dt: datetime) -> str:
    return dt.astimezone(TZ).isoformat()


def prefs(**over) -> dict:
    return {"no_contact": False, "effective_no_contact": False, "topics": {"assignments": True, "messages": True, "news": False},
            "quiet_enabled": False, "quiet_from": 1320, "quiet_to": 540, "timezone": "Europe/Moscow", **over}


def msg(seq, text, author=COORD, name="Мария"):
    return {"seq": seq, "text": text, "assets": [], "author_user_id": author, "author_name": name}


async def main():
    db.init()
    u = {"id": UID, "site_id": SITE_ID, "is_coordinator": 0}

    # --- сообщения: первый проход только запоминает, дальше пачка разговора — одно сообщение
    site["/conversations"] = {"items": [{"id": "c1", "kind": "direct", "title": "", "last_seq": 2},
                                        {"id": "s1", "kind": "system", "title": "Уведомления фонда", "last_seq": 1}]}
    await pjobs.messages(None, u, prefs())
    assert not sent, sent
    site["/conversations"] = {"items": [{"id": "c1", "kind": "direct", "title": "", "last_seq": 5},
                                        {"id": "s1", "kind": "system", "title": "Уведомления фонда", "last_seq": 5}]}
    a = {"title": "Арт-суббота", "starts_at": "2026-10-25T08:00:00+00:00"}
    db.mark_sent(pvolunteer.echo_key(UID, "Участие отменено", a))  # человек сам отменил участие в боте
    site["/conversations/c1/sync"] = {"messages": [msg(3, "Привет!"), msg(4, "Сможете в субботу?"), msg(5, "Моё", SITE_ID, "Анна")],
                                      "next_after_seq": 5, "has_more": False}
    site["/conversations/s1/sync"] = {"messages": [
        msg(2, "Приглашение на занятие. Арт-суббота. 25.10.2026 в 11:00 МСК. Студия", None, ""),
        msg(3, "Участие подтверждено. Арт-суббота. 25.10.2026 в 11:00 МСК. Студия", None, ""),
        msg(4, "Участие отменено. Арт-суббота. 25.10.2026 в 11:00 МСК. Студия", None, ""),
        msg(5, "Новости фонда\nВ субботу ярмарка", None, "")], "next_after_seq": 5, "has_more": False}
    await pjobs.messages(None, u, prefs())
    assert len(sent) == 2, [s[0] for s in sent]
    chat, notice = sent[0][0], sent[1][0]
    assert "Мария" in chat and "Привет!" in chat and "Сможете в субботу?" in chat and "Моё" not in chat, chat
    assert "ярмарка" in notice and "Приглашение" not in notice and "подтверждено" not in notice and "отменено" not in notice, notice
    sent.clear()
    await pjobs.messages(None, u, prefs())
    assert not sent, "уже пересланное не повторяется"

    # тема «Сообщения» выключена на сайте — переписку не пересылаем
    site["/conversations"] = {"items": [{"id": "c1", "kind": "direct", "title": "", "last_seq": 6}]}
    site["/conversations/c1/sync"] = {"messages": [msg(6, "Ещё вопрос")], "next_after_seq": 6, "has_more": False}
    await pjobs.messages(None, u, prefs(topics={"assignments": True, "messages": False}))
    assert not sent, sent

    # --- приглашения: три сразу — одно сообщение со списком; повторно не приходят; «не беспокоить» соблюдается
    soon = datetime.now(TZ) + timedelta(days=3)
    items = [{"id": f"a{i}", "status": "invited", "title": f"Занятие {i}", "role_title": "Помощник", "location": "Студия",
              "starts_at": iso(soon + timedelta(days=i)), "ends_at": iso(soon + timedelta(days=i, hours=2)),
              "allowed_actions": ["confirm", "decline"], "approved_at": iso(soon), "occurrence_status": "scheduled",
              "staffing_need_id": f"n{i}", "occurrence_id": f"o{i}"} for i in range(3)]
    site["/me/schedule"] = {"items": items}
    await pjobs.schedule(None, u, prefs(effective_no_contact=True))
    assert not sent, "просил не беспокоить"
    await pjobs.schedule(None, u, prefs())
    assert len(sent) == 1 and "(3)" in sent[0][0], [s[0] for s in sent]
    assert len(sent[0][1].inline_keyboard) == 3, sent[0][1]
    sent.clear()
    await pjobs.schedule(None, u, prefs())
    assert not sent, "приглашения не повторяются"

    # приглашение без согласования: ответить нельзя, пока роль требует согласования координатора
    site["/me/schedule"] = {"items": [{**items[0], "id": "b1", "approved_at": None, "staffing_need_id": "nb", "occurrence_id": "ob"}]}
    site["/me/events/ob"] = {"needs": [{"id": "nb", "approval_policy": "coordinator"}]}
    await pjobs.schedule(None, u, prefs())
    assert not sent, sent
    site["/me/schedule"] = {"items": [{**items[0], "id": "b2", "approved_at": None, "staffing_need_id": "ns", "occurrence_id": "os"}]}
    site["/me/events/os"] = {"needs": [{"id": "ns", "approval_policy": "self_confirmation"}]}
    await pjobs.schedule(None, u, prefs())
    assert len(sent) == 1 and "Приду" in [b.text for row in sent[0][1].inline_keyboard for b in row], sent
    sent.clear()

    # --- тихие часы человека: сообщение откладывается до их конца
    now = datetime.now(TZ)
    start = (now.hour * 60 + now.minute - 30) % 1440
    end = (start + 120) % 1440
    until = pjobs.quiet_until(prefs(quiet_enabled=True, quiet_from=start, quiet_to=end))
    assert until and timedelta(0) < until - now <= timedelta(minutes=91), (until, now)
    assert pjobs.quiet_until(prefs(quiet_enabled=False)) is None

    # --- «Как прошло?»: второй шаг не стирает настроение и текст, написанный на сайте
    site["/me/assignments/x/reflection"] = {"version": 3, "can_submit": True, "mood": None, "text": "Черновик с сайта", "unexpected": "",
                                            "help": "later", "help_text": "", "continuation": "discuss", "restricted": False}
    await pvolunteer.save_reflection(UID, "x", mood="hard")
    r = await pvolunteer.save_reflection(UID, "x", continuation="pause")
    assert r["mood"] == "hard" and r["text"] == "Черновик с сайта" and r["continuation"] == "pause", r
    assert set(puts[0][1]) == set(pvolunteer.REFLECTION_FIELDS) | {"expected_version"}, puts[0][1]

    # --- ввод в шагах диалога не перехватывает команды (ссылка /start bind_… из профиля)
    m = lambda t: Message(message_id=1, date=datetime.now(), chat=Chat(id=1, type="private"), text=t)  # noqa: E731
    assert pvolunteer.TEXT.resolve(m("Добрый день")) and not pvolunteer.TEXT.resolve(m("/start bind_x"))

    # --- Excel: название события с двоеточием — нормальный лист, имя «=…» — текст, а не формула
    book = load_workbook(BytesIO(exports._book("Мастер-класс: керамика", ["Имя"], [["=HYPERLINK(\"x\")"]])))
    sheet = book.active
    assert sheet.title == "Мастер-класс  керамика" and sheet["A2"].data_type == "s", (sheet.title, sheet["A2"].data_type)
    print("PASS: пачка сообщений разговора одним сообщением, без дублей уведомлений сайта и эха своих действий, "
          "тема «Сообщения» и «не беспокоить», приглашения списком и без повторов, согласование роли, "
          "тихие часы человека, «Как прошло?» не теряет ответов, команды не попадают в ввод, Excel без формул из имён")


asyncio.run(main())
