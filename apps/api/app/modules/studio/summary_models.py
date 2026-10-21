"""Immutable after-live text revisions, explicit publication and source-bound delivery."""
from datetime import datetime
from uuid import UUID,uuid4
from sqlalchemy import CheckConstraint,DateTime,ForeignKey,Integer,String,Text,UniqueConstraint,func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.core.db import Base

class WebinarSummary(Base):
    __tablename__='studio_webinar_summaries'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    webinar_id:Mapped[UUID]=mapped_column(ForeignKey('studio_webinars.id'),unique=True)
    draft_revision:Mapped[int]=mapped_column(Integer,default=1)
    reviewed_revision:Mapped[int|None]=mapped_column(Integer)
    published_revision:Mapped[int|None]=mapped_column(Integer)
    version:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(CheckConstraint('draft_revision>0 AND version>0',name='ck_webinar_summary_revision'),)

class WebinarSummaryRevision(Base):
    __tablename__='studio_webinar_summary_revisions'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    summary_id:Mapped[UUID]=mapped_column(ForeignKey('studio_webinar_summaries.id'))
    number:Mapped[int]=mapped_column(Integer)
    title:Mapped[str]=mapped_column(String(300))
    body:Mapped[str]=mapped_column(Text)
    created_by_user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    __table_args__=(UniqueConstraint('summary_id','number'),CheckConstraint('number>0',name='ck_webinar_summary_revision_number'))

class WebinarSummaryPreview(Base):
    __tablename__='studio_webinar_summary_previews'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    summary_id:Mapped[UUID]=mapped_column(ForeignKey('studio_webinar_summaries.id'))
    published_revision:Mapped[int]=mapped_column(Integer)
    actor_user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    snapshot:Mapped[list]=mapped_column(JSONB)
    preview_hash:Mapped[str]=mapped_column(String(64))
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    consumed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))

class WebinarSummaryDelivery(Base):
    __tablename__='studio_webinar_summary_deliveries'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    summary_id:Mapped[UUID]=mapped_column(ForeignKey('studio_webinar_summaries.id'))
    published_revision:Mapped[int]=mapped_column(Integer)
    recipient_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    sender_user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    outbox_id:Mapped[UUID]=mapped_column(ForeignKey('outbox_messages.id'),unique=True)
    __table_args__=(UniqueConstraint('summary_id','published_revision','recipient_id'),)
