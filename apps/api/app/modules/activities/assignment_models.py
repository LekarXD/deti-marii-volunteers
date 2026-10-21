from datetime import datetime
from uuid import UUID,uuid4
from sqlalchemy import BigInteger,CheckConstraint,DateTime,ForeignKey,ForeignKeyConstraint,Index,Integer,String,Text,UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB,UUID as PGUUID
from sqlalchemy.orm import Mapped,mapped_column
from app.core.clock import utcnow
from app.core.db import Base


class OpportunityResponse(Base):
    __tablename__='opportunity_responses'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    opportunity_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    state:Mapped[str]=mapped_column(String(30),default='submitted')
    decision_reason:Mapped[str]=mapped_column(Text,default='')
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('opportunity_id','user_id'),
        ForeignKeyConstraint(['opportunity_id','foundation_id'],['opportunities.id','opportunities.foundation_id']),
        CheckConstraint("state IN ('submitted','under_review','approved','declined','preparation_requested','withdrawn')"),
        Index('ix_opportunity_response_scope','foundation_id','state','id'))


class OpportunityResponseEvent(Base):
    __tablename__='opportunity_response_events'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    response_id:Mapped[UUID]=mapped_column(ForeignKey('opportunity_responses.id'))
    version:Mapped[int]=mapped_column(BigInteger)
    state:Mapped[str]=mapped_column(String(30))
    reason:Mapped[str]=mapped_column(Text,default='')
    actor_id:Mapped[str]=mapped_column(String(200))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('response_id','version'),)


class Assignment(Base):
    __tablename__='assignments'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    occurrence_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    staffing_need_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    group_id_snapshot:Mapped[UUID|None]=mapped_column(PGUUID(as_uuid=True))
    status:Mapped[str]=mapped_column(String(20),default='invited')
    approved_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    confirmed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    conditions_version:Mapped[int]=mapped_column(BigInteger)
    conditions_snapshot:Mapped[dict]=mapped_column(JSONB)
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('occurrence_id','user_id'),UniqueConstraint('id','foundation_id'),
        ForeignKeyConstraint(['occurrence_id','foundation_id'],['event_occurrences.id','event_occurrences.foundation_id']),
        ForeignKeyConstraint(['staffing_need_id','occurrence_id','foundation_id'],['staffing_needs.id','staffing_needs.occurrence_id','staffing_needs.foundation_id']),
        ForeignKeyConstraint(['group_id_snapshot','foundation_id'],['participant_groups.id','participant_groups.foundation_id']),
        CheckConstraint("status IN ('invited','confirmed','declined','cancelled','expired')"),
        CheckConstraint("status <> 'confirmed' OR confirmed_at IS NOT NULL"),
        Index('ix_assignment_user_scope','foundation_id','user_id','status','id'),Index('ix_assignment_need_status','staffing_need_id','status'))


class AssignmentEvent(Base):
    __tablename__='assignment_events'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    assignment_id:Mapped[UUID]=mapped_column(ForeignKey('assignments.id'))
    version:Mapped[int]=mapped_column(BigInteger)
    command:Mapped[str]=mapped_column(String(50))
    status:Mapped[str]=mapped_column(String(20))
    reason:Mapped[str]=mapped_column(Text,default='')
    actor_id:Mapped[str]=mapped_column(String(200))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('assignment_id','version'),)


class AssignmentParticipantSnapshot(Base):
    __tablename__='assignment_participant_snapshots'
    assignment_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True)
    participant_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True)
    foundation_id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True))
    __table_args__=(ForeignKeyConstraint(['assignment_id','foundation_id'],['assignments.id','assignments.foundation_id']),ForeignKeyConstraint(['participant_id','foundation_id'],['participants.id','participants.foundation_id']))


class AssignmentRequirementReview(Base):
    __tablename__='assignment_requirement_reviews'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    assignment_id:Mapped[UUID]=mapped_column(ForeignKey('assignments.id'))
    requirement_key:Mapped[str]=mapped_column(String(100))
    conditions_version:Mapped[int]=mapped_column(BigInteger)
    state:Mapped[str]=mapped_column(String(20))
    reason:Mapped[str]=mapped_column(Text)
    author_id:Mapped[str]=mapped_column(String(200))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(CheckConstraint("state IN ('fulfilled','waived','pending')"),Index('ix_assignment_requirement','assignment_id','conditions_version','requirement_key','created_at'))


class Attendance(Base):
    __tablename__='attendance'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    assignment_id:Mapped[UUID]=mapped_column(ForeignKey('assignments.id'),unique=True)
    outcome:Mapped[str]=mapped_column(String(20))
    minutes:Mapped[int]=mapped_column(Integer)
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(CheckConstraint("outcome IN ('attended','absent')"),CheckConstraint('minutes >= 0'),CheckConstraint("outcome <> 'absent' OR minutes = 0"))


class AttendanceEvent(Base):
    __tablename__='attendance_events'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    attendance_id:Mapped[UUID]=mapped_column(ForeignKey('attendance.id'))
    assignment_id:Mapped[UUID]=mapped_column(ForeignKey('assignments.id'))
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    version:Mapped[int]=mapped_column(BigInteger)
    old_minutes:Mapped[int]=mapped_column(Integer)
    new_minutes:Mapped[int]=mapped_column(Integer)
    reason:Mapped[str]=mapped_column(Text)
    actor_id:Mapped[str]=mapped_column(String(200))
    ledger_state:Mapped[str]=mapped_column(String(20),default='pending')
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('attendance_id','version'),)
