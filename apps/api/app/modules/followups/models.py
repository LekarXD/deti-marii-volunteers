from datetime import date,datetime
from uuid import UUID,uuid4
from sqlalchemy import BigInteger,Boolean,CheckConstraint,Date,DateTime,ForeignKey,ForeignKeyConstraint,Index,String,Text,UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.core.db import Base
from app.core.clock import utcnow


class FirstVisitChecklist(Base):
    __tablename__='first_visit_checklists'
    assignment_id:Mapped[UUID]=mapped_column(primary_key=True)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    checklist_version:Mapped[int]=mapped_column(default=1)
    checked_keys:Mapped[list]=mapped_column(JSONB,default=list)
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(ForeignKeyConstraint(['assignment_id','foundation_id'],['assignments.id','assignments.foundation_id']),CheckConstraint('checklist_version > 0 AND version > 0'))


class AssignmentQuestion(Base):
    __tablename__='assignment_questions'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    assignment_id:Mapped[UUID]
    user_id:Mapped[UUID]
    group_id:Mapped[UUID|None]
    kind:Mapped[str]=mapped_column(String(30),default='question')
    text:Mapped[str]=mapped_column(Text)
    restricted:Mapped[bool]=mapped_column(Boolean,default=False)
    public_answer:Mapped[str]=mapped_column(Text,default='')
    answered_by:Mapped[UUID|None]=mapped_column(ForeignKey('users.id'))
    answered_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('id','foundation_id'),ForeignKeyConstraint(['assignment_id','foundation_id'],['assignments.id','assignments.foundation_id']),
        ForeignKeyConstraint(['user_id','foundation_id'],['users.id','users.foundation_id']),ForeignKeyConstraint(['group_id','foundation_id'],['participant_groups.id','participant_groups.foundation_id']),
        CheckConstraint("kind IN ('question','alternate_date')"),Index('ix_assignment_questions_owner','foundation_id','user_id','assignment_id','created_at'))


class Reflection(Base):
    __tablename__='reflections'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    assignment_id:Mapped[UUID]=mapped_column(unique=True)
    user_id:Mapped[UUID]
    group_id:Mapped[UUID|None]
    mood:Mapped[str|None]=mapped_column(String(20))
    text:Mapped[str]=mapped_column(Text,default='')
    unexpected:Mapped[str]=mapped_column(Text,default='')
    help:Mapped[str]=mapped_column(String(10),default='later')
    help_text:Mapped[str]=mapped_column(Text,default='')
    continuation:Mapped[str]=mapped_column(String(15),default='discuss')
    restricted:Mapped[bool]=mapped_column(Boolean,default=False)
    submitted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('id','foundation_id'),ForeignKeyConstraint(['assignment_id','foundation_id'],['assignments.id','assignments.foundation_id']),
        ForeignKeyConstraint(['user_id','foundation_id'],['users.id','users.foundation_id']),ForeignKeyConstraint(['group_id','foundation_id'],['participant_groups.id','participant_groups.foundation_id']),
        CheckConstraint("mood IS NULL OR mood IN ('great','good','ok','hard','awful')"),CheckConstraint("help IN ('later','yes','no')"),
        CheckConstraint("continuation IN ('discuss','yes','other','pause','finish')"),Index('ix_reflections_staff','foundation_id','submitted_at','group_id','id'),Index('ix_reflections_user','foundation_id','user_id','submitted_at'))


class ReflectionReview(Base):
    __tablename__='reflection_reviews'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    reflection_id:Mapped[UUID]
    revision:Mapped[int]=mapped_column(BigInteger)
    decision:Mapped[str]=mapped_column(String(20))
    public_message:Mapped[str]=mapped_column(Text)
    next_date:Mapped[date|None]=mapped_column(Date)
    assigned_user_id:Mapped[UUID]
    follow_up_task_id:Mapped[UUID|None]=mapped_column(ForeignKey('follow_up_tasks.id'))
    author_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('reflection_id','revision'),ForeignKeyConstraint(['reflection_id','foundation_id'],['reflections.id','reflections.foundation_id']),
        ForeignKeyConstraint(['assigned_user_id','foundation_id'],['users.id','users.foundation_id']),CheckConstraint("decision IN ('next_date','other_role','discussion','pause','finish')"))


class ReflectionReviewNote(Base):
    __tablename__='reflection_review_notes'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    review_id:Mapped[UUID]=mapped_column(ForeignKey('reflection_reviews.id'),unique=True)
    text:Mapped[str]=mapped_column(Text)
    author_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)


class SupportSignal(Base):
    __tablename__='support_signals'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    reflection_id:Mapped[UUID|None]=mapped_column(unique=True)
    question_id:Mapped[UUID|None]=mapped_column(unique=True)
    subject_user_id:Mapped[UUID]
    group_id:Mapped[UUID|None]
    restricted:Mapped[bool]=mapped_column(Boolean,default=False)
    priority:Mapped[str]=mapped_column(String(10),default='normal')
    state:Mapped[str]=mapped_column(String(15),default='open')
    assigned_user_id:Mapped[UUID|None]
    follow_up_task_id:Mapped[UUID|None]=mapped_column(ForeignKey('follow_up_tasks.id'))
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(ForeignKeyConstraint(['reflection_id','foundation_id'],['reflections.id','reflections.foundation_id']),ForeignKeyConstraint(['question_id','foundation_id'],['assignment_questions.id','assignment_questions.foundation_id']),
        ForeignKeyConstraint(['subject_user_id','foundation_id'],['users.id','users.foundation_id']),ForeignKeyConstraint(['group_id','foundation_id'],['participant_groups.id','participant_groups.foundation_id']),ForeignKeyConstraint(['assigned_user_id','foundation_id'],['users.id','users.foundation_id']),
        CheckConstraint('(reflection_id IS NULL) <> (question_id IS NULL)'),CheckConstraint("state IN ('open','in_progress','resolved','dismissed')"),CheckConstraint("priority IN ('normal','high','urgent')"),Index('ix_support_signals_queue','foundation_id','restricted','state','priority','created_at','id'))


class SupportSignalEvent(Base):
    __tablename__='support_signal_events'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    signal_id:Mapped[UUID]=mapped_column(ForeignKey('support_signals.id'))
    revision:Mapped[int]=mapped_column(BigInteger)
    action:Mapped[str]=mapped_column(String(20))
    reason:Mapped[str]=mapped_column(Text)
    author_id:Mapped[str]=mapped_column(String(100))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('signal_id','revision'),)


class ReflectionAudioUpload(Base):
    """Private source intent; processing and transcript use the shared Job/AIRun stores."""
    __tablename__='reflection_audio_uploads'
    asset_id:Mapped[UUID]=mapped_column(primary_key=True)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    assignment_id:Mapped[UUID]
    user_id:Mapped[UUID]
    request_session_id:Mapped[UUID]=mapped_column(ForeignKey('sessions.id'))
    run_id:Mapped[UUID|None]=mapped_column(ForeignKey('ai_runs.id'),unique=True)
    duration_seconds:Mapped[int|None]
    cancelled_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(ForeignKeyConstraint(['asset_id','foundation_id'],['media_assets.id','media_assets.foundation_id']),
        ForeignKeyConstraint(['assignment_id','foundation_id'],['assignments.id','assignments.foundation_id']),
        ForeignKeyConstraint(['user_id','foundation_id'],['users.id','users.foundation_id']),
        CheckConstraint('version > 0 AND (duration_seconds IS NULL OR (duration_seconds > 0 AND duration_seconds <= 180))'),
        Index('ix_reflection_audio_owner','foundation_id','user_id','assignment_id','created_at'))

from .rule_models import SignalRuleSettings,RuleSignal
