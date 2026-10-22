"""CRM facts and historical import provenance, distinct from login identity."""
from datetime import date, datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class CrmVolunteer(Base):
    __tablename__ = "crm_volunteers"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    application_id: Mapped[UUID | None] = mapped_column(ForeignKey("applications.id"))
    display_name: Mapped[str] = mapped_column(String(240))
    contacts: Mapped[dict] = mapped_column(JSONB, default=dict)
    context: Mapped[str] = mapped_column(Text, default="")
    relationship_state: Mapped[str] = mapped_column(String(30), default="unverified")
    no_contact: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    merged_into_id: Mapped[UUID | None] = mapped_column(ForeignKey("crm_volunteers.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (
        Index("uq_crm_volunteer_application", "foundation_id", "application_id", unique=True, postgresql_where=text("application_id IS NOT NULL")),
        Index("uq_crm_volunteer_user", "foundation_id", "user_id", unique=True, postgresql_where=text("user_id IS NOT NULL AND merged_into_id IS NULL")),
        CheckConstraint("relationship_state IN ('unverified','contacted','awaiting_reply','ready','active','paused','unavailable','unreachable','closed')", name="ck_crm_relationship_state"),
        CheckConstraint("merged_into_id IS NULL OR merged_into_id <> id", name="ck_crm_not_own_alias"),
    )


class Agreement(Base):
    __tablename__ = "agreements"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    volunteer_id: Mapped[UUID] = mapped_column(ForeignKey("crm_volunteers.id"), index=True)
    role_context: Mapped[str] = mapped_column(String(400), default="")
    text: Mapped[str] = mapped_column(Text)
    valid_until: Mapped[date | None] = mapped_column(Date)
    supersedes_id: Mapped[UUID | None] = mapped_column(ForeignKey("agreements.id"))
    author_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ContactEvent(Base):
    __tablename__ = "contact_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    volunteer_id: Mapped[UUID] = mapped_column(ForeignKey("crm_volunteers.id"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    direction: Mapped[str] = mapped_column(String(20), default="recorded")
    text: Mapped[str] = mapped_column(Text)
    author_id: Mapped[str] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AvailabilityRule(Base):
    __tablename__ = "availability_rules"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    volunteer_id: Mapped[UUID] = mapped_column(ForeignKey("crm_volunteers.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    summary: Mapped[str] = mapped_column(Text)
    timezone: Mapped[str] = mapped_column(String(80), default="Europe/Moscow")
    preferred_channel: Mapped[str] = mapped_column(String(40))
    author_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("volunteer_id", "number"),)


class AvailabilityWindow(Base):
    __tablename__ = "availability_windows"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    rule_id: Mapped[UUID] = mapped_column(ForeignKey("availability_rules.id"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)
    start_minute: Mapped[int] = mapped_column(Integer)
    end_minute: Mapped[int] = mapped_column(Integer)
    __table_args__ = (CheckConstraint("weekday BETWEEN 0 AND 6 AND start_minute >= 0 AND end_minute <= 1440 AND start_minute < end_minute", name="ck_availability_window"),)


class AvailabilityVerification(Base):
    __tablename__ = "availability_verifications"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    rule_id: Mapped[UUID] = mapped_column(ForeignKey("availability_rules.id"), index=True)
    valid_until: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(80))
    author_id: Mapped[str] = mapped_column(String(100))
    verified_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# Unused since contact review and import were removed (2026-10-22). The tables stay until the fund decides about the personal data in them.
class ReserveReview(Base):
    __tablename__ = "reserve_reviews"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    volunteer_id: Mapped[UUID] = mapped_column(ForeignKey("crm_volunteers.id"), index=True)
    outcome: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text)
    no_contact: Mapped[bool] = mapped_column(Boolean)
    author_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FollowUpTask(Base):
    __tablename__ = "follow_up_tasks"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    volunteer_id: Mapped[UUID] = mapped_column(ForeignKey("crm_volunteers.id"), index=True)
    application_id: Mapped[UUID | None] = mapped_column(ForeignKey("applications.id"))
    assigned_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    due_on: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(400))
    state: Mapped[str] = mapped_column(String(20), default="open")
    source_type: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[UUID] = mapped_column()
    source_revision: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("foundation_id", "source_type", "source_id", "source_revision", name="uq_follow_up_source_revision"),
        CheckConstraint("state IN ('open','done','cancelled') AND source_revision > 0", name="ck_follow_up_state"),
        Index("ix_follow_up_due", "foundation_id", "state", "due_on", "assigned_user_id"),
    )


class FollowUpTaskEvent(Base):
    __tablename__ = "follow_up_task_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    task_id: Mapped[UUID] = mapped_column(ForeignKey("follow_up_tasks.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text, default="")
    before: Mapped[dict] = mapped_column(JSONB, default=dict)
    after: Mapped[dict] = mapped_column(JSONB, default=dict)
    author_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


# Import tables below: unused since 2026-10-22, kept for the same personal-data decision. MergeReview is still written by merges.
class ImportBatch(Base):
    __tablename__ = "import_batches"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    checksum: Mapped[str] = mapped_column(String(64))
    filename: Mapped[str] = mapped_column(String(240))
    columns: Mapped[list] = mapped_column(JSONB)
    mapping: Mapped[dict] = mapped_column(JSONB, default=dict)
    source_system: Mapped[str] = mapped_column(String(80), default="")
    state: Mapped[str] = mapped_column(String(20), default="uploaded")
    version: Mapped[int] = mapped_column(Integer, default=1)
    author_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("foundation_id", "checksum"), CheckConstraint("state IN ('uploaded','mapped','previewed','applied')", name="ck_import_batch_state"))


class ImportRow(Base):
    __tablename__ = "import_rows"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(ForeignKey("import_batches.id"), index=True)
    line_number: Mapped[int] = mapped_column(Integer)
    raw: Mapped[dict] = mapped_column(JSONB)
    normalized: Mapped[dict] = mapped_column(JSONB, default=dict)
    decision: Mapped[str] = mapped_column(String(20), default="unmapped")
    volunteer_id: Mapped[UUID | None] = mapped_column(ForeignKey("crm_volunteers.id"))
    errors: Mapped[list] = mapped_column(JSONB, default=list)
    resolution_reason: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (UniqueConstraint("batch_id", "line_number"), CheckConstraint("decision IN ('unmapped','create','link','review','skip','error')", name="ck_import_row_decision"))


class ImportExternalReference(Base):
    __tablename__ = "import_external_references"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"))
    source_system: Mapped[str] = mapped_column(String(80))
    external_id: Mapped[str] = mapped_column(String(240))
    volunteer_id: Mapped[UUID] = mapped_column(ForeignKey("crm_volunteers.id"), index=True)
    __table_args__ = (UniqueConstraint("foundation_id", "source_system", "external_id", name="uq_import_external_reference"),)


class ImportEffect(Base):
    __tablename__ = "import_effects"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    row_id: Mapped[UUID] = mapped_column(ForeignKey("import_rows.id"), unique=True)
    volunteer_id: Mapped[UUID] = mapped_column(ForeignKey("crm_volunteers.id"), index=True)
    effect: Mapped[str] = mapped_column(String(20))
    snapshot: Mapped[dict] = mapped_column(JSONB)
    author_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MergeReview(Base):
    __tablename__ = "merge_reviews"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    import_row_id: Mapped[UUID | None] = mapped_column(ForeignKey("import_rows.id"))
    source_volunteer_id: Mapped[UUID | None] = mapped_column(ForeignKey("crm_volunteers.id"))
    target_volunteer_id: Mapped[UUID | None] = mapped_column(ForeignKey("crm_volunteers.id"))
    state: Mapped[str] = mapped_column(String(20), default="pending")
    reason: Mapped[str] = mapped_column(Text)
    author_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class FollowUpSource(Base):
    __tablename__ = "follow_up_sources"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"))
    source_type: Mapped[str] = mapped_column(String(50))
    source_id: Mapped[UUID] = mapped_column()
    current_revision: Mapped[int] = mapped_column(Integer)
    payload_hash: Mapped[str] = mapped_column(String(64))
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("follow_up_tasks.id"))
    __table_args__ = (UniqueConstraint("foundation_id", "source_type", "source_id", name="uq_follow_up_source"),)
