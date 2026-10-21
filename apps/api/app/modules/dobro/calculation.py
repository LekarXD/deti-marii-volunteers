"""Deterministic minute projection; neither writes nor trusts external hour totals."""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

ZONE = ZoneInfo('Europe/Moscow')

@dataclass(frozen=True)
class Fact:
    assignment_id: UUID
    user_id: UUID
    starts_at: datetime
    ends_at: datetime
    minutes: int
    activity_id: UUID | None

@dataclass(frozen=True)
class Allocation:
    user_id: UUID
    activity_id: UUID | None
    day: date
    raw_minutes: int
    eligible_minutes: int
    capped_minutes: int
    overlap_minutes: int
    duration_trimmed_minutes: int

def allocate(facts: list[Fact]) -> list[Allocation]:
    """Earlier start, then immutable assignment UUID wins. All attendance consumes
    the same daily budget. The caller supplies only explicitly linked Dobro facts;
    an opted-out enrollment does not change the order or other activity budgets.
    The source records a duration, not actual clock-in/out: its minutes occupy the
    start of the event, conservatively excluding overlaps with earlier facts.
    """
    occupied: dict[tuple, list[tuple[datetime, datetime]]] = {}
    used: dict[tuple, int] = {}
    result = []
    for fact in sorted(facts, key=lambda item: (item.starts_at, str(item.assignment_id))):
        start = fact.starts_at.astimezone(ZONE)
        duration = max(0, int((fact.ends_at - fact.starts_at).total_seconds() // 60))
        budget = max(0, min(fact.minutes, duration))
        trimmed = max(0, fact.minutes - duration)
        cursor = start
        first = True
        while budget or (first and trimmed):
            midnight = datetime.combine(cursor.date() + timedelta(days=1), datetime.min.time(), ZONE)
            minutes = min(budget, max(0, int((midnight - cursor).total_seconds() // 60)))
            end = cursor + timedelta(minutes=minutes)
            key = (fact.user_id, cursor.date())
            segments = [(cursor, end)] if minutes else []
            for left, right in occupied.get(key, []):
                remaining = []
                for a, b in segments:
                    if b <= left or a >= right:
                        remaining.append((a, b))
                    else:
                        if a < left: remaining.append((a, left))
                        if b > right: remaining.append((right, b))
                segments = remaining
            free = sum(int((b - a).total_seconds() // 60) for a, b in segments)
            allowed = min(free, max(0, 480 - used.get(key, 0)))
            occupied.setdefault(key, []).append((cursor, end))
            used[key] = used.get(key, 0) + allowed
            extra = trimmed if first else 0
            result.append(Allocation(fact.user_id, fact.activity_id, cursor.date(), minutes + extra, allowed, free - allowed, minutes - free, extra))
            budget -= minutes
            cursor = midnight
            first = False
    return result

def month_start(value: str) -> date:
    try:
        result = date.fromisoformat(value + '-01')
        if result.strftime('%Y-%m') != value: raise ValueError()
        return result
    except (ValueError, TypeError):
        from app.core.errors import ApiError
        raise ApiError(422, 'invalid_period', 'Укажите месяц в формате ГГГГ-ММ.')

def next_month(value: date) -> date:
    try:
        return date(value.year + value.month // 12, value.month % 12 + 1, 1)
    except ValueError:
        from app.core.errors import ApiError
        raise ApiError(422, 'invalid_period', 'Выберите месяц до декабря 9999 года.')
