from datetime import datetime, timedelta
from uuid import UUID
from app.modules.dobro.calculation import Fact, allocate, ZONE
from app.modules.dobro.schemas import dobro_url
import pytest

def test_global_daily_cap_order_overlap_and_midnight():
    person, a, b = UUID(int=1), UUID(int=2), UUID(int=3)
    start = datetime(2026, 8, 1, 8, tzinfo=ZONE)
    facts = [Fact(UUID(int=20), person, start + timedelta(hours=6), start + timedelta(hours=11), 300, b), Fact(UUID(int=10), person, start, start + timedelta(hours=6), 360, a)]
    rows = allocate(facts)
    assert [(row.activity_id, row.eligible_minutes, row.capped_minutes) for row in rows] == [(a, 360, 0), (b, 120, 180)]
    assert allocate(list(reversed(facts))) == rows
    overlapped = allocate([facts[1], Fact(UUID(int=30), person, start + timedelta(hours=5), start + timedelta(hours=8), 180, b)])
    assert overlapped[-1].overlap_minutes == 60 and overlapped[-1].eligible_minutes == 120
    late = start.replace(hour=23)
    midnight = allocate([Fact(UUID(int=40), person, late, late + timedelta(hours=3), 180, a)])
    assert [row.eligible_minutes for row in midnight] == [60, 120]

@pytest.mark.parametrize('url', ['https://dobro.ru.evil.test/volunteers/1', 'https://evil.test/?next=https://dobro.ru', 'https://user@dobro.ru/volunteers/1', 'https://dobro.ru:443/volunteers/1', 'http://dobro.ru/volunteers/1', 'https://dobro.ru\\@evil.test/volunteers/1', 'https://dobro.ru/volunteers/1?next=x', 'https://dobro.ru/volunteers/1#x', 'https://dobro.ru/volunteers/nope'])
def test_profile_url_rejects_other_origins_and_ambiguous_ids(url):
    with pytest.raises(ValueError): dobro_url(url, profile=True)

def test_profile_url_canonicalization():
    assert dobro_url(' https://dobro.ru/volunteers/123 ', profile=True) == 'https://dobro.ru/volunteers/123'
    assert dobro_url('https://добро.рф/volunteers/123', profile=True).startswith('https://xn--')
