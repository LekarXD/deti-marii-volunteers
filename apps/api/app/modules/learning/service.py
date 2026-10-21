from copy import deepcopy
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import ApiError
from .models import AssessmentAnswer, AssessmentAttempt, AssessmentQuestion, AssessmentVersion, LearningAssignment, LearningRelease, LearningTrack, Lesson, LessonBlock, LessonProgress, LessonVersion


def owner_scope(principal: Principal):
    if principal.user_id is not None:
        return LearningAssignment.user_id == principal.user_id
    if principal.registration_id is not None:
        return LearningAssignment.registration_id == principal.registration_id
    raise ApiError(403, "owner_required", "Нужна личная сессия")


async def assignment(db: AsyncSession, principal: Principal, assignment_id: UUID, *, lock=False):
    query = select(LearningAssignment).where(LearningAssignment.id == assignment_id, LearningAssignment.foundation_id == principal.foundation_id, owner_scope(principal))
    if lock:
        query = query.with_for_update()
    value = await db.scalar(query)
    if value is None:
        raise ApiError(404, "assignment_not_found", "Обучение не найдено")
    return value


async def ensure_introduction(db: AsyncSession, principal: Principal):
    track = await db.scalar(select(LearningTrack).where(LearningTrack.foundation_id == principal.foundation_id, LearningTrack.key == "introduction", LearningTrack.archived.is_(False)))
    if not track or not track.current_release_id:
        return
    values = dict(id=uuid4(), foundation_id=principal.foundation_id, release_id=track.current_release_id, user_id=principal.user_id, registration_id=None if principal.user_id else principal.registration_id)
    owner_scope(principal)
    await db.execute(insert(LearningAssignment).values(**values).on_conflict_do_nothing())


async def preparation(db: AsyncSession, principal: Principal):
    await ensure_introduction(db, principal)
    assignments = list((await db.scalars(select(LearningAssignment).where(LearningAssignment.foundation_id == principal.foundation_id, owner_scope(principal)).order_by(LearningAssignment.assigned_at.desc(), LearningAssignment.id))).all())
    views = []
    introduction_completed = False
    for item in assignments:
        release = await db.get(LearningRelease, item.release_id)
        track = await db.get(LearningTrack, release.track_id)
        introduction_completed = introduction_completed or (track.key == "introduction" and item.completed_at is not None)
        completed_versions = set((await db.scalars(select(LessonProgress.lesson_version_id).where(LessonProgress.assignment_id == item.id))).all())
        lessons = []
        for version_id in release.lesson_version_ids:
            version = await db.get(LessonVersion, UUID(version_id))
            lesson = await db.get(Lesson, version.lesson_id)
            lessons.append(dict(id=version.id, lesson_id=lesson.id, key=lesson.key, title=version.title, minutes=version.minutes, completed=version.id in completed_versions))
        latest = await db.scalar(select(AssessmentAttempt).where(AssessmentAttempt.assignment_id == item.id).order_by(AssessmentAttempt.started_at.desc(), AssessmentAttempt.id.desc()).limit(1))
        views.append(dict(id=item.id, track_id=track.id, track_key=track.key, release_id=release.id, release_number=release.number, title=release.title, intro=release.intro, lessons=lessons, assessment_version_id=release.assessment_version_id, completed=item.completed_at is not None, acknowledged=item.acknowledged_at is not None, latest_attempt_id=latest.id if latest else None, latest_attempt_state=("submitted" if latest.submitted_at else "active") if latest else None, reacknowledgement_required=release.reacknowledgement_required))
    return dict(assignments=views, introduction_completed=introduction_completed, booking_requires_introduction=False)


def learner_block(block: LessonBlock):
    content = {key: deepcopy(value) for key, value in block.content.items() if not key.startswith("_")}
    if content.get("type") == "quiz":
        content["items"] = [{"q": x["q"], "o": x["o"]} for x in content.get("items", [])]
    return {"id": str(block.id), **content}


async def lesson_view(db: AsyncSession, principal: Principal, version_id: UUID):
    scoped = (await db.scalars(select(LearningRelease).join(LearningAssignment, LearningAssignment.release_id == LearningRelease.id).where(LearningAssignment.foundation_id == principal.foundation_id, owner_scope(principal)))).all()
    if not any(str(version_id) in release.lesson_version_ids for release in scoped):
        raise ApiError(404, "lesson_not_found", "Материал не найден")
    version = await db.get(LessonVersion, version_id)
    blocks = (await db.scalars(select(LessonBlock).where(LessonBlock.lesson_version_id == version_id).order_by(LessonBlock.position))).all()
    return dict(id=version.id, title=version.title, minutes=version.minutes, blocks=[learner_block(block) for block in blocks])


async def mini_quiz(db: AsyncSession, principal: Principal, version_id: UUID, block_id: UUID, question_index: int, selected_option: int):
    await lesson_view(db, principal, version_id)
    block = await db.scalar(select(LessonBlock).where(LessonBlock.id == block_id, LessonBlock.lesson_version_id == version_id))
    if block is None or block.content.get("type") != "quiz" or question_index >= len(block.content["items"]):
        raise ApiError(404, "question_not_found", "Вопрос не найден")
    question = block.content["items"][question_index]
    if selected_option >= len(question["o"]):
        raise ApiError(422, "invalid_option", "Выберите один из вариантов")
    return dict(correct=selected_option == question["a"], explanation=question["e"])


async def update_completion(db: AsyncSession, item: LearningAssignment):
    release = await db.get(LearningRelease, item.release_id)
    progress = set(str(value) for value in (await db.scalars(select(LessonProgress.lesson_version_id).where(LessonProgress.assignment_id == item.id))).all())
    submitted = await db.scalar(select(AssessmentAttempt.id).where(AssessmentAttempt.assignment_id == item.id, AssessmentAttempt.submitted_at.is_not(None)).limit(1))
    if set(release.lesson_version_ids).issubset(progress) and (submitted or release.assessment_version_id is None) and item.acknowledged_at:
        item.completed_at = item.completed_at or datetime.now(timezone.utc)


async def complete_lesson(db: AsyncSession, principal: Principal, version_id: UUID, assignment_id: UUID):
    item = await assignment(db, principal, assignment_id, lock=True)
    release = await db.get(LearningRelease, item.release_id)
    if str(version_id) not in release.lesson_version_ids:
        raise ApiError(404, "lesson_not_found", "Материал не найден")
    from .models import LessonTaskSubmission
    required = (await db.scalars(select(LessonBlock).where(LessonBlock.lesson_version_id == version_id))).all()
    required_ids = {block.id for block in required if block.content.get("type") == "task" and block.content.get("required") is True}
    submitted_ids = set((await db.scalars(select(LessonTaskSubmission.block_id).where(LessonTaskSubmission.assignment_id == item.id))).all())
    if not required_ids.issubset(submitted_ids):
        raise ApiError(422, "tasks_incomplete", "Сначала сохраните ответы на обязательные задания")
    await db.execute(insert(LessonProgress).values(id=uuid4(), assignment_id=item.id, lesson_version_id=version_id).on_conflict_do_nothing())
    await update_completion(db, item)
    return dict(completed=True, assignment_completed=item.completed_at is not None)


async def acknowledge(db: AsyncSession, principal: Principal, assignment_id: UUID):
    item = await assignment(db, principal, assignment_id, lock=True)
    item.acknowledged_at = item.acknowledged_at or datetime.now(timezone.utc)
    await update_completion(db, item)
    return dict(acknowledged=True, assignment_completed=item.completed_at is not None)


async def questions(db: AsyncSession, version_id: UUID):
    return list((await db.scalars(select(AssessmentQuestion).where(AssessmentQuestion.assessment_version_id == version_id).order_by(AssessmentQuestion.position))).all())


async def attempt_view(db: AsyncSession, principal: Principal, attempt_id: UUID, *, lock=False):
    # Scope before locking and before revealing any question or history.
    query = select(AssessmentAttempt).join(LearningAssignment).where(AssessmentAttempt.id == attempt_id, LearningAssignment.foundation_id == principal.foundation_id, owner_scope(principal))
    if lock:
        query = query.with_for_update(of=AssessmentAttempt)
    item = await db.scalar(query)
    if item is None:
        raise ApiError(404, "attempt_not_found", "Попытка не найдена")
    assessment = await db.get(AssessmentVersion, item.assessment_version_id)
    qs = await questions(db, item.assessment_version_id)
    answers = (await db.scalars(select(AssessmentAnswer).where(AssessmentAnswer.attempt_id == item.id))).all()
    by_id = {q.id: q for q in qs}
    return item, dict(id=item.id, title=assessment.title, intro=assessment.intro, assignment_id=item.assignment_id, assessment_version_id=item.assessment_version_id, state="submitted" if item.submitted_at else "active", questions=[dict(id=q.id, prompt=q.prompt, options=q.options) for q in qs], answers=[dict(question_id=a.question_id, selected_option=a.selected_option, correct=a.selected_option == by_id[a.question_id].correct_option, explanation=by_id[a.question_id].explanation) for a in answers], score=item.score if item.submitted_at else None, total=len(qs))


async def start_attempt(db: AsyncSession, principal: Principal, version_id: UUID, assignment_id: UUID | None = None):
    query = select(LearningAssignment).join(LearningRelease).where(LearningAssignment.foundation_id == principal.foundation_id, owner_scope(principal), LearningRelease.assessment_version_id == version_id).order_by(LearningAssignment.assigned_at.desc(), LearningAssignment.id.desc()).limit(1).with_for_update(of=LearningAssignment)
    if assignment_id is not None:
        query = query.where(LearningAssignment.id == assignment_id)
    item = await db.scalar(query)
    if item is None:
        raise ApiError(404, "assessment_not_found", "Тест не найден")
    active = await db.scalar(select(AssessmentAttempt).where(AssessmentAttempt.assignment_id == item.id, AssessmentAttempt.submitted_at.is_(None)))
    if active is None:
        active = AssessmentAttempt(assignment_id=item.id, assessment_version_id=version_id)
        db.add(active)
        await db.flush()
    return (await attempt_view(db, principal, active.id))[1]


async def answer(db: AsyncSession, principal: Principal, attempt_id: UUID, question_id: UUID, selected_option: int):
    item, _ = await attempt_view(db, principal, attempt_id, lock=True)
    if item.submitted_at:
        raise ApiError(409, "attempt_submitted", "Эта попытка уже завершена")
    question = await db.scalar(select(AssessmentQuestion).where(AssessmentQuestion.id == question_id, AssessmentQuestion.assessment_version_id == item.assessment_version_id))
    if question is None or selected_option >= len(question.options):
        raise ApiError(422, "invalid_answer", "Проверьте вопрос и вариант ответа")
    previous = await db.scalar(select(AssessmentAnswer).where(AssessmentAnswer.attempt_id == item.id, AssessmentAnswer.question_id == question_id))
    if previous and previous.selected_option != selected_option:
        raise ApiError(409, "answer_already_recorded", "Ответ уже сохранён. Новую попытку можно начать после завершения теста")
    if previous is None:
        db.add(AssessmentAnswer(attempt_id=item.id, question_id=question_id, selected_option=selected_option))
        await db.flush()
    return dict(question_id=question_id, selected_option=selected_option, correct=selected_option == question.correct_option, explanation=question.explanation)


async def submit(db: AsyncSession, principal: Principal, attempt_id: UUID):
    item, view = await attempt_view(db, principal, attempt_id, lock=True)
    if item.submitted_at is None:
        if len(view["answers"]) != view["total"]:
            raise ApiError(422, "assessment_incomplete", "Ответьте на все вопросы")
        item.score = sum(answer["correct"] for answer in view["answers"])
        item.submitted_at = datetime.now(timezone.utc)
        # Serialize with completion/acknowledgement commands on the same owner assignment.
        owned = await assignment(db, principal, item.assignment_id, lock=True)
        await db.flush()
        await update_completion(db, owned)
    return (await attempt_view(db, principal, attempt_id))[1]


async def claim_registration(db: AsyncSession, registration_id: UUID, user_id: UUID):
    """Called only inside verified identity transaction; never match by contact."""
    from app.core.models import RegistrationSession, User
    registration = await db.get(RegistrationSession, registration_id)
    user = await db.get(User, user_id)
    if registration is None or user is None or registration.foundation_id != user.foundation_id:
        raise ApiError(409, "learning_owner_conflict", "Не удалось перенести историю знакомства")
    items = list((await db.scalars(select(LearningAssignment).where(LearningAssignment.registration_id == registration_id, LearningAssignment.foundation_id == user.foundation_id).with_for_update())).all())
    for item in items:
        collision = await db.scalar(select(LearningAssignment.id).where(LearningAssignment.user_id == user_id, LearningAssignment.release_id == item.release_id))
        if collision:
            raise ApiError(409, "learning_history_conflict", "У аккаунта уже есть история этой версии знакомства. Координатор поможет сохранить обе истории")
    for item in items:
        item.user_id, item.registration_id = user_id, None
    await db.flush()


async def candidate_progress(db: AsyncSession, foundation_id: UUID, user_id: UUID | None = None, registration_id: UUID | None = None):
    """Read-only projection for scoped candidate review; never assigns a course."""
    track = await db.scalar(select(LearningTrack).where(LearningTrack.foundation_id == foundation_id, LearningTrack.key == "introduction"))
    if track is None or track.current_release_id is None:
        return dict(completed=False, completed_lessons=0, total_lessons=0, available=False)
    release = await db.get(LearningRelease, track.current_release_id)
    scope = LearningAssignment.user_id == user_id if user_id else LearningAssignment.registration_id == registration_id
    item = await db.scalar(select(LearningAssignment).where(LearningAssignment.foundation_id == foundation_id, LearningAssignment.release_id == release.id, scope)) if (user_id or registration_id) else None
    progress = list((await db.scalars(select(LessonProgress.lesson_version_id).where(LessonProgress.assignment_id == item.id))).all()) if item else []
    count = len(set(map(str, progress)).intersection(release.lesson_version_ids))
    return dict(completed=bool(item and item.completed_at), completed_lessons=count, total_lessons=len(release.lesson_version_ids), available=True)


async def task_submissions(db, principal, assignment_id):
    from .models import LessonTaskSubmission
    await assignment(db, principal, assignment_id)
    items = (await db.scalars(select(LessonTaskSubmission).where(LessonTaskSubmission.assignment_id == assignment_id))).all()
    return [dict(block_id=item.block_id, answer_text=item.answer_text, version=item.version) for item in items]


async def submit_task(db, principal, version_id, block_id, body):
    from .models import LessonTaskSubmission
    item = await assignment(db, principal, body.assignment_id, lock=True)
    release = await db.get(LearningRelease, item.release_id)
    block = await db.scalar(select(LessonBlock).where(LessonBlock.id == block_id, LessonBlock.lesson_version_id == version_id))
    if str(version_id) not in release.lesson_version_ids or block is None or block.content.get("type") != "task":
        raise ApiError(404, "task_not_found", "Задание не найдено")
    if not body.answer_text.strip():
        raise ApiError(422, "answer_empty", "Добавьте ответ на задание")
    value = await db.scalar(select(LessonTaskSubmission).where(LessonTaskSubmission.assignment_id == item.id, LessonTaskSubmission.block_id == block_id).with_for_update())
    actual = value.version if value else 0
    if actual != body.expected_version:
        raise ApiError(409, "version_conflict", "Ответ изменён. Обновите страницу", current_version=actual)
    if value is None:
        value = LessonTaskSubmission(assignment_id=item.id, lesson_version_id=version_id, block_id=block_id, answer_text=body.answer_text.strip())
        db.add(value)
    else:
        value.answer_text, value.version = body.answer_text.strip(), value.version + 1
    await db.flush()
    return dict(block_id=value.block_id, answer_text=value.answer_text, version=value.version)


async def requirement_status(db: AsyncSession, foundation_id: UUID, user_id: UUID, key: str):
    """P09 seam: only explicitly version-bound evidence; no inferred waivers."""
    kind, separator, raw_id = key.partition(":")
    if kind not in {"learning_release", "policy_ack"} or not separator:
        return None
    try:
        release_id = UUID(raw_id)
    except ValueError:
        return dict(status="pending", evidence=None)
    item = await db.scalar(select(LearningAssignment).where(LearningAssignment.foundation_id == foundation_id, LearningAssignment.user_id == user_id, LearningAssignment.release_id == release_id))
    timestamp = (item.completed_at if kind == "learning_release" else item.acknowledged_at) if item else None
    return dict(status="fulfilled" if timestamp else "pending", evidence=(dict(assignment_id=str(item.id), release_id=str(release_id), at=timestamp.isoformat()) if timestamp else None))
