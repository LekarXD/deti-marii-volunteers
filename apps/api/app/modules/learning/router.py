from uuid import UUID
from fastapi import APIRouter, Depends, Header, Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal, authz_guard, get_principal
from app.core.audit import audit
from app.core.db import get_db
from app.core.idempotency import begin_command, finish_command
from . import service
from .schemas import AcknowledgeInput, AnswerInput, AssignmentView, AttemptView, EmptyCommand, FeedbackView, LessonView, MiniQuizInput, PreparationView, ProgressInput

router = APIRouter(prefix="/api/v1", tags=["learning"])


async def command(db, principal, request, key, operation, payload, action):
    await authz_guard(db, principal)
    previous = await begin_command(db, principal, operation, key, payload)
    if previous is not None:
        await db.commit()
        return previous
    result = jsonable_encoder(await action())
    audit(db, principal, operation, "learning", payload.get("id", payload.get("assignment_id", "self")), fields=tuple(payload), request_id=getattr(request.state, "request_id", None))
    await finish_command(db, principal, operation, key, result)
    await db.commit()
    return result


@router.get("/me/preparation", response_model=PreparationView)
async def get_preparation(principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    result = await service.preparation(db, principal)
    # Persist the scoped automatic introduction assignment before reporting it.
    await db.commit()
    return result


@router.get("/learning/assignments", response_model=list[AssignmentView])
async def get_assignments(principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return (await get_preparation(principal, db))["assignments"]


@router.get("/learning/lessons/{version_id}", response_model=LessonView)
async def get_lesson(version_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return await service.lesson_view(db, principal, version_id)


@router.post("/learning/lessons/{version_id}/blocks/{block_id}/answer")
async def quiz_answer(version_id: UUID, block_id: UUID, body: MiniQuizInput, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.quiz", {"id": str(block_id), "version_id": str(version_id), **body.model_dump(mode="json")}, lambda: service.mini_quiz(db, principal, version_id, block_id, body.question_index, body.selected_option))


@router.post("/learning/progress/{version_id}/complete")
async def complete_lesson(version_id: UUID, body: ProgressInput, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.complete", {"id": str(version_id), **body.model_dump(mode="json")}, lambda: service.complete_lesson(db, principal, version_id, body.assignment_id))


@router.post("/policy-acknowledgements")
async def acknowledge(body: AcknowledgeInput, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.acknowledge", body.model_dump(mode="json"), lambda: service.acknowledge(db, principal, body.assignment_id))


@router.post("/assessments/{version_id}/attempts", response_model=AttemptView)
async def start_attempt(version_id: UUID, body: EmptyCommand, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.start_attempt", {"id": str(version_id)}, lambda: service.start_attempt(db, principal, version_id))


@router.post("/assessment-attempts/{attempt_id}/answers", response_model=FeedbackView)
async def save_answer(attempt_id: UUID, body: AnswerInput, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.answer", {"id": str(attempt_id), **body.model_dump(mode="json")}, lambda: service.answer(db, principal, attempt_id, body.question_id, body.selected_option))


@router.post("/assessment-attempts/{attempt_id}/submit", response_model=AttemptView)
async def submit_attempt(attempt_id: UUID, body: EmptyCommand, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.submit", {"id": str(attempt_id)}, lambda: service.submit(db, principal, attempt_id))


@router.get("/assessment-attempts/{attempt_id}/result", response_model=AttemptView)
async def get_result(attempt_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return (await service.attempt_view(db, principal, attempt_id))[1]
