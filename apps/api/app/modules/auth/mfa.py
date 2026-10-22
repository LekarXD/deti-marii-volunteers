"""TOTP / recovery code check shared by the web MFA step and the Telegram bot coordinator step."""
import pyotp
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.crypto import digest, unseal
from app.core.models import MfaFactor, MfaRecovery


async def consume_code(db, user_id, code):
    """Locks the user's factor, accepts a fresh TOTP (±30 s, never reused) or an unused recovery code.

    Returns (factor, accepted). On acceptance the counter advances or the recovery code is consumed.
    """
    factor = await db.scalar(select(MfaFactor).where(MfaFactor.user_id == user_id).with_for_update())
    recovery = await db.scalar(select(MfaRecovery).where(MfaRecovery.user_id == user_id, MfaRecovery.code_hash == digest(code), MfaRecovery.consumed_at.is_(None)).with_for_update())
    counter = int(utcnow().timestamp()) // 30
    matched_counter = next((c for c in (counter-1,counter,counter+1) if factor and pyotp.TOTP(unseal(factor.secret_cipher)).at(c*30) == code and c > factor.last_counter), None)
    if not factor or (matched_counter is None and not recovery):
        return factor, False
    if recovery:
        recovery.consumed_at = utcnow()
    else:
        factor.last_counter = matched_counter
    return factor, True
