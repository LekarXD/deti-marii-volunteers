"""Versioned authored scenarios, private attempts, and evidence-based evaluations."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.clock import utcnow
from app.core.db import Base


class SimulatorScenario(Base):
    __tablename__ = 'simulator_scenarios'
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'))
    title: Mapped[str] = mapped_column(String(200))
    draft: Mapped[dict] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    publication_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_by: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('id', 'foundation_id'), ForeignKeyConstraint(['publication_id','foundation_id'],['simulator_scenario_versions.id','simulator_scenario_versions.foundation_id'],name='fk_scenario_publication_scope',use_alter=True), Index('ix_simulator_scenario_scope', 'foundation_id', 'archived_at', 'id'))


class RubricVersion(Base):
    __tablename__ = 'rubric_versions'
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    scenario_id: Mapped[UUID] = mapped_column(ForeignKey('simulator_scenarios.id'))
    version: Mapped[int] = mapped_column(BigInteger)
    criteria: Mapped[list] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('scenario_id', 'version'), UniqueConstraint('id','scenario_id'))


class SimulatorScenarioVersion(Base):
    __tablename__ = 'simulator_scenario_versions'
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'))
    scenario_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    version: Mapped[int] = mapped_column(BigInteger)
    content: Mapped[dict] = mapped_column(JSONB)
    rubric_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    review_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    test_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    published_by: Mapped[str] = mapped_column(String(200))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('scenario_id', 'version'), UniqueConstraint('id', 'foundation_id'),
        UniqueConstraint('id','rubric_version_id','foundation_id'),
        ForeignKeyConstraint(['scenario_id', 'foundation_id'], ['simulator_scenarios.id', 'simulator_scenarios.foundation_id']),
        ForeignKeyConstraint(['rubric_version_id','scenario_id'],['rubric_versions.id','rubric_versions.scenario_id']),
        ForeignKeyConstraint(['review_id','scenario_id'],['simulator_scenario_reviews.id','simulator_scenario_reviews.scenario_id']),
        ForeignKeyConstraint(['test_run_id','scenario_id'],['simulator_test_runs.id','simulator_test_runs.scenario_id']))


class SimulatorScenarioReview(Base):
    __tablename__ = 'simulator_scenario_reviews'
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    scenario_id: Mapped[UUID] = mapped_column(ForeignKey('simulator_scenarios.id'))
    draft_version: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String(64))
    decision: Mapped[str] = mapped_column(String(30))
    reason: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('id','scenario_id'), CheckConstraint("decision IN ('approved', 'changes_requested')"), Index('ix_simulator_review_draft', 'scenario_id', 'draft_version'))


class SimulatorTestRun(Base):
    __tablename__ = 'simulator_test_runs'
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'))
    scenario_id: Mapped[UUID] = mapped_column(ForeignKey('simulator_scenarios.id'))
    draft_version: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(String(64))
    scenario_snapshot: Mapped[dict] = mapped_column(JSONB)
    dataset_hash: Mapped[str] = mapped_column(String(64))
    limits: Mapped[dict] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(30), default='queued')
    actor_id: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('id','scenario_id'), Index('ix_simulator_test_scope', 'foundation_id', 'scenario_id', 'draft_version'),)


class SimulatorTestCaseRun(Base):
    __tablename__ = 'simulator_test_case_runs'
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    test_run_id: Mapped[UUID] = mapped_column(ForeignKey('simulator_test_runs.id'))
    case_key: Mapped[str] = mapped_column(String(100))
    ai_run_id: Mapped[UUID] = mapped_column(ForeignKey('ai_runs.id'))
    expected_scores: Mapped[dict] = mapped_column(JSONB)
    result: Mapped[dict | None] = mapped_column(JSONB)
    state: Mapped[str] = mapped_column(String(30), default='pending')
    __table_args__ = (UniqueConstraint('test_run_id', 'case_key'), UniqueConstraint('ai_run_id'))


class SimulationSession(Base):
    __tablename__ = 'simulation_sessions'
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey('users.id'))
    registration_id: Mapped[UUID | None] = mapped_column(ForeignKey('registration_sessions.id'))
    scenario_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    rubric_version_id: Mapped[UUID] = mapped_column(ForeignKey('rubric_versions.id'))
    parent_session_id: Mapped[UUID | None] = mapped_column(ForeignKey('simulation_sessions.id'))
    state: Mapped[str] = mapped_column(String(30), default='active')
    pending_ai_run_id: Mapped[UUID | None] = mapped_column(ForeignKey('ai_runs.id'))
    pending_kind: Mapped[str | None] = mapped_column(String(30))
    provider_error: Mapped[str | None] = mapped_column(String(100))
    hint_count: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('id', 'foundation_id'), UniqueConstraint('id','rubric_version_id'), CheckConstraint('(user_id IS NULL) <> (registration_id IS NULL)'),
        CheckConstraint("state IN ('active', 'paused', 'waiting_reply', 'evaluating', 'finished', 'stopped')"),
        ForeignKeyConstraint(['scenario_version_id','rubric_version_id','foundation_id'], ['simulator_scenario_versions.id','simulator_scenario_versions.rubric_version_id','simulator_scenario_versions.foundation_id']),
        Index('ix_simulation_owner', 'foundation_id', 'user_id', 'registration_id', 'created_at', 'id'))


class SimulationTurn(Base):
    __tablename__ = 'simulation_turns'
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey('simulation_sessions.id'))
    ordinal: Mapped[int] = mapped_column(Integer)
    speaker: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20))
    ai_run_id: Mapped[UUID | None] = mapped_column(ForeignKey('ai_runs.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint('session_id', 'ordinal'), CheckConstraint("speaker IN ('character','volunteer','hint','system')"), CheckConstraint("source IN ('authored','volunteer','ai')"))


class SimulationEvaluation(Base):
    __tablename__ = 'simulation_evaluations'
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey('simulation_sessions.id'))
    rubric_version_id: Mapped[UUID] = mapped_column(ForeignKey('rubric_versions.id'))
    version: Mapped[int] = mapped_column(BigInteger)
    ai_run_id: Mapped[UUID] = mapped_column(ForeignKey('ai_runs.id'), unique=True)
    prompt_version: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(30), default='pending')
    result: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('session_id', 'version'), ForeignKeyConstraint(['session_id','rubric_version_id'],['simulation_sessions.id','simulation_sessions.rubric_version_id']))


class EvaluationAppeal(Base):
    __tablename__ = 'evaluation_appeals'
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'))
    evaluation_id: Mapped[UUID] = mapped_column(ForeignKey('simulation_evaluations.id'), unique=True)
    text: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(30), default='submitted')
    response: Mapped[str | None] = mapped_column(Text)
    corrected_result: Mapped[dict | None] = mapped_column(JSONB)
    reviewer_id: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("state IN ('submitted','under_review','resolved')"), Index('ix_evaluation_appeal_scope', 'foundation_id', 'state', 'id'))


class SimulationSupportRequest(Base):
    __tablename__ = 'simulation_support_requests'
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'))
    session_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    text: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(30), default='open')
    response: Mapped[str | None] = mapped_column(Text)
    reviewer_id: Mapped[str | None] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (ForeignKeyConstraint(['session_id', 'foundation_id'], ['simulation_sessions.id', 'simulation_sessions.foundation_id']),
        CheckConstraint("state IN ('open','resolved')"), Index('ix_simulation_support_scope', 'foundation_id', 'state', 'id'))
