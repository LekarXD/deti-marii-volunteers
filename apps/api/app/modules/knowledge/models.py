from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import BigInteger, Boolean, CheckConstraint, Computed, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


class KnowledgeSource(Base):
    __tablename__ = 'knowledge_sources'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'), index=True)
    owner_user_id: Mapped[UUID | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    kind: Mapped[str] = mapped_column(String(30), default='text')
    draft_body: Mapped[str] = mapped_column(Text, default='')
    draft_visibility: Mapped[str] = mapped_column(String(20), default='all')
    draft_version: Mapped[int] = mapped_column(BigInteger, default=1)
    reviewed_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    current_version_id: Mapped[UUID | None] = mapped_column(nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False)
    index_generation: Mapped[int] = mapped_column(BigInteger, default=0)
    index_state: Mapped[str] = mapped_column(String(30), default='unpublished')
    index_error: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ingest_state: Mapped[str | None] = mapped_column(String(30), nullable=True)
    ingest_error: Mapped[str | None] = mapped_column(String(100), nullable=True)
    asset_id: Mapped[UUID | None] = mapped_column(ForeignKey('media_assets.id'), nullable=True)
    lesson_version_id: Mapped[UUID | None] = mapped_column(ForeignKey('lesson_versions.id'), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SourceVersion(Base):
    __tablename__ = 'source_versions'
    __table_args__ = (UniqueConstraint('source_id','number'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_id: Mapped[UUID] = mapped_column(ForeignKey('knowledge_sources.id'), index=True)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'), index=True)
    number: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    visibility: Mapped[str] = mapped_column(String(20))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunk(Base):
    __tablename__ = 'knowledge_chunks'
    __table_args__ = (UniqueConstraint('source_version_id','position'), Index('ix_knowledge_chunks_fts','search_document',postgresql_using='gin'))
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    source_version_id: Mapped[UUID] = mapped_column(ForeignKey('source_versions.id'), index=True)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    search_document: Mapped[str] = mapped_column(TSVECTOR, Computed("to_tsvector('russian'::regconfig, translate(lower(text), 'АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ', 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'))", persisted=True))


class KnowledgeQuestion(Base):
    __tablename__ = 'knowledge_questions'
    __table_args__ = (CheckConstraint('(user_id IS NULL) <> (registration_id IS NULL)',name='knowledge_question_owner_xor'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'), index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    registration_id: Mapped[UUID | None] = mapped_column(ForeignKey('registration_sessions.id'), nullable=True)
    text: Mapped[str] = mapped_column(String(3000))
    kind: Mapped[str] = mapped_column(String(30), default='unknown')
    state: Mapped[str] = mapped_column(String(30), default='pending')
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApprovedAnswer(Base):
    __tablename__ = 'approved_answers'
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'), index=True)
    question_id: Mapped[UUID] = mapped_column(ForeignKey('knowledge_questions.id'), unique=True)
    author_user_id: Mapped[UUID] = mapped_column(ForeignKey('users.id'))
    body: Mapped[str] = mapped_column(String(12000))
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    reviewed_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    published_source_id: Mapped[UUID | None] = mapped_column(ForeignKey('knowledge_sources.id'), nullable=True)
    citations: Mapped[list] = mapped_column(JSONB, default=list)


class MentorRun(Base):
    __tablename__ = 'mentor_runs'
    __table_args__ = (CheckConstraint('(user_id IS NULL) <> (registration_id IS NULL)',name='mentor_run_owner_xor'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey('foundations.id'), index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey('users.id'), nullable=True)
    registration_id: Mapped[UUID | None] = mapped_column(ForeignKey('registration_sessions.id'), nullable=True)
    question: Mapped[str] = mapped_column(String(3000))
    ai_run_id: Mapped[UUID | None] = mapped_column(ForeignKey('ai_runs.id'), nullable=True)
    state: Mapped[str] = mapped_column(String(40), default='queued')
    answer: Mapped[str | None] = mapped_column(String(12000), nullable=True)
    citation_ids: Mapped[list] = mapped_column(JSONB, default=list)
    question_id: Mapped[UUID | None] = mapped_column(ForeignKey('knowledge_questions.id'), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
