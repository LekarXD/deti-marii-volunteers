"""P07 role directory and opportunity conditions. History never follows mutable defaults."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def now():
    return datetime.now(timezone.utc)


class VolunteerRole(Base):
    __tablename__ = "volunteer_roles"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200))
    normalized_title: Mapped[str] = mapped_column(String(300))
    task: Mapped[str] = mapped_column(Text, default="")
    preparation_defaults: Mapped[list] = mapped_column(JSONB, default=list)
    approval_policy: Mapped[str] = mapped_column(String(30), default="coordinator")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_by: Mapped[str] = mapped_column(String(200))
    __table_args__ = (
        UniqueConstraint("id", "foundation_id"),
        CheckConstraint("version > 0"),
        CheckConstraint("approval_policy IN ('coordinator', 'self_confirmation')"),
        Index("uq_active_role_title", "foundation_id", "normalized_title", unique=True, postgresql_where=text("archived_at IS NULL")),
        Index("ix_roles_foundation_list", "foundation_id", "archived_at", "title", "id"),
    )


class VolunteerRoleVersion(Base):
    __tablename__ = "volunteer_role_versions"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("volunteer_roles.id"))
    version: Mapped[int] = mapped_column(BigInteger)
    snapshot: Mapped[dict] = mapped_column(JSONB)
    actor_id: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("role_id", "version"), UniqueConstraint("id", "role_id"))


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"))
    title: Mapped[str] = mapped_column(String(200))
    program: Mapped[str] = mapped_column(String(200), default="")
    audience: Mapped[str] = mapped_column(Text, default="")
    task: Mapped[str] = mapped_column(Text, default="")
    conditions: Mapped[str] = mapped_column(Text, default="")
    regularity: Mapped[str] = mapped_column(String(40), default="once")
    location: Mapped[str] = mapped_column(String(500), default="")
    schedule: Mapped[str] = mapped_column(String(500), default="")
    format: Mapped[str] = mapped_column(String(20), default="onsite")
    preparation_requirements: Mapped[list] = mapped_column(JSONB, default=list)
    approval_policy: Mapped[str] = mapped_column(String(30), default="coordinator")
    state: Mapped[str] = mapped_column(String(20), default="draft")
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_by: Mapped[str] = mapped_column(String(200))
    __table_args__ = (
        UniqueConstraint("id", "foundation_id"),
        CheckConstraint("state IN ('draft', 'published', 'paused', 'closed')"),
        CheckConstraint("regularity IN ('regular', 'periodic', 'once', 'tasks')"),
        CheckConstraint("format IN ('onsite', 'online', 'hybrid')"),
        CheckConstraint("approval_policy IN ('coordinator', 'self_confirmation')"),
        CheckConstraint("version > 0"),
        Index("ix_opportunities_list", "foundation_id", "state", "title", "id"),
    )


class OpportunityRoleLink(Base):
    __tablename__ = "opportunity_role_links"
    opportunity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    role_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    foundation_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    role_version_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    __table_args__ = (
        ForeignKeyConstraint(["opportunity_id", "foundation_id"], ["opportunities.id", "opportunities.foundation_id"]),
        ForeignKeyConstraint(["role_id", "foundation_id"], ["volunteer_roles.id", "volunteer_roles.foundation_id"]),
        ForeignKeyConstraint(["role_version_id", "role_id"], ["volunteer_role_versions.id", "volunteer_role_versions.role_id"]),
    )


class OpportunityVersion(Base):
    __tablename__ = "opportunity_versions"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    opportunity_id: Mapped[UUID] = mapped_column(ForeignKey("opportunities.id"))
    version: Mapped[int] = mapped_column(BigInteger)
    snapshot: Mapped[dict] = mapped_column(JSONB)
    actor_id: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("opportunity_id", "version"),)

# Imported here for the shared model loader and Alembic registry.
from .calendar_models import EventSeries, EventSeriesNeedTemplate, EventOccurrence, OccurrenceOverride, StaffingNeed, EventRevision  # noqa: E402,F401
