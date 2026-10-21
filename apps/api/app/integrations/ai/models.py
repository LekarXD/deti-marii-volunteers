from datetime import date, datetime
from uuid import UUID, uuid4
from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class AISettings(Base):
    __tablename__ = 'ai_settings'
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    daily_tokens: Mapped[int] = mapped_column(BigInteger, default=100000)
    daily_requests: Mapped[int] = mapped_column(Integer, default=100)
    max_concurrent: Mapped[int] = mapped_column(Integer, default=2)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=25)
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    circuit_open_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIDailyUsage(Base):
    __tablename__ = 'ai_daily_usage'
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    charged_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    reserved_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    requests: Mapped[int] = mapped_column(Integer, default=0)


class AIRun(Base):
    __tablename__ = 'ai_runs'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'), index=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    request_session_id: Mapped[UUID] = mapped_column(ForeignKey('sessions.id'))
    task: Mapped[str] = mapped_column(String(60))
    prompt_version: Mapped[str] = mapped_column(String(60))
    model: Mapped[str] = mapped_column(String(200), default='unconfigured')
    state: Mapped[str] = mapped_column(String(40), default='queued', index=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_data: Mapped[dict] = mapped_column(JSONB)
    source_refs: Mapped[list] = mapped_column(JSONB, default=list)
    output: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=1200)
    reserved_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    charged_tokens: Mapped[int] = mapped_column(BigInteger, default=0)
    reservation_day: Mapped[date | None] = mapped_column(Date, nullable=True)
    provider_request_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    calling_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
