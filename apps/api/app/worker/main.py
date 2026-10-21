"""Run as python -m app.worker.main. Unknown external delivery is never marked sent."""
import asyncio
from uuid import UUID
from app.core.db import SessionLocal
from app.core.models import OutboxMessage
from app.core.config import get_settings
from app.worker.queue import claim, complete, retry

async def run_once():
    async with SessionLocal() as db:
        job = await claim(db)
        await db.commit()
        if job is None:
            return False
        try:
            if job.kind == "outbox.deliver":
                message = await db.get(OutboxMessage, UUID(job.payload["outbox_id"]))
                if get_settings().environment == "development" and get_settings().dev_inbox:
                    message.state = "dev_inbox"
                    await complete(db, job.id, job.claim_token, {"delivery": "dev_inbox"})
                else:
                    message.state = "unavailable"
                    await retry(db, job.id, job.claim_token, "provider_unavailable", job.attempts, job.max_attempts)
            else:
                await retry(db, job.id, job.claim_token, "handler_unavailable", job.attempts, job.max_attempts)
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        return True

async def main():
    while True:
        if not await run_once():
            await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(main())
