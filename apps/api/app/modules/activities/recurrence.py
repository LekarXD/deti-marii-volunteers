"""Explicit local recurrence subset. Missing monthly dates and DST gaps are skipped."""
from calendar import monthrange
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID, uuid5
from zoneinfo import ZoneInfo
from .calendar_schemas import RecurrenceRule


def dates_in_range(start:date, rule:RecurrenceRule, lower:date, upper:date):
    lower=max(lower,start)
    if rule.until:upper=min(upper,rule.until)
    excluded=set(rule.exceptions)
    if lower>upper:return
    if rule.frequency=='once':
        if lower<=start<=upper and start not in excluded:yield start
        return
    if rule.frequency=='monthly':
        year,month=lower.year,lower.month
        while date(year,month,1)<=upper:
            if start.day<=monthrange(year,month)[1]:
                value=date(year,month,start.day)
                if lower<=value<=upper and value not in excluded:yield value
            month+=1
            if month==13:year+=1;month=1
        return
    day=lower
    anchor_monday=start-timedelta(days=start.weekday())
    while day<=upper:
        weeks=((day-timedelta(days=day.weekday()))-anchor_monday).days//7
        if day.weekday() in rule.weekdays and (rule.frequency!='biweekly' or weeks%2==0) and day not in excluded:yield day
        day+=timedelta(days=1)


def local_interval(day:date,clock:time,zone:str,duration:int):
    local=datetime.combine(day,clock)
    aware=local.replace(tzinfo=ZoneInfo(zone),fold=0)
    # Spring-forward nonexistent wall times are skipped, not silently moved.
    if aware.astimezone(timezone.utc).astimezone(ZoneInfo(zone)).replace(tzinfo=None)!=local:return None
    start=aware.astimezone(timezone.utc)
    return start,start+timedelta(minutes=duration)


def occurrence_id(series_id:UUID,origin_date:date,origin_time:time):
    return uuid5(series_id,datetime.combine(origin_date,origin_time).isoformat())
