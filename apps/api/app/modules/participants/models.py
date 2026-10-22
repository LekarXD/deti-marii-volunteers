"""Participant records; private notes deliberately live outside the safe projection."""
from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, Date, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class Participant(Base):
    __tablename__ = "participants"
    __table_args__ = (
        UniqueConstraint("foundation_id", "id", name="uq_participants_scope_id"),
        ForeignKeyConstraint(["photo_asset_id", "foundation_id"], ["media_assets.id", "media_assets.foundation_id"], name="fk_participant_photo_scope"),
        CheckConstraint("lifecycle IN ('active', 'archived')", name="ck_participants_lifecycle"),
        CheckConstraint("birth_year IS NULL OR birth_year BETWEEN 1900 AND 2200", name="ck_participants_birth_year"),
        Index("ix_participants_scope_lifecycle_name", "foundation_id", "lifecycle", "display_name", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200))
    birth_year: Mapped[int | None]
    lifecycle: Mapped[str] = mapped_column(String(20), default="active")
    about: Mapped[str] = mapped_column(Text, default="")
    photo_asset_id: Mapped[UUID | None]
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ParticipantBriefing(Base):
    __tablename__ = "participant_briefings"
    participant_id: Mapped[UUID] = mapped_column(ForeignKey("participants.id"), primary_key=True)
    communication: Mapped[str] = mapped_column(Text, default="")
    support: Mapped[str] = mapped_column(Text, default="")
    interests: Mapped[str] = mapped_column(Text, default="")
    # Short memo chips (presets live in the web app); the text fields above are an optional note.
    communication_tags: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    support_tags: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    interests_tags: Mapped[list[str]] = mapped_column(JSONB, default=list, server_default=text("'[]'::jsonb"))
    version: Mapped[int] = mapped_column(BigInteger, default=1)


class ParticipantPrivateNote(Base):
    __tablename__ = "participant_private_notes"
    __table_args__ = (
        ForeignKeyConstraint(["foundation_id", "participant_id"], ["participants.foundation_id", "participants.id"]),
        Index("ix_participant_private_notes_scope_person", "foundation_id", "participant_id", "created_at", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"))
    participant_id: Mapped[UUID]
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ParticipantGroup(Base):
    __tablename__ = "participant_groups"
    __table_args__ = (
        UniqueConstraint("foundation_id", "id", name="uq_participant_groups_scope_id"),
        ForeignKeyConstraint(["leader_id", "foundation_id"], ["users.id", "users.foundation_id"], name="fk_group_leader_scope"),
        ForeignKeyConstraint(["coordinator_id", "foundation_id"], ["users.id", "users.foundation_id"], name="fk_group_coordinator_scope"),
        CheckConstraint("lifecycle IN ('active', 'archived')", name="ck_participant_groups_lifecycle"),
        Index("ix_participant_groups_scope_lifecycle_title", "foundation_id", "lifecycle", "title", "id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"))
    title: Mapped[str] = mapped_column(String(200))
    schedule: Mapped[str] = mapped_column(Text, default="")
    location: Mapped[str] = mapped_column(Text, default="")
    leader_id: Mapped[UUID | None]
    coordinator_id: Mapped[UUID | None]
    lifecycle: Mapped[str] = mapped_column(String(20), default="active")
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class GroupMembership(Base):
    """A membership interval is [valid_from, valid_until), with no open-ended overlap."""
    __tablename__ = "group_memberships"
    __table_args__ = (
        ForeignKeyConstraint(["foundation_id", "group_id"], ["participant_groups.foundation_id", "participant_groups.id"]),
        ForeignKeyConstraint(["foundation_id", "participant_id"], ["participants.foundation_id", "participants.id"]),
        CheckConstraint("valid_until IS NULL OR valid_until > valid_from", name="ck_group_membership_period"),
        Index("ix_group_memberships_scope_group_period", "foundation_id", "group_id", "valid_from", "valid_until"),
        Index("ix_group_memberships_participant", "foundation_id", "participant_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"))
    group_id: Mapped[UUID]
    participant_id: Mapped[UUID]
    valid_from: Mapped[date] = mapped_column(Date)
    valid_until: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
