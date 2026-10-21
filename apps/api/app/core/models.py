from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base
from app.core.clock import utcnow

class IdentityMixin:
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Foundation(IdentityMixin, Base):
    __tablename__ = "foundations"
    name: Mapped[str] = mapped_column(String(200))

class User(IdentityMixin, Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("id","foundation_id",name="uq_user_foundation_identity"),)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    display_name: Mapped[str] = mapped_column(String(200), default="Волонтёр")
    account_state: Mapped[str] = mapped_column(String(30), default="active")
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    authz_version: Mapped[int] = mapped_column(BigInteger, default=1)

class ContactChannel(IdentityMixin, Base):
    __tablename__ = "contact_channels"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    normalized_value: Mapped[str] = mapped_column(String(320), unique=True)
    type: Mapped[str] = mapped_column(String(20), default="email")
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class RegistrationSession(IdentityMixin, Base):
    __tablename__ = "registration_sessions"
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    verified_email: Mapped[str | None] = mapped_column(String(320))
    claimed_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))

class Session(IdentityMixin, Base):
    __tablename__ = "sessions"
    __table_args__ = (CheckConstraint("(user_id IS NULL) <> (registration_id IS NULL)", name="session_one_owner"),)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    csrf_cipher: Mapped[str] = mapped_column(Text)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    registration_id: Mapped[UUID | None] = mapped_column(ForeignKey("registration_sessions.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class AuthChallenge(IdentityMixin, Base):
    __tablename__ = "auth_challenges"
    bound_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    bound_session_id: Mapped[UUID | None] = mapped_column(ForeignKey("sessions.id"))
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"))
    registration_id: Mapped[UUID | None] = mapped_column(ForeignKey("registration_sessions.id"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    normalized_contact: Mapped[str] = mapped_column(String(320))
    purpose: Mapped[str] = mapped_column(String(30))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)

class StaffMembership(IdentityMixin, Base):
    __tablename__ = "staff_memberships"
    __table_args__ = (UniqueConstraint("foundation_id", "user_id"),)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"))
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class PermissionGrant(IdentityMixin, Base):
    __tablename__ = "permission_grants"
    membership_id: Mapped[UUID] = mapped_column(ForeignKey("staff_memberships.id"), index=True)
    permission: Mapped[str] = mapped_column(String(100))
    scope_type: Mapped[str] = mapped_column(String(20), default="foundation")
    scope_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class MfaFactor(IdentityMixin, Base):
    __tablename__ = "mfa_factors"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), unique=True)
    secret_cipher: Mapped[str] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_counter: Mapped[int] = mapped_column(BigInteger, default=-1)

class MfaRecovery(IdentityMixin, Base):
    __tablename__ = "mfa_recovery_codes"
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class AuditEvent(IdentityMixin, Base):
    __tablename__ = "audit_events"
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    command: Mapped[str] = mapped_column(String(120))
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(100))
    changed_fields: Mapped[list] = mapped_column(JSONB, default=list)
    request_id: Mapped[str | None] = mapped_column(String(100))

class MutationReceipt(IdentityMixin, Base):
    __tablename__ = "mutation_receipts"
    __table_args__ = (UniqueConstraint("actor_id", "operation", "key"),)
    actor_id: Mapped[str] = mapped_column(String(100))
    operation: Mapped[str] = mapped_column(String(120))
    key: Mapped[str] = mapped_column(String(128))
    payload_hash: Mapped[str] = mapped_column(String(64))
    result: Mapped[dict | None] = mapped_column(JSONB)

class Job(IdentityMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (Index("ix_jobs_claim", "state", "available_at"),)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"))
    kind: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    state: Mapped[str] = mapped_column(String(30), default="queued")
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claim_token: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    error_code: Mapped[str | None] = mapped_column(String(100))
    result: Mapped[dict | None] = mapped_column(JSONB)

class OutboxMessage(IdentityMixin, Base):
    __tablename__ = "outbox_messages"
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"))
    channel: Mapped[str] = mapped_column(String(30))
    payload_cipher: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(30), default="queued")
    job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"))
    defer_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class MediaAsset(IdentityMixin, Base):
    __tablename__ = "media_assets"
    __table_args__ = (UniqueConstraint("id","foundation_id",name="uq_asset_foundation_identity"),)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    owner_registration_id: Mapped[UUID | None] = mapped_column(ForeignKey("registration_sessions.id"))
    access_permission: Mapped[str | None] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(String(80), default="generic", server_default="generic")
    resource_type: Mapped[str | None] = mapped_column(String(80))
    resource_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    processing_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"))
    storage_key: Mapped[str] = mapped_column(String(200), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    expected_size: Mapped[int] = mapped_column(BigInteger)
    checksum: Mapped[str] = mapped_column(String(64))
    received_size: Mapped[int] = mapped_column(BigInteger, default=0)
    state: Mapped[str] = mapped_column(String(30), default="uploading")

class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window: Mapped[int] = mapped_column(BigInteger)
    count: Mapped[int] = mapped_column(Integer)

class ResourceReservation(IdentityMixin, Base):
    __tablename__ = "resource_reservations"
    __table_args__ = (
        CheckConstraint("(user_id IS NULL) <> (registration_id IS NULL)", name="reservation_one_owner"),
        CheckConstraint("busy_until > starts_at", name="reservation_positive_range"),
        ExcludeConstraint(("foundation_id", "="), ("owner_key", "="), (text("tstzrange(starts_at,busy_until,'[)')"), "&&"), where=text("active"), using="gist", name="reservation_no_overlap"),
        UniqueConstraint("source_type", "source_id"),
        Index("ix_reservation_owner", "foundation_id", "owner_key", "starts_at"),
    )
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    registration_id: Mapped[UUID | None] = mapped_column(ForeignKey("registration_sessions.id"))
    owner_key: Mapped[str] = mapped_column(String(100))
    source_type: Mapped[str] = mapped_column(String(40))
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    busy_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
