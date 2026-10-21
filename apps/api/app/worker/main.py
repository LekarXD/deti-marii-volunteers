"""Run as python -m app.worker.main. Unknown external delivery is never marked sent."""
import asyncio
import argparse
import json
from datetime import timedelta
from app.core.clock import utcnow
from app.core.crypto import unseal
from app.worker.queue import fenced_update
from uuid import UUID
from app.core.db import SessionLocal
from app.core.models import OutboxMessage
from app.core.config import get_settings
from app.worker.queue import claim, complete, retry, LeaseLost

async def run_once(kinds=None):
    async with SessionLocal() as db:
        from app.worker.registry import HANDLERS, load_extensions, run_handler
        load_extensions()
        kinds=kinds if kinds is not None else get_settings().worker_kinds
        if not kinds or len(kinds)>32:
            raise RuntimeError("An explicit bounded worker kind filter is required")
        lease=max([HANDLERS[k].lease_seconds for k in kinds if k in HANDLERS]+[60])
        job = await claim(db,kinds=kinds,lease_seconds=lease)
        await db.commit()
        if job is None:
            return False
        job_id,token,attempts,max_attempts=job.id,job.claim_token,job.attempts,job.max_attempts
        try:
            if job.kind == "outbox.deliver":
                message = await db.get(OutboxMessage, UUID(job.payload["outbox_id"]))
                payload=json.loads(unseal(message.payload_cipher))
                if message.channel in ("internal","in_app"):
                    from app.modules.notifications.delivery import process_internal
                    state=await process_internal(db,job,message,payload)
                    message.state=state
                    if state=="waiting_identity":
                        await fenced_update(db,job.id,job.claim_token,state="queued",attempts=max(0,job.attempts-1),available_at=utcnow()+timedelta(minutes=5),lease_until=None)
                    else:
                        await complete(db,job.id,job.claim_token,{"delivery":state})
                elif message.channel=="email":
                    from app.modules.notifications.delivery import process_email
                    result=await process_email(db,job,message,payload)
                    message.state=result.state
                    if result.state=="unavailable":
                        await retry(db,job.id,job.claim_token,result.error_code or "provider_unavailable",job.attempts,job.max_attempts)
                    else:
                        # Unknown SMTP outcomes are terminal and never retried blindly.
                        await complete(db,job.id,job.claim_token,{"delivery":result.state})
                else:
                    message.state="unavailable"
                    await retry(db,job.id,job.claim_token,"channel_unavailable",job.attempts,job.max_attempts)
            elif job.kind in HANDLERS:
                result=await run_handler(db,job,HANDLERS[job.kind])
                await complete(db,job.id,job.claim_token,result)
            else:
                await retry(db, job.id, job.claim_token, "handler_unavailable", job.attempts, job.max_attempts)
            await db.commit()
        except LeaseLost:
            await db.rollback()
        except Exception:
            await db.rollback()
            try:
                await retry(db,job_id,token,"handler_failed",attempts,max_attempts)
                await db.commit()
            except LeaseLost:
                await db.rollback()
        return True

async def main(kinds=None):
    while True:
        try:
            if not await run_once(kinds):
                await asyncio.sleep(1)
        except Exception:
            # No job payload, contact or token is logged; durable leases recover outages.
            await asyncio.sleep(1)

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--kind",action="append")
    args=parser.parse_args()
    asyncio.run(main(args.kind))
