"""Candidate identity is the application UUID, never a contact string."""
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


def now():
    return datetime.now(timezone.utc)


class FormVersion(Base):
    __tablename__ = "form_versions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    version: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSONB)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("foundation_id", "version"),)


class ApplicationDraft(Base):
    __tablename__ = "application_drafts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    registration_id: Mapped[UUID | None] = mapped_column(ForeignKey("registration_sessions.id"))
    form_version_id: Mapped[UUID] = mapped_column(ForeignKey("form_versions.id"))
    answers: Mapped[dict] = mapped_column(JSONB, default=dict)
    step: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        CheckConstraint("(user_id IS NULL) <> (registration_id IS NULL)", name="draft_owner_xor"),
        CheckConstraint("step >= 0 AND step <= 2", name="draft_step_range"),
        Index("draft_one_user", "foundation_id", "user_id", unique=True, postgresql_where=text("user_id IS NOT NULL")),
        Index("draft_one_registration", "foundation_id", "registration_id", unique=True, postgresql_where=text("registration_id IS NOT NULL")),
    )


class Application(Base):
    __tablename__ = "applications"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    registration_id: Mapped[UUID | None] = mapped_column(ForeignKey("registration_sessions.id"))
    submitted_revision_id: Mapped[UUID | None] = mapped_column(ForeignKey("application_revisions.id", use_alter=True, name="application_current_revision_fk"))
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    submission_state: Mapped[str] = mapped_column(String(20), default="submitted")
    review_state: Mapped[str] = mapped_column(String(20), default="new")
    assigned_coordinator_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        CheckConstraint("(user_id IS NULL) <> (registration_id IS NULL)", name="application_owner_xor"),
        CheckConstraint("submission_state IN ('submitted','withdrawn')", name="application_submission_state"),
        CheckConstraint("review_state IN ('new','reviewing','discussed','paused','closed')", name="application_review_state"),
        Index("application_one_user", "foundation_id", "user_id", unique=True, postgresql_where=text("user_id IS NOT NULL")),
        Index("application_one_registration", "foundation_id", "registration_id", unique=True, postgresql_where=text("registration_id IS NOT NULL")),
    )


class ApplicationRevision(Base):
    __tablename__ = "application_revisions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    form_version_id: Mapped[UUID] = mapped_column(ForeignKey("form_versions.id"))
    number: Mapped[int] = mapped_column(Integer)
    answers: Mapped[dict] = mapped_column(JSONB)
    author_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("application_id", "number"),)


class ConsentEvent(Base):
    __tablename__ = "consent_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    application_id: Mapped[UUID | None] = mapped_column(ForeignKey("applications.id"), index=True)
    subject_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    __table_args__ = (CheckConstraint("(application_id IS NULL) <> (subject_user_id IS NULL)", name="consent_one_subject"),)
    document: Mapped[str] = mapped_column(String(80))
    document_version: Mapped[str] = mapped_column(String(32))
    purpose: Mapped[str] = mapped_column(String(60))
    granted: Mapped[bool]
    author_id: Mapped[str] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(40), default="application_form")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ApplicationReviewEvent(Base):
    __tablename__ = "application_review_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    state: Mapped[str] = mapped_column(String(20))
    public_message: Mapped[str] = mapped_column(Text, default="")
    author_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ApplicationPrivateNote(Base):
    __tablename__ = "application_private_notes"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    author_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class CandidateRequest(Base):
    __tablename__ = "candidate_requests"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    text: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(20), default="open")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (
        CheckConstraint("kind IN ('alternate_time','question','road_help')", name="candidate_request_kind"),
        CheckConstraint("state IN ('open','answered','resolved')", name="candidate_request_state"),
    )


class CandidateRequestResponse(Base):
    __tablename__ = "candidate_request_responses"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    request_id: Mapped[UUID] = mapped_column(ForeignKey("candidate_requests.id"), index=True)
    text: Mapped[str] = mapped_column(Text)
    author_id: Mapped[str] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
