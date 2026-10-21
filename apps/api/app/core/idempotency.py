import hashlib
import json
from sqlalchemy import select, text
from app.core.errors import ApiError
from app.core.models import MutationReceipt

def payload_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()).hexdigest()

async def begin_command(db, principal, operation, key, payload):
    if not key or len(key) > 128:
        raise ApiError(428, "idempotency_key_required", "Требуется Idempotency-Key длиной до 128 символов")
    lock = int.from_bytes(hashlib.sha256(f"{principal.actor_id}:{operation}:{key}".encode()).digest()[:8], "big", signed=True)
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock})
    receipt = await db.scalar(select(MutationReceipt).where(MutationReceipt.actor_id == principal.actor_id, MutationReceipt.operation == operation, MutationReceipt.key == key))
    expected = payload_hash(payload)
    if receipt:
        if receipt.payload_hash != expected:
            raise ApiError(409, "idempotency_payload_conflict", "Этот ключ уже использован с другими данными")
        return receipt.result
    db.add(MutationReceipt(actor_id=principal.actor_id, operation=operation, key=key, payload_hash=expected))
    await db.flush()
    return None

async def finish_command(db, principal, operation, key, result):
    receipt = await db.scalar(select(MutationReceipt).where(MutationReceipt.actor_id == principal.actor_id, MutationReceipt.operation == operation, MutationReceipt.key == key))
    receipt.result = result
    await db.flush()
    return result
