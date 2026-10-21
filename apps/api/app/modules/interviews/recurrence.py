"""Pure local recurrence expansion. The stored origin never changes on override."""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc

def local_instant(day: date, minute: int, zone: str) -> datetime | None:
    naive = datetime.combine(day, time()) + timedelta(minutes=minute)
    z = ZoneInfo(zone)
    # Nonexistent DST wall times are skipped. Ambiguous times consistently use fold=0.
    aware = naive.replace(tzinfo=z, fold=0)
    if aware.astimezone(UTC).astimezone(z).replace(tzinfo=None) != naive:
        return None
    return aware.astimezone(UTC)

def matches(series, day: date) -> bool:
    if day < series.local_start_date or (series.last_date and day > series.last_date): return False
    if series.recurrence == "once": return day == series.local_start_date
    weekdays = series.weekdays or [series.local_start_date.weekday()]
    anchor_monday = series.local_start_date - timedelta(days=series.local_start_date.weekday())
    return day.weekday() in weekdays and ((day - anchor_monday).days // 7) % series.interval_weeks == 0

def expand(series, start: date, end: date, exceptions=()):
    overrides = {e.origin_date: e for e in exceptions}
    day = max(start, series.local_start_date)
    while day <= end:
        if matches(series, day):
            exc = overrides.get(day)
            if not exc or exc.kind != "skip":
                first = exc.start_minute if exc and exc.kind == "override" else series.start_minute
                last = exc.end_minute if exc and exc.kind == "override" else series.end_minute
                minute = first
                while minute + series.duration_minutes <= last:
                    a = local_instant(day, minute, series.timezone)
                    b = local_instant(day, minute + series.duration_minutes, series.timezone)
                    if a is not None and b is not None and b > a:
                        yield day, minute, a, b, b + timedelta(minutes=series.buffer_after_minutes)
                    minute += series.duration_minutes + series.buffer_after_minutes
        day += timedelta(days=1)
