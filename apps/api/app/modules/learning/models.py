"""Versioned learning content and owner-scoped educational history.

Published snapshots are append-only. Current release pointers live on tracks;
completion is always tied to the assigned immutable version.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class LearningTrack(Base):
    __tablename__ = "learning_tracks"
    __table_args__ = (UniqueConstraint("foundation_id", "key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(300))
    current_release_id: Mapped[UUID | None] = mapped_column(nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class LearningRelease(Base):
    __tablename__ = "learning_releases"
    __table_args__ = (UniqueConstraint("track_id", "number"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    track_id: Mapped[UUID] = mapped_column(ForeignKey("learning_tracks.id"), index=True)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    intro: Mapped[str] = mapped_column(String(3000), default="")
    lesson_version_ids: Mapped[list] = mapped_column(JSONB)
    assessment_version_id: Mapped[UUID | None] = mapped_column(nullable=True)
    reacknowledgement_required: Mapped[bool] = mapped_column(Boolean, default=False)
    changed_required_items: Mapped[list] = mapped_column(JSONB, default=list)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("track_id", "key"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    track_id: Mapped[UUID] = mapped_column(ForeignKey("learning_tracks.id"), index=True)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    key: Mapped[str] = mapped_column(String(100))
    current_version_id: Mapped[UUID | None] = mapped_column(nullable=True)
    publication_revision: Mapped[int] = mapped_column(BigInteger, default=0)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)


class LessonVersion(Base):
    __tablename__ = "lesson_versions"
    __table_args__ = (UniqueConstraint("lesson_id", "number"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    lesson_id: Mapped[UUID] = mapped_column(ForeignKey("lessons.id"), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(3000), default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LessonBlock(Base):
    __tablename__ = "lesson_blocks"
    __table_args__ = (UniqueConstraint("lesson_version_id", "position"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    lesson_version_id: Mapped[UUID] = mapped_column(ForeignKey("lesson_versions.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    content: Mapped[dict] = mapped_column(JSONB)


class LearningAssignment(Base):
    __tablename__ = "learning_assignments"
    __table_args__ = (
        CheckConstraint("(user_id IS NULL) <> (registration_id IS NULL)", name="learning_owner_xor"),
        UniqueConstraint("release_id", "user_id"), UniqueConstraint("release_id", "registration_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    release_id: Mapped[UUID] = mapped_column(ForeignKey("learning_releases.id"), index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    registration_id: Mapped[UUID | None] = mapped_column(ForeignKey("registration_sessions.id"), nullable=True, index=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class LessonProgress(Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (UniqueConstraint("assignment_id", "lesson_version_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    assignment_id: Mapped[UUID] = mapped_column(ForeignKey("learning_assignments.id"), index=True)
    lesson_version_id: Mapped[UUID] = mapped_column(ForeignKey("lesson_versions.id"), index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssessmentVersion(Base):
    __tablename__ = "assessment_versions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    intro: Mapped[str] = mapped_column(String(3000), default="")
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"
    __table_args__ = (UniqueConstraint("assessment_version_id", "position"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    assessment_version_id: Mapped[UUID] = mapped_column(ForeignKey("assessment_versions.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    prompt: Mapped[str] = mapped_column(String(3000))
    options: Mapped[list] = mapped_column(JSONB)
    correct_option: Mapped[int] = mapped_column(Integer)
    explanation: Mapped[str] = mapped_column(String(6000))


class AssessmentAttempt(Base):
    __tablename__ = "assessment_attempts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    assignment_id: Mapped[UUID] = mapped_column(ForeignKey("learning_assignments.id"), index=True)
    assessment_version_id: Mapped[UUID] = mapped_column(ForeignKey("assessment_versions.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class AssessmentAnswer(Base):
    __tablename__ = "assessment_answers"
    __table_args__ = (UniqueConstraint("attempt_id", "question_id"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    attempt_id: Mapped[UUID] = mapped_column(ForeignKey("assessment_attempts.id"), index=True)
    question_id: Mapped[UUID] = mapped_column(ForeignKey("assessment_questions.id"))
    selected_option: Mapped[int] = mapped_column(Integer)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LessonDraft(Base):
    __tablename__ = "lesson_drafts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    lesson_id: Mapped[UUID] = mapped_column(ForeignKey("lessons.id"), unique=True)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(3000), default="")
    blocks: Mapped[list] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class AssessmentDraft(Base):
    __tablename__ = "assessment_drafts"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    track_id: Mapped[UUID] = mapped_column(ForeignKey("learning_tracks.id"), unique=True)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    intro: Mapped[str] = mapped_column(String(3000), default="")
    questions: Mapped[list] = mapped_column(JSONB, default=list)
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    status: Mapped[str] = mapped_column(String(20), default="draft")
    reviewed_by: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
