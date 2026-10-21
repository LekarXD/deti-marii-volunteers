"""Выгрузки: Excel для координатора и .ics для календаря волонтёра."""
from datetime import date, datetime, timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Font

from . import db
from .schedule import duration_hours, ends_at, human, occurrences, starts_at, time_range
from .seed import ROLES
from .ui import STATUS_RU, USER_STATUS_RU, days_text, roles_text


def _book(title: str, header: list[str], rows: list[list]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = title[:31]
    ws.append(header)
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in rows:
        ws.append(r)
    for col in ws.columns:
        width = max(len(str(c.value or "")) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 60)
    ws.freeze_panes = "A2"
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def volunteers_xlsx() -> bytes:
    rows = []
    for u in db.all_("SELECT * FROM users WHERE status!='new' ORDER BY status, name"):
        done = db.one("SELECT COUNT(*) AS n, COALESCE(SUM(hours),0) AS h FROM invites WHERE user_id=? AND status='attended'", u["id"])
        rows.append([u["name"], u["phone"], ("@" + u["username"]) if u["username"] else "", USER_STATUS_RU.get(u["status"], u["status"]),
                     roles_text(u["roles"]), days_text(u["days"]), done["n"], done["h"], (u["created_at"] or "")[:10]])
    return _book("Волонтёры", ["Имя", "Телефон", "Telegram", "Статус", "Интересы", "Свободные дни",
                               "Занятий", "Часов", "В боте с"], rows)


def teams_xlsx(days: int = 14) -> bytes:
    today = db.now().date()
    rows = []
    for ev, day in occurrences(db.events(), today, today + timedelta(days=days)):
        team = db.team(ev["id"], day.isoformat())
        if not team:
            rows.append([day.isoformat(), ev["title"], time_range(ev), ev["place"], ev["need"], "", "", "", ""])
        for r in team:
            rows.append([day.isoformat(), ev["title"], time_range(ev), ev["place"], ev["need"], r["name"], r["phone"],
                         ("@" + r["username"]) if r["username"] else "", STATUS_RU.get(r["status"], r["status"])])
    return _book("Команды", ["Дата", "Событие", "Время", "Место", "Нужно", "Волонтёр", "Телефон", "Telegram", "Статус"], rows)


def team_xlsx(ev, day: date) -> bytes:
    rows = [[r["name"], r["phone"], ("@" + r["username"]) if r["username"] else "", STATUS_RU.get(r["status"], r["status"])]
            for r in db.team(ev["id"], day.isoformat())]
    return _book("Команда", ["Волонтёр", "Телефон", "Telegram", "Статус"], rows)


def month_bounds(today: date) -> tuple[date, date]:
    first = today.replace(day=1)
    nxt = (first + timedelta(days=32)).replace(day=1)
    return first, nxt - timedelta(days=1)


def hours_xlsx(today: date) -> bytes:
    first, last = month_bounds(today)
    rows = []
    for r in db.all_(
            "SELECT u.name, u.phone, i.event_id, i.date, i.hours FROM invites i JOIN users u ON u.id=i.user_id "
            "WHERE i.status='attended' AND i.date BETWEEN ? AND ? ORDER BY u.name, i.date", first.isoformat(), last.isoformat()):
        ev = db.event(r["event_id"])
        rows.append([r["name"], r["phone"], r["date"], ev["title"] if ev else r["event_id"], r["hours"]])
    return _book("Часы", ["Волонтёр", "Телефон", "Дата", "Событие", "Часов"], rows)


def month_summary(today: date) -> str:
    first, last = month_bounds(today)
    occ = [(e, d) for e, d in occurrences(db.events(), first, min(last, today))]
    with_need = [(e, d) for e, d in occ if e["need"]]
    short = [(e, d) for e, d in with_need if db.confirmed_count(e["id"], d.isoformat()) < e["need"]]
    went = db.one("SELECT COUNT(DISTINCT user_id) AS n, COALESCE(SUM(hours),0) AS h FROM invites "
                  "WHERE status='attended' AND date BETWEEN ? AND ?", first.isoformat(), last.isoformat())
    late = db.all_("SELECT i.*, u.name FROM invites i JOIN users u ON u.id=i.user_id WHERE i.status='declined' "
                   "AND i.date BETWEEN ? AND ?", first.isoformat(), last.isoformat())
    late_names = []
    for r in late:
        ev = db.event(r["event_id"])
        if not ev or not r["answered_at"]:
            continue
        day = date.fromisoformat(r["date"])
        if starts_at(ev, day) - datetime.fromisoformat(r["answered_at"]) < timedelta(hours=24):
            late_names.append(f"{r['name']} — {ev['title']}, {human(day, False)}")
    lines = [f"<b>Итоги с {human(first, False)} по {human(min(last, today), False)}</b>",
             f"Событий: {len(occ)}, из них с волонтёрами: {len(with_need)}",
             f"Вышли волонтёров: {went['n']}, часов: {went['h']:g}",
             f"Не хватало людей: {len(short)}"]
    lines += [f"• {e['title']}, {human(d, False)} — {db.confirmed_count(e['id'], d.isoformat())} из {e['need']}" for e, d in short[:10]]
    lines.append(f"Отказались меньше чем за сутки: {len(late_names)}")
    lines += [f"• {x}" for x in late_names[:10]]
    return "\n".join(lines)


def ics(items) -> bytes:
    """items: список (событие, дата)."""
    out = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Deti Marii//Opora bot//RU", "CALSCALE:GREGORIAN"]
    for ev, day in items:
        start = starts_at(ev, day)
        end = ends_at(ev, day) or start + timedelta(hours=duration_hours(ev) or 2)
        fmt = "%Y%m%dT%H%M%S"
        out += ["BEGIN:VEVENT", f"UID:{ev['id']}-{day.isoformat()}@detimarie_bot",
                f"DTSTAMP:{db.now().strftime(fmt)}",
                f"DTSTART;TZID=Europe/Moscow:{start.strftime(fmt)}", f"DTEND;TZID=Europe/Moscow:{end.strftime(fmt)}",
                f"SUMMARY:{ev['title']} — фонд «Дети Марии»", f"LOCATION:{(ev['place'] or '').replace(',', chr(92) + ',')}",
                f"DESCRIPTION:{ROLES.get(ev['role'], '')}", "END:VEVENT"]
    out.append("END:VCALENDAR")
    return "\r\n".join(out).encode("utf-8")
