"""Run as python -m app.worker.main. Unknown external delivery is never marked sent."""
import asyncio
import argparse
import json
import signal
from datetime import timedelta
from app.core.clock import utcnow
from app.core.crypto import unseal
from app.worker.queue import fenced_update
from uuid import UUID
from app.core.db import SessionLocal
from app.core.models import OutboxMessage
from app.core.config import get_settings
from app.worker.queue import claim, complete, retry, LeaseLost

async def run_once(kinds=None,on_ready=None):
    async with SessionLocal() as db:
        from app.worker.registry import HANDLERS, load_extensions, run_handler
        load_extensions()
        kinds=kinds if kinds is not None else get_settings().worker_kinds
        if not kinds or len(kinds)>32:
            raise RuntimeError("An explicit bounded worker kind filter is required")
        lease=max([HANDLERS[k].lease_seconds for k in kinds if k in HANDLERS]+[60])
        job = await claim(db,kinds=kinds,lease_seconds=lease)
        await db.commit()
        if on_ready:on_ready()
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
                    if state in ("waiting_identity","deferred_quiet"):
                        await fenced_update(db,job.id,job.claim_token,state="queued",attempts=max(0,job.attempts-1),available_at=message.defer_until if state=="deferred_quiet" else utcnow()+timedelta(minutes=5),lease_until=None)
                    else:
                        await complete(db,job.id,job.claim_token,{"delivery":state})
                elif message.channel=="email":
                    from app.modules.notifications.delivery import process_email
                    result=await process_email(db,job,message,payload)
                    message.state=result.state
                    if result.state=="deferred_quiet":
                        await fenced_update(db,job.id,job.claim_token,state="queued",attempts=max(0,job.attempts-1),available_at=message.defer_until,lease_until=None,error_code='quiet_hours')
                    elif result.state=="unavailable":
                        await retry(db,job.id,job.claim_token,result.error_code or "provider_unavailable",job.attempts,job.max_attempts)
                    else:
                        # Unknown SMTP outcomes are terminal and never retried blindly.
                        await complete(db,job.id,job.claim_token,{"delivery":result.state})
                else:
                    message.state="unavailable"
                    await retry(db,job.id,job.claim_token,"channel_unavailable",job.attempts,job.max_attempts)
            elif job.kind in HANDLERS:
                result=await run_handler(db,job,HANDLERS[job.kind])
                # A handler may rollback a failed media transaction, expiring the ORM job.
                # Immutable claim values were copied before entering the handler.
                await complete(db,job_id,token,result)
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
    from app.worker.runtime import WorkerRuntime,live_drain,HEARTBEAT_INTERVAL
    runtime=WorkerRuntime();runtime.acquire();stopping=asyncio.Event()
    loop=asyncio.get_running_loop()
    for signum in (signal.SIGTERM,signal.SIGINT):loop.add_signal_handler(signum,stopping.set)
    runtime.publish()
    def mark_ready():
        runtime.ready=True;runtime.publish()
    async def pulse():
        while True:
            try:runtime.publish()
            except OSError:
                runtime.ready=False;stopping.set();raise
            await asyncio.sleep(HEARTBEAT_INTERVAL)
    monitor=asyncio.create_task(pulse())
    try:
        while not stopping.is_set():
            gate=live_drain(runtime.root)
            if gate:
                # Acknowledgement happens only here, after run_once returned.
                # The heartbeat never guesses that a newly requested gate is safe.
                runtime.gate=gate;runtime.active=False;runtime.publish()
            else:
                runtime.gate=None;runtime.active=True;runtime.ready=False;runtime.publish()
                try:
                    await run_once(kinds,on_ready=mark_ready)
                except Exception:
                    # No payload/contact/token logs. A failed DB claim is not ready.
                    runtime.ready=False
                finally:
                    runtime.active=False;runtime.publish()
            try:await asyncio.wait_for(stopping.wait(),timeout=1)
            except TimeoutError:pass
    finally:
        monitor.cancel();await asyncio.gather(monitor,return_exceptions=True)
        runtime.ready=False;runtime.active=False
        try:runtime.publish()
        finally:runtime.close()
        for signum in (signal.SIGTERM,signal.SIGINT):loop.remove_signal_handler(signum)

if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--kind",action="append")
    args=parser.parse_args()
    asyncio.run(main(args.kind))
