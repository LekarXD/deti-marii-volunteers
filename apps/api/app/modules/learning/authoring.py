"""Manual academy authoring with CAS, explicit review and immutable publication."""
from copy import deepcopy
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import ApiError
from app.core.models import User, RegistrationSession
from .models import AssessmentDraft, AssessmentQuestion, AssessmentVersion, LearningAssignment, LearningRelease, LearningTrack, Lesson, LessonBlock, LessonDraft, LessonVersion


def permission(principal: Principal, name: str):
    if not principal.has_permission(name):
        raise ApiError(403, "permission_denied", "Недостаточно прав для работы с материалами")


async def track(db, principal, track_id, *, lock=False):
    query = select(LearningTrack).where(LearningTrack.id == track_id, LearningTrack.foundation_id == principal.foundation_id)
    if lock:
        query = query.with_for_update()
    value = await db.scalar(query)
    if value is None:
        raise ApiError(404, "track_not_found", "Трек не найден")
    return value


async def lesson(db, principal, lesson_id, *, lock=False):
    query = select(Lesson).where(Lesson.id == lesson_id, Lesson.foundation_id == principal.foundation_id)
    if lock:
        query = query.with_for_update()
    value = await db.scalar(query)
    if value is None:
        raise ApiError(404, "lesson_not_found", "Урок не найден")
    return value


def check_version(actual, expected):
    if actual != expected:
        raise ApiError(409, "version_conflict", "Материал изменён. Обновите страницу, чтобы сохранить новую редакцию", current_version=actual)


def draft_view(value):
    return None if value is None else dict(id=str(value.id), version=value.version, title=value.title, minutes=value.minutes, source=value.source, blocks=value.blocks, status=value.status)


async def author_lesson(db, principal, lesson_id):
    permission(principal, "learning.read")
    value = await lesson(db, principal, lesson_id)
    draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == value.id))
    return dict(id=value.id, track_id=value.track_id, key=value.key, current_version_id=value.current_version_id, publication_revision=value.publication_revision, archived=value.archived, draft=draft_view(draft))


async def track_view(db, principal, track_id):
    permission(principal, "learning.read")
    value = await track(db, principal, track_id)
    lessons = (await db.scalars(select(Lesson).where(Lesson.track_id == value.id).order_by(Lesson.key))).all()
    assessment = await db.scalar(select(AssessmentDraft).where(AssessmentDraft.track_id == value.id))
    releases = (await db.scalars(select(LearningRelease).where(LearningRelease.track_id == value.id).order_by(LearningRelease.number.desc()))).all()
    return dict(id=value.id, key=value.key, title=value.title, version=value.version, archived=value.archived, current_release_id=value.current_release_id, lessons=[await author_lesson(db, principal, item.id) for item in lessons], assessment=(dict(id=str(assessment.id), title=assessment.title, intro=assessment.intro, questions=assessment.questions, version=assessment.version, status=assessment.status) if assessment else None), releases=[dict(id=str(r.id), number=r.number, published_at=r.published_at.isoformat(), lesson_version_ids=r.lesson_version_ids) for r in releases])


async def tracks(db, principal):
    permission(principal, "learning.read")
    ids = (await db.scalars(select(LearningTrack.id).where(LearningTrack.foundation_id == principal.foundation_id).order_by(LearningTrack.title))).all()
    return [await track_view(db, principal, item) for item in ids]


async def create_track(db, principal, key, title):
    permission(principal, "learning.write")
    existing = await db.scalar(select(LearningTrack.id).where(LearningTrack.foundation_id == principal.foundation_id, LearningTrack.key == key))
    if existing:
        raise ApiError(409, "track_key_exists", "Трек с таким кодом уже существует")
    value = LearningTrack(foundation_id=principal.foundation_id, key=key, title=title.strip())
    db.add(value)
    await db.flush()
    return await track_view(db, principal, value.id)


async def create_lesson(db, principal, track_id, key, title):
    permission(principal, "learning.write")
    parent = await track(db, principal, track_id, lock=True)
    if parent.archived:
        raise ApiError(409, "track_archived", "Трек в архиве")
    existing = await db.scalar(select(Lesson.id).where(Lesson.track_id == track_id, Lesson.key == key))
    if existing:
        raise ApiError(409, "lesson_key_exists", "Урок с таким кодом уже существует")
    value = Lesson(foundation_id=principal.foundation_id, track_id=track_id, key=key)
    db.add(value)
    await db.flush()
    db.add(LessonDraft(lesson_id=value.id, foundation_id=principal.foundation_id, title=title.strip(), blocks=[]))
    parent.version += 1
    await db.flush()
    return await author_lesson(db, principal, value.id)


async def begin_edit(db, principal, lesson_id):
    permission(principal, "learning.write")
    value = await lesson(db, principal, lesson_id, lock=True)
    draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == value.id))
    if draft is None:
        if not value.current_version_id:
            raise ApiError(409, "lesson_no_version", "У урока пока нет опубликованной версии")
        version = await db.get(LessonVersion, value.current_version_id)
        blocks = (await db.scalars(select(LessonBlock).where(LessonBlock.lesson_version_id == version.id).order_by(LessonBlock.position))).all()
        draft = LessonDraft(lesson_id=value.id, foundation_id=principal.foundation_id, title=version.title, minutes=version.minutes, source=version.source, blocks=[deepcopy(block.content) for block in blocks])
        db.add(draft)
        await db.flush()
    return await author_lesson(db, principal, value.id)


async def save_draft(db, principal, lesson_id, body):
    permission(principal, "learning.write")
    value = await lesson(db, principal, lesson_id, lock=True)
    draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == value.id).with_for_update())
    if draft is None:
        raise ApiError(409, "draft_missing", "Сначала откройте редактирование урока")
    check_version(draft.version, body.expected_version)
    # Preserve arbitrary supported source blocks as JSON snapshots; validation is explicit.
    draft.title, draft.minutes, draft.source, draft.blocks = body.title.strip(), body.minutes, body.source, deepcopy(body.blocks)
    draft.version += 1
    draft.status, draft.reviewed_by = "draft", None
    await db.flush()
    return await author_lesson(db, principal, lesson_id)


def question_errors(questions):
    errors = []
    if not questions:
        errors.append("Добавьте хотя бы один вопрос")
    for i, question in enumerate(questions):
        options = question.get("o")
        answer = question.get("a")
        if not isinstance(question.get("q"), str) or not question["q"].strip():
            errors.append(f"Вопрос {i + 1}: заполните текст")
        if not isinstance(options, list) or not 2 <= len(options) <= 12 or any(not isinstance(x, str) or not x.strip() for x in options):
            errors.append(f"Вопрос {i + 1}: нужны от 2 до 12 вариантов")
        if type(answer) is not int or not isinstance(options, list) or not 0 <= answer < len(options):
            errors.append(f"Вопрос {i + 1}: укажите верный ответ")
        if not isinstance(question.get("e"), str) or not question["e"].strip():
            errors.append(f"Вопрос {i + 1}: добавьте объяснение")
    return errors


async def block_errors(db, principal, blocks):
    errors = []
    allowed = {"lead", "text", "facts", "timeline", "icards", "story", "rules", "phrases", "quiz", "video", "file", "task", "callout"}
    if not blocks:
        errors.append("Добавьте хотя бы один блок")
    for i, block in enumerate(blocks):
        kind = block.get("type")
        if kind not in allowed:
            errors.append(f"Блок {i + 1}: неизвестный тип")
        if kind in {"lead", "text", "task", "callout"} and not str(block.get("text", "")).strip():
            errors.append(f"Блок {i + 1}: заполните текст")
        if kind in {"facts", "timeline", "icards", "story", "rules", "phrases"} and not isinstance(block.get("items"), list):
            errors.append(f"Блок {i + 1}: заполните элементы")
        if kind == "quiz":
            errors += [f"Блок {i + 1}: {error}" for error in question_errors(block.get("items", []))]
        if kind in {"video", "file"}:
            # Preserve the source introduction's honest empty-video placeholder.
            if kind == "video" and not block.get("asset_id") and not block.get("src"):
                continue
            if block.get("src"):
                errors.append(f"Блок {i + 1}: используйте защищённый файл, а не внешний адрес")
                continue
            try:
                from app.modules.assets.service import require_asset
                asset = await require_asset(db, principal, UUID(str(block.get("asset_id"))))
                if kind == "video" and not asset.content_type.startswith("video/"):
                    errors.append(f"Блок {i + 1}: нужен видеофайл")
            except (ApiError, ValueError, TypeError):
                errors.append(f"Блок {i + 1}: файл недоступен или ещё не готов")
    return errors


async def validate_lesson(db, principal, lesson_id):
    permission(principal, "learning.read")
    value = await lesson(db, principal, lesson_id)
    draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == value.id))
    if draft is None:
        return dict(valid=bool(value.current_version_id), errors=[] if value.current_version_id else ["Нет черновика"], version=0)
    errors = await block_errors(db, principal, draft.blocks)
    if not draft.title.strip():
        errors.append("Заполните название")
    return dict(valid=not errors, errors=errors, version=draft.version)


async def review_lesson(db, principal, lesson_id, expected_version):
    permission(principal, "learning.write")
    await lesson(db, principal, lesson_id, lock=True)
    draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == lesson_id).with_for_update())
    if draft is None:
        raise ApiError(409, "draft_missing", "Нет черновика")
    check_version(draft.version, expected_version)
    validation = await validate_lesson(db, principal, lesson_id)
    if not validation["valid"]:
        raise ApiError(422, "lesson_invalid", "Проверьте блоки урока", field_errors={"blocks": validation["errors"]})
    draft.status, draft.reviewed_by = "reviewed", principal.user_id
    draft.version += 1
    await db.flush()
    return await author_lesson(db, principal, lesson_id)


async def preview_lesson(db, principal, lesson_id):
    from .service import learner_block
    permission(principal, "learning.read")
    value = await lesson(db, principal, lesson_id)
    draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == value.id))
    if draft:
        # The exact learner renderer schema, no progress reads or writes.
        blocks = [learner_block(LessonBlock(id=uuid4(), content=block)) for block in draft.blocks]
        return dict(id=value.id, title=draft.title, minutes=draft.minutes, blocks=blocks)
    version = await db.get(LessonVersion, value.current_version_id) if value.current_version_id else None
    if version is None:
        raise ApiError(404, "preview_unavailable", "Нет материала для просмотра")
    blocks = (await db.scalars(select(LessonBlock).where(LessonBlock.lesson_version_id == version.id).order_by(LessonBlock.position))).all()
    return dict(id=value.id, title=version.title, minutes=version.minutes, blocks=[learner_block(block) for block in blocks])


async def save_assessment(db, principal, track_id, body):
    permission(principal, "learning.write")
    await track(db, principal, track_id, lock=True)
    draft = await db.scalar(select(AssessmentDraft).where(AssessmentDraft.track_id == track_id).with_for_update())
    check_version(draft.version if draft else 0, body.expected_version)
    if draft is None:
        draft = AssessmentDraft(track_id=track_id, foundation_id=principal.foundation_id, title=body.title, intro=body.intro, questions=body.questions)
        db.add(draft)
    else:
        draft.title, draft.intro, draft.questions = body.title.strip(), body.intro, deepcopy(body.questions)
        draft.version += 1
        draft.status, draft.reviewed_by = "draft", None
    await db.flush()
    return await track_view(db, principal, track_id)


async def review_assessment(db, principal, track_id, expected_version):
    permission(principal, "learning.write")
    await track(db, principal, track_id, lock=True)
    draft = await db.scalar(select(AssessmentDraft).where(AssessmentDraft.track_id == track_id).with_for_update())
    if draft is None:
        raise ApiError(409, "draft_missing", "Нет черновика теста")
    check_version(draft.version, expected_version)
    errors = question_errors(draft.questions)
    if errors:
        raise ApiError(422, "assessment_invalid", "Проверьте вопросы теста", field_errors={"questions": errors})
    draft.status, draft.reviewed_by = "reviewed", principal.user_id
    draft.version += 1
    await db.flush()
    return await track_view(db, principal, track_id)


async def publish_lesson_version(db, principal, lesson_id, expected_draft_version, expected_publication_revision):
    """P18E extension: exact draft + pointer CAS; called inside release transaction."""
    permission(principal, "learning.publish")
    value = await lesson(db, principal, lesson_id, lock=True)
    check_version(value.publication_revision, expected_publication_revision)
    draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == lesson_id).with_for_update())
    if draft is None or draft.status != "reviewed":
        raise ApiError(409, "review_required", "Сначала проверьте и согласуйте редакцию урока")
    check_version(draft.version, expected_draft_version)
    validation = await validate_lesson(db, principal, lesson_id)
    if not validation["valid"]:
        raise ApiError(422, "lesson_invalid", "Материал не прошёл проверку", field_errors={"blocks": validation["errors"]})
    number = (await db.scalar(select(func.max(LessonVersion.number)).where(LessonVersion.lesson_id == value.id)) or 0) + 1
    version = LessonVersion(lesson_id=value.id, number=number, title=draft.title, minutes=draft.minutes, source=draft.source)
    db.add(version)
    await db.flush()
    for position, block in enumerate(draft.blocks):
        db.add(LessonBlock(lesson_version_id=version.id, position=position, content=deepcopy(block)))
    value.current_version_id = version.id
    value.publication_revision += 1
    draft.status = "published"
    await db.flush()
    return version.id


async def publish_release(db, principal, track_id, body):
    permission(principal, "learning.publish")
    parent = await track(db, principal, track_id, lock=True)
    check_version(parent.version, body.expected_version)
    if parent.archived or len(body.lesson_ids) != len(set(body.lesson_ids)):
        raise ApiError(422, "release_invalid", "Проверьте состав трека")
    versions = []
    # Lock stable lessons in stable order, avoiding races/deadlocks across release commands.
    locked = {key: await lesson(db, principal, key, lock=True) for key in sorted(body.lesson_ids)}
    for lesson_id in body.lesson_ids:
        value = locked[lesson_id]
        if value.track_id != parent.id or value.archived:
            raise ApiError(422, "release_lesson_invalid", "Урок не входит в активные материалы этого трека")
        draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == value.id).with_for_update())
        check_version(value.publication_revision, body.lesson_publication_revisions.get(value.id, -1))
        check_version(draft.version if draft else 0, body.lesson_draft_versions.get(value.id, -1))
        if draft and draft.status != "published":
            version_id = await publish_lesson_version(db, principal, value.id, draft.version, value.publication_revision)
        elif value.current_version_id:
            version_id = value.current_version_id
        else:
            raise ApiError(409, "review_required", "Урок ещё не согласован")
        versions.append(str(version_id))
    current = await db.get(LearningRelease, parent.current_release_id) if parent.current_release_id else None
    assessment_id = current.assessment_version_id if current else None
    assessment = await db.scalar(select(AssessmentDraft).where(AssessmentDraft.track_id == parent.id).with_for_update())
    if assessment and assessment.status != "published":
        if assessment.status != "reviewed":
            raise ApiError(409, "assessment_review_required", "Сначала согласуйте тест")
        errors = question_errors(assessment.questions)
        if errors:
            raise ApiError(422, "assessment_invalid", "Проверьте вопросы", field_errors={"questions":errors})
        version = AssessmentVersion(foundation_id=principal.foundation_id, title=assessment.title, intro=assessment.intro)
        db.add(version)
        await db.flush()
        assessment_id = version.id
        for position, question in enumerate(assessment.questions):
            db.add(AssessmentQuestion(assessment_version_id=version.id, position=position, prompt=question["q"], options=deepcopy(question["o"]), correct_option=question["a"], explanation=question["e"]))
        assessment.status = "published"
    number = (await db.scalar(select(func.max(LearningRelease.number)).where(LearningRelease.track_id == parent.id)) or 0) + 1
    release = LearningRelease(track_id=parent.id, foundation_id=principal.foundation_id, number=number, title=parent.title, intro=body.intro, lesson_version_ids=versions, assessment_version_id=assessment_id, reacknowledgement_required=body.reacknowledgement_required, changed_required_items=body.changed_required_items)
    db.add(release)
    await db.flush()
    parent.current_release_id = release.id
    parent.version += 1
    return await track_view(db, principal, parent.id)


async def rollback_release(db, principal, track_id, release_id, expected_version):
    permission(principal, "learning.publish")
    parent = await track(db, principal, track_id, lock=True)
    check_version(parent.version, expected_version)
    target = await db.scalar(select(LearningRelease).where(LearningRelease.id == release_id, LearningRelease.track_id == parent.id, LearningRelease.foundation_id == principal.foundation_id))
    if target is None:
        raise ApiError(404, "release_not_found", "Версия трека не найдена")
    parent.current_release_id = target.id
    parent.version += 1
    # Stable primary pointers follow the rollback without mutating any old snapshot.
    for version_id in target.lesson_version_ids:
        version = await db.get(LessonVersion, UUID(version_id))
        stable = await lesson(db, principal, version.lesson_id, lock=True)
        stable.current_version_id = version.id
        stable.publication_revision += 1
    return await track_view(db, principal, track_id)


async def archive_track(db, principal, track_id, expected_version):
    permission(principal, "learning.publish")
    parent = await track(db, principal, track_id, lock=True)
    check_version(parent.version, expected_version)
    parent.archived = True
    parent.version += 1
    return await track_view(db, principal, parent.id)


async def assign(db, principal, body):
    permission(principal, "learning.write")
    if bool(body.user_id) == bool(body.registration_id):
        raise ApiError(422, "assignment_owner_required", "Укажите одного получателя")
    owner = await db.get(User if body.user_id else RegistrationSession, body.user_id or body.registration_id)
    release = await db.scalar(select(LearningRelease).where(LearningRelease.id == body.release_id, LearningRelease.foundation_id == principal.foundation_id))
    if owner is None or owner.foundation_id != principal.foundation_id or release is None:
        raise ApiError(404, "assignment_target_not_found", "Получатель или опубликованная версия не найдены")
    parent = await track(db, principal, release.track_id, lock=True)
    if parent.archived:
        raise ApiError(409, "track_archived", "Трек в архиве")
    query = select(LearningAssignment).where(LearningAssignment.release_id == release.id)
    query = query.where(LearningAssignment.user_id == body.user_id) if body.user_id else query.where(LearningAssignment.registration_id == body.registration_id)
    existing = await db.scalar(query)
    if existing:
        return dict(id=str(existing.id), release_id=str(existing.release_id))
    value = LearningAssignment(foundation_id=principal.foundation_id, release_id=release.id, user_id=body.user_id, registration_id=body.registration_id)
    db.add(value)
    await db.flush()
    return dict(id=str(value.id), release_id=str(value.release_id))
