"""P08 calendar schema. Origins stay stable even when the effective date moves."""
from datetime import date, datetime, time
from uuid import UUID, uuid4
from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base
from app.core.clock import utcnow as now


class EventSeries(Base):
    __tablename__='event_series'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    group_id:Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True))
    anchor_date:Mapped[date]=mapped_column(Date)
    origin_time:Mapped[time]=mapped_column(Time)
    start_date:Mapped[date]=mapped_column(Date)
    start_time:Mapped[time]=mapped_column(Time)
    timezone:Mapped[str]=mapped_column(String(100),default='Europe/Moscow')
    duration_minutes:Mapped[int]=mapped_column(Integer)
    recurrence:Mapped[dict]=mapped_column(JSONB)
    title:Mapped[str]=mapped_column(String(200))
    program:Mapped[str]=mapped_column(String(200),default='')
    kind:Mapped[str]=mapped_column(String(30),default='activity')
    format:Mapped[str]=mapped_column(String(20),default='onsite')
    location:Mapped[str]=mapped_column(String(500),default='')
    audience:Mapped[str]=mapped_column(Text,default='')
    state:Mapped[str]=mapped_column(String(20),default='active')
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_by:Mapped[str]=mapped_column(String(200))
    __table_args__=(UniqueConstraint('id','foundation_id'),
        ForeignKeyConstraint(['group_id','foundation_id'],['participant_groups.id','participant_groups.foundation_id']),
        CheckConstraint('duration_minutes > 0 AND duration_minutes <= 10080'),
        CheckConstraint("state IN ('active','cancelled')"),
        Index('ix_event_series_scope','foundation_id','state','id'))


class EventSeriesNeedTemplate(Base):
    __tablename__='event_series_need_templates'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    series_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    foundation_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    role_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    role_version_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    capacity_required:Mapped[int]=mapped_column(Integer)
    preparation_requirements:Mapped[list]=mapped_column(JSONB,default=list)
    approval_policy:Mapped[str]=mapped_column(String(30),default='coordinator')
    # Points only; never part of the invitation conditions or their version.
    points_multiplier:Mapped[float]=mapped_column(Numeric(3,2,asdecimal=False),default=1,server_default='1')
    active:Mapped[bool]=mapped_column(default=True)
    __table_args__=(CheckConstraint('capacity_required >= 0 AND capacity_required <= 1000'),CheckConstraint('points_multiplier IN (1, 1.5)',name='ck_need_template_points_multiplier'),UniqueConstraint('series_id','role_id'),
        ForeignKeyConstraint(['series_id','foundation_id'],['event_series.id','event_series.foundation_id']),
        ForeignKeyConstraint(['role_id','foundation_id'],['volunteer_roles.id','volunteer_roles.foundation_id']),
        ForeignKeyConstraint(['role_version_id','role_id'],['volunteer_role_versions.id','volunteer_role_versions.role_id']))


class EventOccurrence(Base):
    __tablename__='event_occurrences'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    series_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    origin_local_date:Mapped[date]=mapped_column(Date)
    origin_local_time:Mapped[time]=mapped_column(Time)
    starts_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    ends_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    timezone:Mapped[str]=mapped_column(String(100))
    group_id:Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True))
    title:Mapped[str]=mapped_column(String(200))
    program:Mapped[str]=mapped_column(String(200),default='')
    kind:Mapped[str]=mapped_column(String(30),default='activity')
    format:Mapped[str]=mapped_column(String(20),default='onsite')
    location:Mapped[str]=mapped_column(String(500),default='')
    audience:Mapped[str]=mapped_column(Text,default='')
    status:Mapped[str]=mapped_column(String(20),default='scheduled')
    cancellation_source:Mapped[str|None]=mapped_column(String(30))
    series_version:Mapped[int]=mapped_column(BigInteger)
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_by:Mapped[str]=mapped_column(String(200))
    __table_args__=(UniqueConstraint('id','foundation_id'),UniqueConstraint('series_id','origin_local_date','origin_local_time'),
        ForeignKeyConstraint(['series_id','foundation_id'],['event_series.id','event_series.foundation_id']),
        ForeignKeyConstraint(['group_id','foundation_id'],['participant_groups.id','participant_groups.foundation_id']),
        CheckConstraint('ends_at > starts_at'),CheckConstraint("status IN ('scheduled','cancelled','completed')"),
        Index('ix_event_occurrence_range','foundation_id','starts_at','id'),Index('ix_event_occurrence_group','group_id','starts_at'))


class OccurrenceOverride(Base):
    __tablename__='occurrence_overrides'
    occurrence_id:Mapped[UUID]=mapped_column(ForeignKey('event_occurrences.id'),primary_key=True)
    fields:Mapped[dict]=mapped_column(JSONB)
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    updated_by:Mapped[str]=mapped_column(String(200))


class StaffingNeed(Base):
    __tablename__='staffing_needs'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    occurrence_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    foundation_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    template_id:Mapped[UUID|None]=mapped_column(ForeignKey('event_series_need_templates.id'))
    role_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    role_version_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    capacity_required:Mapped[int]=mapped_column(Integer)
    preparation_requirements:Mapped[list]=mapped_column(JSONB,default=list)
    approval_policy:Mapped[str]=mapped_column(String(30),default='coordinator')
    # Points only; changing it keeps version so pending invitations stay valid.
    points_multiplier:Mapped[float]=mapped_column(Numeric(3,2,asdecimal=False),default=1,server_default='1')
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    __table_args__=(UniqueConstraint('id','occurrence_id','foundation_id'),CheckConstraint('points_multiplier IN (1, 1.5)',name='ck_staffing_need_points_multiplier'),ForeignKeyConstraint(['occurrence_id','foundation_id'],['event_occurrences.id','event_occurrences.foundation_id']),
        ForeignKeyConstraint(['role_id','foundation_id'],['volunteer_roles.id','volunteer_roles.foundation_id']),
        ForeignKeyConstraint(['role_version_id','role_id'],['volunteer_role_versions.id','volunteer_role_versions.role_id']),
        CheckConstraint('capacity_required >= 0 AND capacity_required <= 1000'),
        UniqueConstraint('occurrence_id','role_id'),Index('ix_staffing_scope','foundation_id','occurrence_id'))


class EventRevision(Base):
    __tablename__='event_revisions'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    entity_type:Mapped[str]=mapped_column(String(30))
    entity_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    version:Mapped[int]=mapped_column(BigInteger)
    snapshot:Mapped[dict]=mapped_column(JSONB)
    actor_id:Mapped[str]=mapped_column(String(200))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=now)
    __table_args__=(UniqueConstraint('entity_type','entity_id','version'),Index('ix_event_history_scope','foundation_id','entity_id'))
