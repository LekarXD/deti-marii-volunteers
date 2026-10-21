"""Interview facts. PostgreSQL constraints are the last line of race protection."""
from datetime import date, datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class AvailabilitySeries(Base):
    __tablename__ = "interview_availability_series"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    coordinator_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    local_start_date: Mapped[date] = mapped_column(Date)
    start_minute: Mapped[int] = mapped_column(Integer)
    end_minute: Mapped[int] = mapped_column(Integer)
    timezone: Mapped[str] = mapped_column(String(80), default="Europe/Moscow")
    recurrence: Mapped[str] = mapped_column(String(12), default="once")
    interval_weeks: Mapped[int] = mapped_column(Integer, default=1)
    weekdays: Mapped[list] = mapped_column(JSONB, default=list)
    last_date: Mapped[date | None] = mapped_column(Date)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    buffer_after_minutes: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    venue: Mapped[str] = mapped_column(String(500))
    join_url: Mapped[str | None] = mapped_column(String(1000))
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (CheckConstraint("start_minute >= 0 AND end_minute <= 1440 AND end_minute > start_minute", name="ck_interview_window_time"), CheckConstraint("duration_minutes > 0 AND buffer_after_minutes >= 0 AND interval_weeks BETWEEN 1 AND 52", name="ck_interview_window_duration"),)

class AvailabilityException(Base):
    __tablename__ = "interview_availability_exceptions"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    series_id: Mapped[UUID] = mapped_column(ForeignKey("interview_availability_series.id"))
    origin_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(12))
    start_minute: Mapped[int | None] = mapped_column(Integer)
    end_minute: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("series_id", "origin_date", name="uq_interview_exception_origin"),)

class InterviewSlot(Base):
    __tablename__ = "interview_slots"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    series_id: Mapped[UUID] = mapped_column(ForeignKey("interview_availability_series.id"), index=True)
    coordinator_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    origin_date: Mapped[date] = mapped_column(Date)
    origin_minute: Mapped[int] = mapped_column(Integer)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    busy_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (UniqueConstraint("series_id", "origin_date", "origin_minute", name="uq_interview_slot_origin"), Index("ix_interview_slot_range", "foundation_id", "starts_at"),)

class InterviewBooking(Base):
    __tablename__ = "interview_bookings"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    application_id: Mapped[UUID] = mapped_column(ForeignKey("applications.id"), index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    registration_id: Mapped[UUID | None] = mapped_column(ForeignKey("registration_sessions.id"))
    candidate_key: Mapped[str] = mapped_column(String(80))
    slot_id: Mapped[UUID] = mapped_column(ForeignKey("interview_slots.id"))
    coordinator_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    busy_until: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    venue: Mapped[str] = mapped_column(String(500))
    join_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), default="booked")
    cancel_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    __table_args__ = (
        CheckConstraint("(user_id IS NULL) <> (registration_id IS NULL)", name="ck_interview_booking_owner"),
        CheckConstraint("starts_at < ends_at AND ends_at <= busy_until", name="ck_interview_booking_interval"),
        CheckConstraint("status IN ('booked','cancelled','completed','missed')", name="ck_interview_booking_status"),
        Index("uq_interview_active_slot", "slot_id", unique=True, postgresql_where=text("status = 'booked'")),
        Index("uq_interview_active_candidate", "candidate_key", unique=True, postgresql_where=text("status = 'booked'")),
        ExcludeConstraint(("coordinator_id", "="), (func.tstzrange(starts_at, busy_until, "[)"), "&&"), where=text("status = 'booked'"), name="ex_interview_coordinator_overlap", using="gist"),
        ExcludeConstraint(("candidate_key", "="), (func.tstzrange(starts_at, busy_until, "[)"), "&&"), where=text("status = 'booked'"), name="ex_interview_candidate_overlap", using="gist"),
        Index("ix_interview_bookings_scope_time", "foundation_id", "status", "starts_at"),
    )

class BookingEvent(Base):
    __tablename__ = "interview_booking_events"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("interview_bookings.id"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    actor_id: Mapped[str] = mapped_column(String(100))
    before: Mapped[dict | None] = mapped_column(JSONB)
    after: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class InterviewResult(Base):
    __tablename__ = "interview_results"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("interview_bookings.id"), unique=True)
    outcome: Mapped[str] = mapped_column(String(200))
    public_agreement: Mapped[str] = mapped_column(Text)
    next_contact_date: Mapped[date | None] = mapped_column(Date)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))

class InterviewPrivateNote(Base):
    __tablename__ = "interview_private_notes"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    booking_id: Mapped[UUID] = mapped_column(ForeignKey("interview_bookings.id"), unique=True)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
