"""Versioned own profile, immutable service-time ledger and review workflows."""
from datetime import date,datetime
from uuid import UUID,uuid4
from sqlalchemy import Boolean,CheckConstraint,Date,DateTime,ForeignKey,Integer,String,Text,UniqueConstraint,Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.core.db import Base
from app.core.clock import utcnow

class VolunteerProfile(Base):
    __tablename__='volunteer_profiles'
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),primary_key=True)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    about:Mapped[str]=mapped_column(Text,default='')
    lifecycle:Mapped[str]=mapped_column(String(20),default='active')
    paused_until:Mapped[date|None]=mapped_column(Date)
    photo_asset_id:Mapped[UUID|None]=mapped_column(ForeignKey('media_assets.id'))
    ai_about:Mapped[bool]=mapped_column(Boolean,default=False)
    ai_skills:Mapped[bool]=mapped_column(Boolean,default=False)
    ai_interests:Mapped[bool]=mapped_column(Boolean,default=False)
    version:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(CheckConstraint("lifecycle IN ('active','paused') AND version > 0",name='ck_profile_lifecycle'),)

class ProfileTag(Base):
    __tablename__='profile_tags'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    kind:Mapped[str]=mapped_column(String(20))
    label:Mapped[str]=mapped_column(String(120))
    normalized:Mapped[str]=mapped_column(String(120))
    __table_args__=(UniqueConstraint('foundation_id','kind','normalized'),CheckConstraint("kind IN ('skill','interest','age_interest','place_interest')",name='ck_profile_tag_kind'))

class ProfileTagLink(Base):
    __tablename__='profile_tag_links'
    user_id:Mapped[UUID]=mapped_column(ForeignKey('volunteer_profiles.user_id'),primary_key=True)
    tag_id:Mapped[UUID]=mapped_column(ForeignKey('profile_tags.id'),primary_key=True)
    level:Mapped[str]=mapped_column(String(20),default='learn')
    __table_args__=(CheckConstraint("level IN ('learn','sure')",name='ck_profile_skill_level'),)

class ProfileRevision(Base):
    __tablename__='profile_revisions'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    number:Mapped[int]=mapped_column(Integer)
    snapshot:Mapped[dict]=mapped_column(JSONB)
    source:Mapped[str]=mapped_column(String(40))
    actor_id:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('user_id','number'),)

class ProfileChangeSuggestion(Base):
    __tablename__='profile_change_suggestions'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    base_version:Mapped[int]=mapped_column(Integer)
    before:Mapped[dict]=mapped_column(JSONB)
    patch:Mapped[dict]=mapped_column(JSONB)
    source_refs:Mapped[list]=mapped_column(JSONB)
    producer:Mapped[dict]=mapped_column(JSONB)
    state:Mapped[str]=mapped_column(String(20),default='proposed')
    applied_revision_id:Mapped[UUID|None]=mapped_column(ForeignKey('profile_revisions.id'))
    reverted_revision_id:Mapped[UUID|None]=mapped_column(ForeignKey('profile_revisions.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(CheckConstraint("state IN ('proposed','accepted','rejected','reverted')",name='ck_profile_suggestion_state'),)

class ManualTimeRequest(Base):
    __tablename__='manual_time_requests'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    title:Mapped[str]=mapped_column(String(400))
    service_date:Mapped[date]=mapped_column(Date)
    requested_minutes:Mapped[int]=mapped_column(Integer)
    approved_minutes:Mapped[int]=mapped_column(Integer,default=0)
    state:Mapped[str]=mapped_column(String(20),default='pending')
    version:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(CheckConstraint("requested_minutes BETWEEN 1 AND 1440 AND approved_minutes BETWEEN 0 AND 1440 AND state IN ('pending','approved','rejected','cancelled')",name='ck_manual_time_request'),)

class ManualTimeReview(Base):
    __tablename__='manual_time_reviews'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    request_id:Mapped[UUID]=mapped_column(ForeignKey('manual_time_requests.id'),index=True)
    version:Mapped[int]=mapped_column(Integer)
    decision:Mapped[str]=mapped_column(String(20))
    approved_minutes:Mapped[int]=mapped_column(Integer)
    reason:Mapped[str]=mapped_column(Text)
    actor_id:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('request_id','version'),)

class ServiceTimeEntry(Base):
    __tablename__='service_time_entries'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    service_date:Mapped[date]=mapped_column(Date)
    title:Mapped[str]=mapped_column(String(400))
    delta_minutes:Mapped[int]=mapped_column(Integer)
    source_kind:Mapped[str]=mapped_column(String(30))
    source_id:Mapped[UUID]=mapped_column()
    source_revision:Mapped[int]=mapped_column(Integer)
    attendance_event_id:Mapped[UUID|None]=mapped_column(ForeignKey('attendance_events.id'),unique=True)
    assignment_id:Mapped[UUID|None]=mapped_column(ForeignKey('assignments.id'))
    manual_request_id:Mapped[UUID|None]=mapped_column(ForeignKey('manual_time_requests.id'))
    reason:Mapped[str]=mapped_column(Text)
    actor_id:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('foundation_id','source_kind','source_id','source_revision',name='uq_service_time_source'),CheckConstraint("source_kind IN ('attendance','manual_review') AND source_revision > 0",name='ck_service_time_source'),Index('ix_service_time_period','foundation_id','user_id','service_date'))

class ProfileDocument(Base):
    __tablename__='profile_documents'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    kind:Mapped[str]=mapped_column(String(20))
    period_from:Mapped[date]=mapped_column(Date)
    period_to:Mapped[date]=mapped_column(Date)
    recipient:Mapped[str]=mapped_column(String(240))
    body:Mapped[str]=mapped_column(Text,default='')
    total_minutes:Mapped[int]=mapped_column(Integer,default=0)
    snapshot:Mapped[dict]=mapped_column(JSONB,default=dict)
    state:Mapped[str]=mapped_column(String(20),default='requested')
    version:Mapped[int]=mapped_column(Integer,default=1)
    asset_id:Mapped[UUID|None]=mapped_column(ForeignKey('media_assets.id'))
    reviewed_by:Mapped[UUID|None]=mapped_column(ForeignKey('users.id'))
    public_response:Mapped[str]=mapped_column(Text,default='')
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(CheckConstraint("kind IN ('certificate','letter') AND state IN ('requested','approved','ready','rejected','withdrawn') AND period_to >= period_from AND total_minutes >= 0",name='ck_profile_document'),)

class Gratitude(Base):
    __tablename__='gratitudes'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    basis_entry_id:Mapped[UUID]=mapped_column(ForeignKey('service_time_entries.id'))
    text:Mapped[str]=mapped_column(Text)
    author_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class ProfileDataRequest(Base):
    __tablename__='profile_data_requests'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    kind:Mapped[str]=mapped_column(String(20))
    state:Mapped[str]=mapped_column(String(20),default='requested')
    version:Mapped[int]=mapped_column(Integer,default=1)
    reason:Mapped[str]=mapped_column(Text,default='')
    public_response:Mapped[str]=mapped_column(Text,default='')
    retention_note:Mapped[str]=mapped_column(Text,default='')
    scheduled_for:Mapped[date|None]=mapped_column(Date)
    asset_id:Mapped[UUID|None]=mapped_column(ForeignKey('media_assets.id'))
    reviewed_by:Mapped[UUID|None]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(CheckConstraint("kind IN ('export','deletion') AND state IN ('requested','in_review','approved','ready','rejected','cancelled','completed')",name='ck_profile_data_request'),)

class PointsEntry(Base):
    """Bonuses and manual adjustments. Hours-based points are derived from the ledger, never stored."""
    __tablename__='points_entries'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    kind:Mapped[str]=mapped_column(String(20))
    bonus_key:Mapped[str|None]=mapped_column(String(40))
    points:Mapped[int]=mapped_column(Integer)
    reason:Mapped[str]=mapped_column(Text)
    actor_id:Mapped[str]=mapped_column(String(100))
    occurred_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('foundation_id','user_id','bonus_key',name='uq_points_bonus_once'),CheckConstraint("kind IN ('bonus','adjustment') AND (kind = 'bonus') = (bonus_key IS NOT NULL) AND points <> 0",name='ck_points_entry'))

class Prize(Base):
    __tablename__='prizes'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    title:Mapped[str]=mapped_column(String(200))
    description:Mapped[str]=mapped_column(Text,default='')
    photo_asset_id:Mapped[UUID|None]=mapped_column(ForeignKey('media_assets.id'))
    price_points:Mapped[int]=mapped_column(Integer)
    stock:Mapped[int]=mapped_column(Integer)
    visible:Mapped[bool]=mapped_column(Boolean,default=True)
    version:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(CheckConstraint('price_points > 0 AND stock >= 0 AND version > 0',name='ck_prize'),)

class PrizeRequest(Base):
    __tablename__='prize_requests'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),index=True)
    prize_id:Mapped[UUID]=mapped_column(ForeignKey('prizes.id'),index=True)
    points:Mapped[int]=mapped_column(Integer)
    state:Mapped[str]=mapped_column(String(20),default='requested')
    version:Mapped[int]=mapped_column(Integer,default=1)
    reason:Mapped[str]=mapped_column(Text,default='')
    decided_by:Mapped[UUID|None]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(CheckConstraint("points > 0 AND state IN ('requested','issued','rejected','cancelled')",name='ck_prize_request'),)
