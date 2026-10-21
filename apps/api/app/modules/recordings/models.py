"""Recording ownership is independent from operational Studio rooms and learning publication."""
from datetime import datetime
from uuid import UUID,uuid4
from sqlalchemy import BigInteger,Boolean,CheckConstraint,DateTime,ForeignKey,Integer,String,Text,UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.core.clock import utcnow
from app.core.db import Base

class RecordingProject(Base):
    __tablename__='recording_projects'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    owner_user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    target_lesson_id:Mapped[UUID|None]=mapped_column(ForeignKey('lessons.id'))
    live_event_id:Mapped[UUID|None]=mapped_column(ForeignKey('studio_webinars.id'))
    title:Mapped[str]=mapped_column(String(300))
    mode:Mapped[str]=mapped_column(String(20),default='solo')
    recording_policy_id:Mapped[UUID]=mapped_column(default=uuid4)
    state:Mapped[str]=mapped_column(String(30),default='draft')
    privacy_state:Mapped[str]=mapped_column(String(20),default='unknown')
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('id','foundation_id'),CheckConstraint("mode IN ('solo','live') AND state IN ('draft','prepared','has_takes','archived') AND privacy_state IN ('unknown','approved','blocked')",name='ck_recording_project_state'),)

class StudioCaptureSession(Base):
    __tablename__='studio_capture_sessions'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    project_id:Mapped[UUID]=mapped_column(ForeignKey('recording_projects.id'),index=True)
    studio_session_id:Mapped[UUID]=mapped_column(ForeignKey('studio_sessions.id'),unique=True)
    host_auth_session_id:Mapped[UUID]=mapped_column(ForeignKey('sessions.id'))
    generation:Mapped[int]=mapped_column(BigInteger)
    state:Mapped[str]=mapped_column(String(30),default='prepared')
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class RecordingTake(Base):
    __tablename__='recording_takes'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    project_id:Mapped[UUID]=mapped_column(ForeignKey('recording_projects.id'),index=True)
    capture_session_id:Mapped[UUID]=mapped_column(ForeignKey('studio_capture_sessions.id'))
    number:Mapped[int]=mapped_column(Integer)
    generation:Mapped[int]=mapped_column(BigInteger)
    state:Mapped[str]=mapped_column(String(30),default='created')
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    renderer_state_version:Mapped[int]=mapped_column(BigInteger,default=1)
    projection:Mapped[dict]=mapped_column(JSONB)
    projection_hash:Mapped[str]=mapped_column(String(64))
    readiness_state:Mapped[str]=mapped_column(String(20),default='waiting')
    readiness:Mapped[dict|None]=mapped_column(JSONB)
    provider_capture_id:Mapped[str|None]=mapped_column(String(200),unique=True)
    capture_job_id:Mapped[UUID|None]=mapped_column(ForeignKey('jobs.id',name='fk_recording_capture_job'))
    capture_phase:Mapped[str|None]=mapped_column(String(30))
    capture_checkpoint:Mapped[dict|None]=mapped_column(JSONB)
    started_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    stopped_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    error_code:Mapped[str|None]=mapped_column(String(100))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('project_id','number'),UniqueConstraint('capture_job_id',name='uq_recording_capture_job'),CheckConstraint("state IN ('created','starting','capturing','stopping','captured','failed','discarded')",name='ck_recording_take_state'),)

class RecordingRendererGrant(Base):
    __tablename__='recording_renderer_grants'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    take_id:Mapped[UUID]=mapped_column(ForeignKey('recording_takes.id'),index=True)
    generation:Mapped[int]=mapped_column(BigInteger)
    token_hash:Mapped[str]=mapped_column(String(64),unique=True)
    purpose:Mapped[str]=mapped_column(String(20))
    readiness_sequence:Mapped[int]=mapped_column(BigInteger,default=0,server_default='0')
    readiness_hash:Mapped[str|None]=mapped_column(String(64))
    readiness_response:Mapped[dict|None]=mapped_column(JSONB)
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    consumed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))

class RecordingStageEvent(Base):
    __tablename__='recording_stage_events'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    take_id:Mapped[UUID]=mapped_column(ForeignKey('recording_takes.id'),index=True)
    sequence:Mapped[int]=mapped_column(BigInteger)
    renderer_state_version:Mapped[int]=mapped_column(BigInteger)
    projection_hash:Mapped[str]=mapped_column(String(64))
    projection:Mapped[dict]=mapped_column(JSONB)
    media_time_ms:Mapped[int|None]=mapped_column(BigInteger)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('take_id','sequence'),)

class RecordingSourceFile(Base):
    __tablename__='recording_source_files'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    take_id:Mapped[UUID]=mapped_column(ForeignKey('recording_takes.id'),index=True)
    asset_id:Mapped[UUID]=mapped_column(ForeignKey('media_assets.id'),unique=True)
    kind:Mapped[str]=mapped_column(String(30))
    content_hash:Mapped[str]=mapped_column(String(64))
    manifest:Mapped[dict]=mapped_column(JSONB)
    duration_ms:Mapped[int]=mapped_column(BigInteger)
    retained_until:Mapped[datetime]=mapped_column(DateTime(timezone=True))

class RecordingRenderVersion(Base):
    __tablename__='recording_render_versions'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    project_id:Mapped[UUID]=mapped_column(ForeignKey('recording_projects.id'),index=True)
    take_id:Mapped[UUID]=mapped_column(ForeignKey('recording_takes.id'),index=True)
    generation:Mapped[int]=mapped_column(BigInteger)
    state:Mapped[str]=mapped_column(String(30),default='queued')
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    job_id:Mapped[UUID|None]=mapped_column(ForeignKey('jobs.id'))
    manifest:Mapped[dict]=mapped_column(JSONB)
    render_hash:Mapped[str]=mapped_column(String(64))
    asset_id:Mapped[UUID|None]=mapped_column(ForeignKey('media_assets.id'),unique=True)
    content_hash:Mapped[str|None]=mapped_column(String(64))
    duration_ms:Mapped[int|None]=mapped_column(BigInteger)
    quality:Mapped[str]=mapped_column(String(30),default='unverified')
    error_code:Mapped[str|None]=mapped_column(String(100))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class RecordingReview(Base):
    __tablename__='recording_reviews'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    render_id:Mapped[UUID]=mapped_column(ForeignKey('recording_render_versions.id'),index=True)
    render_hash:Mapped[str]=mapped_column(String(64))
    content_hash:Mapped[str]=mapped_column(String(64))
    decision:Mapped[str]=mapped_column(String(20))
    reviewer_user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    reason:Mapped[str]=mapped_column(Text)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class RecordingPublication(Base):
    __tablename__='recording_publications'
    __table_args__=(UniqueConstraint('render_id','lesson_version_id','state'),)
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    project_id:Mapped[UUID]=mapped_column(ForeignKey('recording_projects.id'),index=True)
    render_id:Mapped[UUID]=mapped_column(ForeignKey('recording_render_versions.id'))
    render_hash:Mapped[str]=mapped_column(String(64))
    lesson_version_id:Mapped[UUID]=mapped_column(ForeignKey('lesson_versions.id'))
    state:Mapped[str]=mapped_column(String(20))
    actor_user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
