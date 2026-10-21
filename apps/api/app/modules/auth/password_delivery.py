"""Freshness checks for transactional registration/reset mail before provider I/O."""
import secrets
from uuid import UUID
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.models import ContactChannel, RegistrationSession, Session, User
from .password_models import PasswordChallenge, PasswordCredential


async def check_password_email(db, outbox, payload):
    from .password import code_digest
    try:
        identity = UUID(payload.get('challenge_id', ''))
    except (ValueError, TypeError):
        return 'suppressed_stale_auth'
    proof = await db.get(PasswordChallenge, identity, populate_existing=True)
    if not proof or proof.foundation_id != outbox.foundation_id or proof.purpose != payload.get('purpose') or proof.normalized_contact != payload.get('to') or proof.consumed_at or proof.expires_at <= utcnow() or proof.attempts >= 5 or not secrets.compare_digest(proof.code_hash, code_digest(identity, payload.get('code', ''))):
        return 'suppressed_stale_auth'
    session = await db.get(Session, proof.bound_session_id, populate_existing=True)
    registration = await db.get(RegistrationSession, session.registration_id, populate_existing=True) if session and session.registration_id else None
    if not session or session.revoked_at or session.expires_at <= utcnow() or not registration or registration.claimed_user_id or registration.expires_at <= utcnow():
        return 'suppressed_stale_auth'
    channel = await db.scalar(select(ContactChannel).where(ContactChannel.normalized_value == proof.normalized_contact))
    if proof.purpose == 'register':
        return 'suppressed_stale_auth' if channel else None
    user = await db.get(User, proof.user_id, populate_existing=True) if proof.user_id else None
    credential = await db.scalar(select(PasswordCredential).where(PasswordCredential.user_id == proof.user_id).execution_options(populate_existing=True)) if user else None
    if not user or user.account_state != 'active' or not channel or channel.user_id != user.id or (credential.version if credential else 0) != proof.credential_version:
        return 'suppressed_stale_auth'
    return None
