"""Shared pilot contact decision ordering across aliases and delivery workers."""
import hashlib
from sqlalchemy import text

async def contact_guard(db,foundation_id):
    """Acquire before CRM/domain locks; hold until decision/outbox outcome commits.

    The pilot has one foundation and low contact volume. A foundation key avoids
    resolving mutable user/application/historical-contact aliases in different
    orders. It orders new opt-outs and dispatch decisions, not previously accepted
    provider I/O or already downloaded messages.
    """
    key=int.from_bytes(hashlib.sha256(f"contact:{foundation_id}".encode()).digest()[:8],"big",signed=True)
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"),{"key":key})
