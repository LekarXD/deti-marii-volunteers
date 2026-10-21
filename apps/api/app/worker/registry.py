"""Explicit durable job extension points; media never joins the default I/O worker."""
import asyncio
import importlib
from dataclasses import dataclass
from typing import Awaitable, Callable, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app.core.config import get_settings
from app.worker.queue import heartbeat, fenced_update, LeaseLost

@dataclass(frozen=True)
class JobContext:
    job_id: UUID
    claim_token: UUID
    foundation_id: UUID
    payload: dict
    async def fence(self, db):
        await fenced_update(db,self.job_id,self.claim_token,state="running")

@dataclass(frozen=True)
class HandlerSpec:
    handler: Callable[..., Awaitable[dict]]
    lease_seconds: int
    heartbeat_seconds: int
    timeout_seconds: int
    workload: str

HANDLERS: dict[str, HandlerSpec] = {}

def register_handler(kind, handler, *, lease_seconds=120, heartbeat_seconds=30, timeout_seconds=300, workload="io"):
    if workload not in ("io","media") or not 10<=lease_seconds<=3600 or not 1<=heartbeat_seconds<lease_seconds/2 or not 1<=timeout_seconds<=21600:
        raise ValueError("invalid_worker_budget")
    if kind in HANDLERS and HANDLERS[kind].handler is not handler:
        raise ValueError("duplicate_job_handler")
    if len(HANDLERS)>=64 and kind not in HANDLERS:
        raise ValueError("handler_budget_exceeded")
    HANDLERS[kind]=HandlerSpec(handler,lease_seconds,heartbeat_seconds,timeout_seconds,workload)

def load_extensions():
    # An explicit source-controlled allowlist; never import code named in a job payload.
    for name in ("app.modules.studio.jobs","app.modules.knowledge.jobs","app.modules.simulator.jobs","app.modules.profile.jobs","app.modules.reporting.jobs","app.modules.followups.jobs"):
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name not in (name,name.rsplit(".",1)[0]):
                raise

# Heartbeats cannot be starved by domain commands occupying the regular connection pool.
heartbeat_engine=create_async_engine(get_settings().database_url,pool_size=2,max_overflow=0,pool_timeout=2,pool_pre_ping=True,hide_parameters=True)
HeartbeatSession=async_sessionmaker(heartbeat_engine,expire_on_commit=False)
# One admitted task per worker process. Additional processes are an explicit deployment choice.
admission=asyncio.Semaphore(1)

async def run_handler(db,job,spec):
    context=JobContext(job.id,job.claim_token,job.foundation_id,dict(job.payload))
    async with admission:
        async def monitor():
            while True:
                await asyncio.sleep(spec.heartbeat_seconds)
                try:
                    async with HeartbeatSession() as pulse:
                        await heartbeat(pulse,context.job_id,context.claim_token,spec.lease_seconds)
                        await pulse.commit()
                except Exception as exc:
                    raise LeaseLost("heartbeat_failed") from exc
        work=asyncio.create_task(asyncio.wait_for(spec.handler(db,context),timeout=spec.timeout_seconds))
        pulse=asyncio.create_task(monitor())
        try:
            done,_=await asyncio.wait((work,pulse),return_when=asyncio.FIRST_COMPLETED)
            if pulse in done:
                await pulse
                raise LeaseLost("lease_lost")
            result=await work
            await context.fence(db)
            return result
        finally:
            for task in (work,pulse):
                if not task.done():
                    task.cancel()
            await asyncio.gather(work,pulse,return_exceptions=True)
