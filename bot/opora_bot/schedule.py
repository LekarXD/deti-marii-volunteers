"""Даты событий: разовые, многодневные и еженедельные серии."""
import json
from datetime import date, datetime, timedelta

from .config import TZ

WEEKDAYS = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]


def d(s: str) -> date:
    return date.fromisoformat(s)


def occurs(ev, day: date) -> bool:
    start = d(ev["start_date"])
    if day < start or day.isoformat() in json.loads(ev["cancelled_dates"] or "[]"):
        return False
    if ev["repeat"] == "weekly":
        end = d(ev["end_date"]) if ev["end_date"] else None
        if end and day > end:
            return False
        days = [int(x) for x in (ev["weekdays"] or "").split(",") if x != ""]
        return day.weekday() in days
    end = d(ev["end_date"]) if ev["end_date"] else start
    return start <= day <= end


def occurrences(events, start: date, end: date):
    """Список (событие, дата) в периоде, по времени начала."""
    out = []
    day = start
    while day <= end:
        for ev in events:
            if occurs(ev, day):
                out.append((ev, day))
        day += timedelta(days=1)
    return sorted(out, key=lambda x: (x[1], x[0]["time"] or "99"))


def human(day: date, with_weekday: bool = True) -> str:
    text = f"{day.day} {MONTHS[day.month - 1]}"
    return f"{WEEKDAYS[day.weekday()]}, {text}" if with_weekday else text


def time_range(ev) -> str:
    if not ev["time"]:
        return "время уточняется"
    return f"{ev['time']}–{ev['end_time']}" if ev["end_time"] else f"с {ev['time']}"


def starts_at(ev, day: date) -> datetime:
    hh, mm = (ev["time"] or "10:00").split(":")
    return datetime(day.year, day.month, day.day, int(hh), int(mm), tzinfo=TZ)


def ends_at(ev, day: date) -> datetime | None:
    if not ev["end_time"]:
        return None
    hh, mm = ev["end_time"].split(":")
    return datetime(day.year, day.month, day.day, int(hh), int(mm), tzinfo=TZ)


def duration_hours(ev) -> float | None:
    if not ev["time"] or not ev["end_time"]:
        return None
    a = datetime.strptime(ev["time"], "%H:%M")
    b = datetime.strptime(ev["end_time"], "%H:%M")
    return round((b - a).seconds / 3600, 1)


def parse_day(text: str, today: date) -> date | None:
    """«24.10», «24.10.2026» или «2026-10-24»."""
    text = text.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    try:
        dm = datetime.strptime(text, "%d.%m")
    except ValueError:
        return None
    guess = date(today.year, dm.month, dm.day)
    return guess if guess >= today - timedelta(days=1) else date(today.year + 1, dm.month, dm.day)
