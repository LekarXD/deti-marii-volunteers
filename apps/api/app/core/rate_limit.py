import time
from sqlalchemy.dialects.postgresql import insert
from app.core.models import RateLimitBucket
from app.core.crypto import digest
from app.core.errors import ApiError

async def rate_limit(db, identity, operation, limit=10, seconds=300):
    window = int(time.time()) // seconds
    key = digest(f"{identity}:{operation}:{window}")
    statement = insert(RateLimitBucket).values(key=key, window=window, count=1).on_conflict_do_update(index_elements=[RateLimitBucket.key], set_={"count": RateLimitBucket.count + 1}).returning(RateLimitBucket.count)
    count = (await db.execute(statement)).scalar_one()
    if count > limit:
        await db.commit()
        raise ApiError(429, "rate_limited", "Слишком много попыток. Попробуйте позже", retryable=True)
