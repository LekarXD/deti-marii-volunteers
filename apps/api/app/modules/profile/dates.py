"""Calendar dates in the foundation's pilot timezone, independent of server TZ."""
from zoneinfo import ZoneInfo
from app.core.clock import utcnow

def local_today():
    return utcnow().astimezone(ZoneInfo('Europe/Moscow')).date()
