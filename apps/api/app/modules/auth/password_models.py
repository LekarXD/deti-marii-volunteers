"""Password credentials and session-bound email proofs; separate from legacy links."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base
from app.core.models import IdentityMixin


class PasswordCredential(IdentityMixin, Base):
    __tablename__ = 'password_credentials'
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1)
    demo_created: Mapped[bool] = mapped_column(Boolean, default=False)


class PasswordChallenge(IdentityMixin, Base):
    __tablename__ = 'password_challenges'
    __table_args__ = (
        CheckConstraint("purpose IN ('register','password_reset')", name='password_challenge_purpose'),
        CheckConstraint('attempts BETWEEN 0 AND 5', name='password_challenge_attempts'),
        CheckConstraint("purpose <> 'register' OR pending_password_hash IS NOT NULL", name='password_registration_hash'),
    )
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'))
    bound_session_id: Mapped[UUID] = mapped_column(ForeignKey('sessions.id'), index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey('users.id'))
    credential_version: Mapped[int | None] = mapped_column(Integer)
    normalized_contact: Mapped[str] = mapped_column(String(320))
    purpose: Mapped[str] = mapped_column(String(30))
    demo_code_allowed: Mapped[bool] = mapped_column(Boolean, default=False)
    code_hash: Mapped[str] = mapped_column(String(64))
    pending_password_hash: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
