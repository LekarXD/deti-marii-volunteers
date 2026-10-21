"""Report snapshots, review history and source-bound operational digest scheduling."""
from datetime import date,datetime
from uuid import UUID,uuid4
from sqlalchemy import CheckConstraint,Date,DateTime,ForeignKey,ForeignKeyConstraint,Integer,String,Text,UniqueConstraint,Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.core.clock import utcnow
from app.core.db import Base

class ReportDraft(Base):
    __tablename__='report_drafts'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    scope_type:Mapped[str]=mapped_column(String(20))
    scope_id:Mapped[UUID|None]=mapped_column(ForeignKey('participant_groups.id'))
    kind:Mapped[str]=mapped_column(String(20))
    title:Mapped[str]=mapped_column(String(300))
    period_from:Mapped[date]=mapped_column(Date)
    period_to:Mapped[date]=mapped_column(Date)
    definitions_version:Mapped[str]=mapped_column(String(30),default='reports-v1')
    metrics_snapshot:Mapped[dict]=mapped_column(JSONB)
    source_hash:Mapped[str]=mapped_column(String(64))
    sections:Mapped[list]=mapped_column(JSONB)
    state:Mapped[str]=mapped_column(String(20),default='draft')
    version:Mapped[int]=mapped_column(Integer,default=1)
    created_by:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('id','foundation_id'),ForeignKeyConstraint(['scope_id','foundation_id'],['participant_groups.id','participant_groups.foundation_id']),ForeignKeyConstraint(['created_by','foundation_id'],['users.id','users.foundation_id']),CheckConstraint("((scope_type='foundation' AND scope_id IS NULL) OR (scope_type='group' AND scope_id IS NOT NULL)) AND kind IN ('grant','weekly') AND state IN ('draft','confirmed','withdrawn') AND period_to>=period_from AND version>0",name='ck_report_draft'),Index('ix_report_scope_period','foundation_id','scope_type','scope_id','period_from','id'))

class ReportRevision(Base):
    __tablename__='report_revisions'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    report_id:Mapped[UUID]=mapped_column(ForeignKey('report_drafts.id'),index=True)
    version:Mapped[int]=mapped_column(Integer)
    snapshot:Mapped[dict]=mapped_column(JSONB)
    reason:Mapped[str]=mapped_column(String(80))
    actor_id:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('report_id','version'),UniqueConstraint('id','report_id'))

class ReportExport(Base):
    __tablename__='report_exports'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    report_id:Mapped[UUID]=mapped_column(ForeignKey('report_drafts.id'))
    revision_id:Mapped[UUID]=mapped_column(ForeignKey('report_revisions.id'))
    format:Mapped[str]=mapped_column(String(10))
    asset_id:Mapped[UUID|None]=mapped_column(ForeignKey('media_assets.id'))
    state:Mapped[str]=mapped_column(String(20),default='preparing')
    created_by:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(ForeignKeyConstraint(['report_id','foundation_id'],['report_drafts.id','report_drafts.foundation_id']),ForeignKeyConstraint(['revision_id','report_id'],['report_revisions.id','report_revisions.report_id']),ForeignKeyConstraint(['created_by','foundation_id'],['users.id','users.foundation_id']),CheckConstraint("format IN ('csv','pdf','docx') AND state IN ('preparing','ready','failed')",name='ck_report_export'),Index('ix_report_export_source','report_id','revision_id','format','created_at'))

class ReportDigestSchedule(Base):
    __tablename__='report_digest_schedules'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    owner_user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    scope_type:Mapped[str]=mapped_column(String(20))
    scope_id:Mapped[UUID|None]=mapped_column(ForeignKey('participant_groups.id'))
    enabled:Mapped[bool]=mapped_column(default=False)
    weekday:Mapped[int]=mapped_column(Integer,default=0)
    minute_of_day:Mapped[int]=mapped_column(Integer,default=540)
    timezone:Mapped[str]=mapped_column(String(100),default='Europe/Moscow')
    version:Mapped[int]=mapped_column(Integer,default=1)
    next_run_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    last_run_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    state:Mapped[str]=mapped_column(String(30),default='disabled')
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('id','foundation_id'),ForeignKeyConstraint(['scope_id','foundation_id'],['participant_groups.id','participant_groups.foundation_id']),ForeignKeyConstraint(['owner_user_id','foundation_id'],['users.id','users.foundation_id']),CheckConstraint("((scope_type='foundation' AND scope_id IS NULL) OR (scope_type='group' AND scope_id IS NOT NULL)) AND weekday BETWEEN 0 AND 6 AND minute_of_day BETWEEN 0 AND 1439 AND version>0 AND state IN ('disabled','scheduled','blocked','failed')",name='ck_report_digest'),Index('ix_report_digest_due','foundation_id','enabled','next_run_at'))

class ReportDigestRecipient(Base):
    __tablename__='report_digest_recipients'
    schedule_id:Mapped[UUID]=mapped_column(ForeignKey('report_digest_schedules.id'),primary_key=True)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'),primary_key=True)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    __table_args__=(ForeignKeyConstraint(['schedule_id','foundation_id'],['report_digest_schedules.id','report_digest_schedules.foundation_id']),ForeignKeyConstraint(['user_id','foundation_id'],['users.id','users.foundation_id']))

class ReportDigestDelivery(Base):
    __tablename__='report_digest_deliveries'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    schedule_id:Mapped[UUID]=mapped_column(ForeignKey('report_digest_schedules.id'))
    schedule_version:Mapped[int]=mapped_column(Integer)
    recipient_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    period_from:Mapped[date]=mapped_column(Date)
    period_to:Mapped[date]=mapped_column(Date)
    outbox_id:Mapped[UUID|None]=mapped_column(ForeignKey('outbox_messages.id'))
    state:Mapped[str]=mapped_column(String(20),default='queued')
    reason:Mapped[str]=mapped_column(String(200),default='')
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(ForeignKeyConstraint(['schedule_id','foundation_id'],['report_digest_schedules.id','report_digest_schedules.foundation_id']),ForeignKeyConstraint(['recipient_id','foundation_id'],['users.id','users.foundation_id']),UniqueConstraint('schedule_id','period_to','recipient_id'),CheckConstraint("state IN ('queued','suppressed','failed') AND period_to>=period_from",name='ck_report_digest_delivery'))
