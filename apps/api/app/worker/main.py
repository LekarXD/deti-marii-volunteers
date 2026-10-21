"""Run as python -m app.worker.main. Unknown external delivery is never marked sent."""
import asyncio
import json
from datetime import timedelta
from app.core.clock import utcnow
from app.core.crypto import unseal
from app.worker.queue import fenced_update
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
                payload=json.loads(unseal(message.payload_cipher))
                if message.channel in ("internal","in_app"):
                    from app.modules.messaging.consumers import deliver_internal
                    state=await deliver_internal(db,message,payload)
                    message.state=state
                    if state=="waiting_identity":
                        await fenced_update(db,job.id,job.claim_token,state="queued",attempts=max(0,job.attempts-1),available_at=utcnow()+timedelta(minutes=5),lease_until=None)
                    else:
                        await complete(db,job.id,job.claim_token,{"delivery":state})
                elif message.channel=="email":
                    from app.integrations.delivery.email import deliver_email
                    result=await deliver_email(payload)
                    message.state=result.state
                    if result.state=="unavailable":
                        await retry(db,job.id,job.claim_token,result.error_code or "provider_unavailable",job.attempts,job.max_attempts)
                    else:
                        # Unknown SMTP outcomes are terminal and never retried blindly.
                        await complete(db,job.id,job.claim_token,{"delivery":result.state})
                else:
                    message.state="unavailable"
                    await retry(db,job.id,job.claim_token,"channel_unavailable",job.attempts,job.max_attempts)
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
