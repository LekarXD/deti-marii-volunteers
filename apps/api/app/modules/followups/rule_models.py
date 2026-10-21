"""Configured operational thresholds and their durable internal queue observations."""
from datetime import datetime
from uuid import UUID,uuid4
from sqlalchemy import CheckConstraint,DateTime,ForeignKey,Integer,String,UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.core.clock import utcnow
from app.core.db import Base

class SignalRuleSettings(Base):
    __tablename__='signal_rule_settings'
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),primary_key=True)
    thresholds:Mapped[dict]=mapped_column(JSONB)
    owner_user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    version:Mapped[int]=mapped_column(Integer,default=1)
    next_run_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    last_run_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    last_result:Mapped[dict]=mapped_column(JSONB,default=dict)
    __table_args__=(CheckConstraint('version>0',name='ck_signal_rule_version'),)

class RuleSignal(Base):
    __tablename__='rule_signals'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    rule:Mapped[str]=mapped_column(String(20))
    entity_id:Mapped[UUID]=mapped_column()
    group_id:Mapped[UUID|None]=mapped_column(ForeignKey('participant_groups.id'))
    subject_user_id:Mapped[UUID|None]=mapped_column(ForeignKey('users.id'))
    title:Mapped[str]=mapped_column(String(300))
    details:Mapped[dict]=mapped_column(JSONB)
    source_hash:Mapped[str]=mapped_column(String(64))
    settings_version:Mapped[int]=mapped_column(Integer)
    version:Mapped[int]=mapped_column(Integer,default=1)
    state:Mapped[str]=mapped_column(String(20),default='open')
    observed_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('foundation_id','rule','entity_id'),CheckConstraint("rule IN ('miss','quiet','learn','app','shift')",name='ck_rule_signal_kind'),CheckConstraint("state IN ('open','resolved','dismissed') AND version>0",name='ck_rule_signal_state'))
