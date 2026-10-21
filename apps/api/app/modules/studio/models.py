from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base

class Webinar(Base):
    __tablename__='studio_webinars'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    host_user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    title:Mapped[str]=mapped_column(String(300))
    description:Mapped[str]=mapped_column(Text,default='')
    starts_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    duration_minutes:Mapped[int]=mapped_column(Integer,default=60)
    state:Mapped[str]=mapped_column(String(20),default='draft')
    require_strict_revocation:Mapped[bool]=mapped_column(Boolean,default=True)
    recording_policy_id:Mapped[UUID]=mapped_column(default=uuid4)
    version:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    __table_args__=(CheckConstraint("state IN ('draft','published','cancelled','ended')",name='ck_webinar_state'),CheckConstraint('duration_minutes BETWEEN 5 AND 480',name='ck_webinar_duration'),Index('ix_webinar_scope_start','foundation_id','state','starts_at'))

class WebinarEnrollment(Base):
    __tablename__='studio_webinar_enrollments'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    webinar_id:Mapped[UUID]=mapped_column(ForeignKey('studio_webinars.id'))
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    state:Mapped[str]=mapped_column(String(20),default='enrolled')
    version:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    __table_args__=(UniqueConstraint('webinar_id','user_id'),CheckConstraint("state IN ('enrolled','withdrawn','revoked')",name='ck_webinar_enrollment_state'))

class StudioSession(Base):
    __tablename__='studio_sessions'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    resource_kind:Mapped[str]=mapped_column(String(40))
    resource_id:Mapped[UUID]=mapped_column(index=True)
    host_user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    room_name:Mapped[str]=mapped_column(String(128),unique=True)
    generation:Mapped[int]=mapped_column(Integer)
    state:Mapped[str]=mapped_column(String(20),default='prepared')
    provider_sid:Mapped[str|None]=mapped_column(String(100))
    scene:Mapped[dict]=mapped_column(JSONB)
    scene_revision:Mapped[int]=mapped_column(Integer,default=0)
    require_strict_revocation:Mapped[bool]=mapped_column(Boolean,default=True)
    recording_policy_id:Mapped[UUID]=mapped_column(default=uuid4)
    version:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    opened_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    closed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    __table_args__=(UniqueConstraint('resource_kind','resource_id','generation'),Index('uq_studio_active_resource','resource_kind','resource_id',unique=True,postgresql_where=text("state IN ('prepared','opening','live','closing')")),CheckConstraint("state IN ('prepared','opening','live','closing','closed','failed')",name='ck_studio_session_state'),CheckConstraint('generation>0 AND scene_revision>=0',name='ck_studio_session_revision'))

class StudioSceneEvent(Base):
    __tablename__='studio_scene_events'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    session_id:Mapped[UUID]=mapped_column(ForeignKey('studio_sessions.id'))
    revision:Mapped[int]=mapped_column(Integer)
    scene:Mapped[dict]=mapped_column(JSONB)
    actor_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    __table_args__=(UniqueConstraint('session_id','revision'),)

class StudioBoardGrant(Base):
    __tablename__='studio_board_grants'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    session_id:Mapped[UUID]=mapped_column(ForeignKey('studio_sessions.id'))
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    can_draw:Mapped[bool]=mapped_column(Boolean,default=False)
    version:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(UniqueConstraint('session_id','user_id'),)

class SlideDeck(Base):
    __tablename__='slide_decks'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    owner_user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    resource_kind:Mapped[str]=mapped_column(String(40))
    resource_id:Mapped[UUID]=mapped_column(index=True)
    title:Mapped[str]=mapped_column(String(300))
    source_asset_id:Mapped[UUID|None]=mapped_column(ForeignKey('media_assets.id'))
    state:Mapped[str]=mapped_column(String(20),default='uploading')
    error_code:Mapped[str|None]=mapped_column(String(100))
    version:Mapped[int]=mapped_column(Integer,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class SlideDeckVersion(Base):
    __tablename__='slide_deck_versions'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    deck_id:Mapped[UUID]=mapped_column(ForeignKey('slide_decks.id'),index=True)
    number:Mapped[int]=mapped_column(Integer,default=1)
    source_sha256:Mapped[str]=mapped_column(String(64))
    conversion_profile:Mapped[str]=mapped_column(String(50),default='opora-slides/1')
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    __table_args__=(UniqueConstraint('deck_id','number'),)

class SlidePage(Base):
    __tablename__='slide_assets'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    deck_version_id:Mapped[UUID]=mapped_column(ForeignKey('slide_deck_versions.id'),index=True)
    ordinal:Mapped[int]=mapped_column(Integer)
    asset_id:Mapped[UUID]=mapped_column(ForeignKey('media_assets.id'))
    width:Mapped[int]=mapped_column(Integer)
    height:Mapped[int]=mapped_column(Integer)
    sha256:Mapped[str]=mapped_column(String(64))
    __table_args__=(UniqueConstraint('deck_version_id','ordinal'),CheckConstraint('ordinal>=0 AND width>0 AND height>0',name='ck_slide_dimensions'))

class StudioBoardSnapshot(Base):
    __tablename__='studio_board_snapshots'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    session_id:Mapped[UUID]=mapped_column(ForeignKey('studio_sessions.id'),index=True)
    asset_id:Mapped[UUID]=mapped_column(ForeignKey('media_assets.id'))
    width:Mapped[int]=mapped_column(Integer)
    height:Mapped[int]=mapped_column(Integer)
    sha256:Mapped[str]=mapped_column(String(64))
    taken_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())

class StudioWebhookEvent(Base):
    __tablename__='studio_webhook_events'
    id:Mapped[str]=mapped_column(String(100),primary_key=True)
    event_type:Mapped[str]=mapped_column(String(60))
    room_name:Mapped[str]=mapped_column(String(128),index=True)
    received_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
