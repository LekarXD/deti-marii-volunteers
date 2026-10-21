"""P09 injection seam. A volunteer receives nothing until assignment access is wired.

Implementations must query current assignment state on every request (including files),
validate owner/foundation, and return the occurrence's historical participant snapshot.
Do not derive permission from the group's current membership or a browser role.
"""
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import ApiError


@dataclass(frozen=True)
class AssignmentParticipantAccess:
    assignment_id: UUID
    group_ids: tuple[UUID, ...]
    participant_ids: tuple[UUID, ...]


class AssignmentAccess(Protocol):
    async def participants(self, db: AsyncSession, principal: Principal, assignment_id: UUID) -> AssignmentParticipantAccess: ...


class UnavailableAssignmentAccess:
    async def participants(self, db: AsyncSession, principal: Principal, assignment_id: UUID) -> AssignmentParticipantAccess:
        raise ApiError(403, "assignment_access_denied", "Доступ к памятке по назначению пока недоступен.")


def get_assignment_access() -> AssignmentAccess:
    """Override this FastAPI dependency only when the P09 adapter is integrated."""
    return UnavailableAssignmentAccess()
