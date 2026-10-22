"""One bucket table serves 60 s, 300 s and 3600 s limits; cleanup must respect each window."""
import time
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from app.core import rate_limit as module
from app.core.crypto import digest
from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.models import RateLimitBucket
from app.core.rate_limit import rate_limit

@pytest.fixture
def frozen(monkeypatch):
    # Mid-hour, so no 60/300/3600 s window rolls over inside the test.
    now=int(time.time())//3600*3600+1830
    monkeypatch.setattr(module,'time',SimpleNamespace(time=lambda:now))
    return now

@pytest.mark.asyncio
@pytest.mark.parametrize('seconds,shorter',[(300,60),(3600,60),(3600,300)])
async def test_shorter_window_call_keeps_live_longer_bucket(frozen,seconds,shorter):
    async with SessionLocal() as db:
        for _ in range(2):await rate_limit(db,'fixture-actor','fixture.long',limit=2,seconds=seconds)
        await db.commit()
        await rate_limit(db,'fixture-other','fixture.short',limit=5,seconds=shorter);await db.commit()
        with pytest.raises(ApiError) as error:await rate_limit(db,'fixture-actor','fixture.long',limit=2,seconds=seconds)
        assert error.value.status_code==429

@pytest.mark.asyncio
async def test_cleanup_drops_only_ended_and_legacy_window_rows(frozen):
    async with SessionLocal() as db:
        db.add_all([RateLimitBucket(key='legacy-window-index',window=5975437,count=9),RateLimitBucket(key='ended-window',window=frozen,count=9),RateLimitBucket(key='live-window',window=frozen+1,count=9)])
        await db.commit()
        await rate_limit(db,'fixture-actor','fixture.cleanup',seconds=3600);await db.commit()
        keys=set((await db.scalars(select(RateLimitBucket.key))).all())
        assert keys=={'live-window',digest(f'fixture-actor:fixture.cleanup:3600:{frozen//3600}')}
        assert await db.scalar(select(RateLimitBucket.window).where(RateLimitBucket.key!='live-window'))==(frozen//3600+1)*3600
