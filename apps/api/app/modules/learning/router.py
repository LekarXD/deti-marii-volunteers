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

# Authoring is deliberately separate from learner DTOs, including answer keys.
from . import authoring
from .schemas import AssessmentSave, AssignmentCreate, AuthorLessonView, DraftSave, LessonCreate, ReleasePublish, ReleaseRollback, TrackCreate, TrackView, VersionCommand


@router.get("/coord/learning/tracks", response_model=list[TrackView])
async def author_tracks(principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return await authoring.tracks(db, principal)


@router.post("/coord/learning/tracks", response_model=TrackView)
async def create_track(body: TrackCreate, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.create_track", body.model_dump(mode="json"), lambda: authoring.create_track(db, principal, body.key, body.title))


@router.get("/coord/learning/tracks/{track_id}", response_model=TrackView)
async def author_track(track_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return await authoring.track_view(db, principal, track_id)


@router.post("/coord/learning/lessons", response_model=AuthorLessonView)
async def create_lesson(body: LessonCreate, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.create_lesson", body.model_dump(mode="json"), lambda: authoring.create_lesson(db, principal, body.track_id, body.key, body.title))


@router.get("/coord/learning/lessons/{lesson_id}", response_model=AuthorLessonView)
async def author_lesson(lesson_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return await authoring.author_lesson(db, principal, lesson_id)


@router.post("/coord/learning/lessons/{lesson_id}/edit", response_model=AuthorLessonView)
async def begin_lesson_edit(lesson_id: UUID, body: EmptyCommand, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.begin_edit", {"id":str(lesson_id)}, lambda: authoring.begin_edit(db, principal, lesson_id))


@router.put("/coord/learning/lessons/{lesson_id}/draft", response_model=AuthorLessonView)
async def save_draft(lesson_id: UUID, body: DraftSave, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.save_draft", {"id":str(lesson_id), **body.model_dump(mode="json")}, lambda: authoring.save_draft(db, principal, lesson_id, body))


@router.post("/coord/learning/lessons/{lesson_id}/validate")
async def validate_lesson(lesson_id: UUID, body: EmptyCommand, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.validate", {"id":str(lesson_id)}, lambda: authoring.validate_lesson(db, principal, lesson_id))


@router.post("/coord/learning/lessons/{lesson_id}/review", response_model=AuthorLessonView)
async def review_lesson(lesson_id: UUID, body: VersionCommand, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.review", {"id":str(lesson_id), **body.model_dump(mode="json")}, lambda: authoring.review_lesson(db, principal, lesson_id, body.expected_version))


@router.get("/coord/learning/lessons/{lesson_id}/preview", response_model=LessonView)
async def preview_lesson(lesson_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return await authoring.preview_lesson(db, principal, lesson_id)


@router.put("/coord/learning/tracks/{track_id}/assessment", response_model=TrackView)
async def save_assessment(track_id: UUID, body: AssessmentSave, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.save_assessment", {"id":str(track_id), **body.model_dump(mode="json")}, lambda: authoring.save_assessment(db, principal, track_id, body))


@router.post("/coord/learning/tracks/{track_id}/assessment/review", response_model=TrackView)
async def review_assessment(track_id: UUID, body: VersionCommand, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.review_assessment", {"id":str(track_id), **body.model_dump(mode="json")}, lambda: authoring.review_assessment(db, principal, track_id, body.expected_version))


@router.post("/coord/learning/tracks/{track_id}/publish", response_model=TrackView)
async def publish_release(track_id: UUID, body: ReleasePublish, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.publish", {"id":str(track_id), **body.model_dump(mode="json")}, lambda: authoring.publish_release(db, principal, track_id, body))


@router.post("/coord/learning/tracks/{track_id}/rollback", response_model=TrackView)
async def rollback_release(track_id: UUID, body: ReleaseRollback, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.rollback", {"id":str(track_id), **body.model_dump(mode="json")}, lambda: authoring.rollback_release(db, principal, track_id, body.release_id, body.expected_version))


@router.post("/coord/learning/tracks/{track_id}/archive", response_model=TrackView)
async def archive_track(track_id: UUID, body: VersionCommand, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.archive", {"id":str(track_id), **body.model_dump(mode="json")}, lambda: authoring.archive_track(db, principal, track_id, body.expected_version))


@router.post("/coord/learning/assignments")
async def assign_release(body: AssignmentCreate, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.assign", body.model_dump(mode="json"), lambda: authoring.assign(db, principal, body))


@router.get("/learning/lessons/{version_id}/assets/{asset_id}")
async def learning_asset(version_id: UUID, asset_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    from app.core.errors import ApiError
    from app.core.models import MediaAsset
    from app.modules.assets.service import asset_content
    from sqlalchemy import select
    detail = await service.lesson_view(db, principal, version_id)
    if not any(str(block.get("asset_id")) == str(asset_id) and block.get("type") in {"video", "file"} for block in detail["blocks"]):
        raise ApiError(404, "asset_not_found", "Файл не найден")
    asset = await db.scalar(select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.foundation_id == principal.foundation_id, MediaAsset.state == "ready"))
    if asset is None:
        raise ApiError(404, "asset_not_found", "Файл не найден")
    return await asset_content(db, asset)

from .schemas import TaskSubmit, TaskSubmissionView


@router.get("/learning/assignments/{assignment_id}/tasks", response_model=list[TaskSubmissionView])
async def get_tasks(assignment_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return await service.task_submissions(db, principal, assignment_id)


@router.post("/learning/lessons/{version_id}/tasks/{block_id}", response_model=TaskSubmissionView)
async def submit_task(version_id: UUID, block_id: UUID, body: TaskSubmit, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.task_submit", {"id":str(block_id), "version_id":str(version_id), **body.model_dump(mode="json")}, lambda: service.submit_task(db, principal, version_id, block_id, body))


@router.post("/coord/learning/lessons/{lesson_id}/preview/quiz/{block_position}")
async def preview_quiz(lesson_id: UUID, block_position: int, body: MiniQuizInput, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.preview_quiz", {"id":str(lesson_id),"block_position":block_position,**body.model_dump(mode="json")}, lambda: authoring.preview_quiz(db, principal, lesson_id, block_position, body.question_index, body.selected_option))


@router.get("/coord/learning/recipients")
async def learning_recipients(search: str = "", principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from app.core.models import User
    authoring.permission(principal, "learning.write")
    user_query = select(User).where(User.foundation_id == principal.foundation_id, User.account_state == "active")
    if search:
        user_query = user_query.where(User.display_name.ilike("%" + search[:100].replace("%", "").replace("_", "") + "%"))
    users = (await db.scalars(user_query.order_by(User.display_name).limit(100))).all()
    options = [dict(user_id=str(user.id), registration_id=None, application_id=None, label=user.display_name) for user in users]
    if principal.has_permission("candidates.read"):
        from app.modules.applications.service import learning_recipient_options
        applications = await learning_recipient_options(db, principal, search)
        options += [dict(user_id=None, registration_id=None, application_id=str(item["application_id"]), label=item["label"]) for item in applications]
    return options


@router.post("/coord/learning/lessons/{lesson_id}/archive", response_model=AuthorLessonView)
async def archive_lesson(lesson_id: UUID, body: VersionCommand, request: Request, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db), key: str | None = Header(None, alias="Idempotency-Key")):
    return await command(db, principal, request, key, "learning.archive_lesson", {"id":str(lesson_id), **body.model_dump(mode="json")}, lambda: authoring.archive_lesson(db, principal, lesson_id, body.expected_version))
