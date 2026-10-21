import json
from datetime import timedelta
from uuid import uuid4
from sqlalchemy import and_, or_, select, update
from app.core.models import Job, OutboxMessage
from app.core.clock import utcnow
from app.core.crypto import seal

class LeaseLost(RuntimeError):
    pass

def enqueue_job(db, foundation_id, kind, payload, **kwargs):
    job = Job(id=uuid4(), foundation_id=foundation_id, kind=kind, payload=payload, **kwargs)
    db.add(job)
    return job

def enqueue_outbox(db, foundation_id, channel, payload):
    message = OutboxMessage(id=uuid4(), foundation_id=foundation_id, channel=channel, payload_cipher=seal(json.dumps(payload)))
    job = enqueue_job(db, foundation_id, "outbox.deliver", {"outbox_id": str(message.id)})
    message.job_id = job.id
    db.add(message)
    return message

async def claim(db, kinds=None, lease_seconds=60):
    now = utcnow()
    query = select(Job).where(or_(and_(Job.state == "queued", Job.available_at <= now), and_(Job.state == "running", Job.lease_until < now)), Job.attempts < Job.max_attempts).order_by(Job.available_at, Job.id).with_for_update(skip_locked=True).limit(1)
    if kinds is not None:
        query = query.where(Job.kind.in_(kinds))
    job = await db.scalar(query)
    if not job:
        return None
    job.state, job.claim_token, job.lease_until = "running", uuid4(), now + timedelta(seconds=lease_seconds)
    job.attempts += 1
    await db.flush()
    return job

async def fenced_update(db, job_id, token, **values):
    result = await db.execute(update(Job).where(Job.id == job_id, Job.claim_token == token, Job.state == "running", Job.lease_until > utcnow()).values(**values).returning(Job.id))
    if result.scalar_one_or_none() is None:
        raise LeaseLost("lease_lost")

async def heartbeat(db, job_id, token, lease_seconds=60):
    await fenced_update(db, job_id, token, lease_until=utcnow() + timedelta(seconds=lease_seconds))

async def complete(db, job_id, token, result=None):
    await fenced_update(db, job_id, token, state="succeeded", result=result or {}, lease_until=None)

async def retry(db, job_id, token, error_code, attempts, max_attempts):
    await fenced_update(db, job_id, token, state="dead" if attempts >= max_attempts else "queued", available_at=utcnow()+timedelta(seconds=min(300, 2**attempts)), lease_until=None, error_code=error_code)
