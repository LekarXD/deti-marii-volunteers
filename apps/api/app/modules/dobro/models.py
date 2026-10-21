"""Manual external copies. These tables never grant participation or mutate minutes."""
from datetime import date, datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.clock import utcnow
from app.core.db import Base


class DobroActivityLink(Base):
    __tablename__ = 'dobro_activity_links'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'), index=True)
    opportunity_id: Mapped[UUID] = mapped_column()
    url: Mapped[str] = mapped_column(String(1500))
    kind: Mapped[str] = mapped_column(String(20))
    title: Mapped[str] = mapped_column(String(300))
    valid_from: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)
    actor_id: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('id', 'foundation_id'),
        ForeignKeyConstraint(['opportunity_id', 'foundation_id'], ['opportunities.id', 'opportunities.foundation_id']),
        CheckConstraint("kind IN ('long_term','one_off') AND valid_until >= valid_from AND version > 0", name='ck_dobro_activity'))


class DobroSeriesOpportunity(Base):
    """Explicit event attribution; replacing after any ledger fact is forbidden."""
    __tablename__ = 'dobro_series_opportunities'
    series_id: Mapped[UUID] = mapped_column(primary_key=True)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'))
    opportunity_id: Mapped[UUID] = mapped_column()
    version: Mapped[int] = mapped_column(Integer, default=1)
    actor_id: Mapped[str] = mapped_column(String(200))
    __table_args__ = (ForeignKeyConstraint(['series_id', 'foundation_id'], ['event_series.id', 'event_series.foundation_id']),
        ForeignKeyConstraint(['opportunity_id', 'foundation_id'], ['opportunities.id', 'opportunities.foundation_id']),
        CheckConstraint('version > 0', name='ck_dobro_series_version'))


class DobroProfile(Base):
    __tablename__ = 'dobro_profiles'
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), primary_key=True)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'))
    profile_url: Mapped[str] = mapped_column(String(1500))
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DobroEnrollment(Base):
    __tablename__ = 'dobro_enrollments'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'))
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    activity_id: Mapped[UUID] = mapped_column()
    state: Mapped[str] = mapped_column(String(20), default='none')
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('activity_id', 'user_id'),
        ForeignKeyConstraint(['activity_id', 'foundation_id'], ['dobro_activity_links.id', 'dobro_activity_links.foundation_id']),
        CheckConstraint("state IN ('none','applied','approved','not_needed') AND version > 0", name='ck_dobro_enrollment'))


class DobroEnrollmentEvent(Base):
    __tablename__ = 'dobro_enrollment_events'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    enrollment_id: Mapped[UUID] = mapped_column(ForeignKey('dobro_enrollments.id'))
    version: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[str] = mapped_column(String(200))
    reason: Mapped[str] = mapped_column(Text, default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('enrollment_id', 'version'),)


class DobroTransfer(Base):
    __tablename__ = 'dobro_transfers'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'), index=True)
    activity_id: Mapped[UUID] = mapped_column()
    period: Mapped[date] = mapped_column(Date)
    minutes_due_snapshot: Mapped[int] = mapped_column(Integer)
    hours_delta: Mapped[int] = mapped_column(Integer)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    snapshot: Mapped[dict] = mapped_column(JSONB)
    actor_id: Mapped[str] = mapped_column(String(200))
    note: Mapped[str] = mapped_column(Text, default='')
    entered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (ForeignKeyConstraint(['activity_id', 'foundation_id'], ['dobro_activity_links.id', 'dobro_activity_links.foundation_id']),
        CheckConstraint('hours_delta <> 0 AND EXTRACT(DAY FROM period) = 1', name='ck_dobro_transfer_delta'))


class DobroSettings(Base):
    __tablename__ = 'dobro_settings'
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'), primary_key=True)
    organization_url: Mapped[str] = mapped_column(String(1500), default='')
    registration_url: Mapped[str] = mapped_column(String(1500), default='')
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    monthly_day: Mapped[int] = mapped_column(Integer, default=5)
    hard_deadline_days: Mapped[int] = mapped_column(Integer, default=60)
    risk_days: Mapped[int] = mapped_column(Integer, default=7)
    whole_hours: Mapped[bool] = mapped_column(Boolean, default=True)
    rules_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_template: Mapped[str] = mapped_column(Text, default='{имя}, чтобы мы внесли твои часы в электронную книжку Добро.рф, откликнись один раз на доброе дело: {ссылка}. Потом нажми «Я откликнулся» в Опоре.')
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated_by: Mapped[str] = mapped_column(String(200))
    __table_args__ = (CheckConstraint('monthly_day BETWEEN 1 AND 28 AND hard_deadline_days BETWEEN 1 AND 365 AND risk_days BETWEEN 1 AND 60 AND version > 0', name='ck_dobro_settings'),)
