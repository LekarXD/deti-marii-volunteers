import time
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import delete, select
from app.core.models import RateLimitBucket
from app.core.crypto import digest
from app.core.errors import ApiError

def _key(identity, operation, seconds):
    window = int(time.time()) // seconds
    return window, digest(f"{identity}:{operation}:{window}")

def _rejected():
    return ApiError(429, "rate_limited", "Слишком много попыток. Попробуйте позже", retryable=True)

async def _increment(db, identity, operation, seconds):
    window, key = _key(identity, operation, seconds)
    await db.execute(delete(RateLimitBucket).where(RateLimitBucket.window < window - 2))
    statement = insert(RateLimitBucket).values(key=key, window=window, count=1).on_conflict_do_update(index_elements=[RateLimitBucket.key], set_={"count": RateLimitBucket.count + 1}).returning(RateLimitBucket.count)
    return (await db.execute(statement)).scalar_one()

async def rate_limit(db, identity, operation, limit=10, seconds=300):
    if await _increment(db, identity, operation, seconds) > limit:
        await db.commit()
        raise _rejected()

async def failure_limit(db, identity, operation, limit=10, seconds=300):
    """Rejects only after `limit` recorded failures; successful attempts never count."""
    _, key = _key(identity, operation, seconds)
    if (await db.scalar(select(RateLimitBucket.count).where(RateLimitBucket.key == key)) or 0) >= limit:
        raise _rejected()

async def record_failure(db, identity, operation, seconds=300):
    await _increment(db, identity, operation, seconds)
