"""Manual academy authoring with CAS, explicit review and immutable publication."""
from copy import deepcopy
from uuid import UUID, uuid4

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import Principal
from app.core.errors import ApiError
from app.core.models import User, RegistrationSession
from .models import AssessmentAttempt, AssessmentDraft, AssessmentQuestion, AssessmentVersion, LearningAssignment, LearningRelease, LearningTrack, Lesson, LessonBlock, LessonDraft, LessonProgress, LessonVersion
from .video import video_embed

ASSET_BLOCKS = {"file", "video", "image"}


def permission(principal: Principal, name: str):
    if not principal.has_permission(name):
        raise ApiError(403, "permission_denied", "Недостаточно прав для работы с материалами")


async def track(db, principal, track_id, *, lock=False):
    query = select(LearningTrack).where(LearningTrack.id == track_id, LearningTrack.foundation_id == principal.foundation_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    value = await db.scalar(query)
    if value is None:
        raise ApiError(404, "track_not_found", "Трек не найден")
    return value


async def lesson(db, principal, lesson_id, *, lock=False):
    query = select(Lesson).where(Lesson.id == lesson_id, Lesson.foundation_id == principal.foundation_id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
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
    published = await db.get(LessonVersion, value.current_version_id) if value.current_version_id else None
    return dict(id=value.id, title=draft.title if draft else published.title if published else value.key, track_id=value.track_id, key=value.key, position=value.position, stage_title=value.stage_title, current_version_id=value.current_version_id, publication_revision=value.publication_revision, archived=value.archived, draft=draft_view(draft))


def stage_groups(items):
    """Consecutive lessons with the same stage title form one stage: [(title, [items])]."""
    groups = []
    for item, title in items:
        if groups and groups[-1][0] == title:
            groups[-1][1].append(item)
        else:
            groups.append((title, [item]))
    return groups


async def track_stats(db, track_id):
    """Per person: completed any release of the course, or still learning; stuck = lessons done, test not submitted."""
    releases = {release.id: release for release in (await db.scalars(select(LearningRelease).where(LearningRelease.track_id == track_id))).all()}
    if not releases:
        return dict(completed=0, learning=0, stuck=0)
    rows = (await db.execute(select(LearningAssignment.id, LearningAssignment.user_id, LearningAssignment.registration_id, LearningAssignment.release_id, LearningAssignment.completed_at).where(LearningAssignment.release_id.in_(list(releases))))).all()
    completed = {row.user_id or row.registration_id for row in rows if row.completed_at}
    pending = [row for row in rows if row.completed_at is None and (row.user_id or row.registration_id) not in completed]
    ids = [row.id for row in pending]
    done = dict((await db.execute(select(LessonProgress.assignment_id, func.count()).where(LessonProgress.assignment_id.in_(ids)).group_by(LessonProgress.assignment_id))).all()) if ids else {}
    submitted = set((await db.scalars(select(AssessmentAttempt.assignment_id).where(AssessmentAttempt.assignment_id.in_(ids), AssessmentAttempt.submitted_at.is_not(None)))).all()) if ids else set()
    stuck = {row.user_id or row.registration_id for row in pending if releases[row.release_id].assessment_version_id and row.id not in submitted and done.get(row.id, 0) >= len(releases[row.release_id].lesson_version_ids)}
    return dict(completed=len(completed), learning=len({row.user_id or row.registration_id for row in pending}), stuck=len(stuck))


async def publish_state(db, value, lessons, views, assessment):
    if not value.current_release_id:
        return "draft"
    current = await db.get(LearningRelease, value.current_release_id)
    published = []
    for version_id in current.lesson_version_ids:
        version = await db.get(LessonVersion, UUID(version_id))
        published.append((version.lesson_id, version.id))
    titles = [stage.get("title") for stage in current.stages or [] for _ in stage.get("lesson_version_ids", [])]
    if len(titles) != len(published):
        titles = [None] * len(published)
    active = [(item, view) for item, view in zip(lessons, views) if not item.archived]
    changed = (
        [(item.id, item.current_version_id) for item, _ in active] != published
        or [item.stage_title for item, _ in active] != titles
        or any(view["draft"] and view["draft"]["status"] != "published" for _, view in active)
        or current.title != value.title
        or bool(assessment and assessment.status != "published")
    )
    return "changed" if changed else "published"


async def track_view(db, principal, track_id):
    permission(principal, "learning.read")
    value = await track(db, principal, track_id)
    lessons = (await db.scalars(select(Lesson).where(Lesson.track_id == value.id).order_by(Lesson.position, Lesson.key))).all()
    assessment = await db.scalar(select(AssessmentDraft).where(AssessmentDraft.track_id == value.id))
    releases = (await db.scalars(select(LearningRelease).where(LearningRelease.track_id == value.id).order_by(LearningRelease.number.desc()))).all()
    assessment_snapshot = None
    if assessment:
        assessment_snapshot = dict(id=str(assessment.id), title=assessment.title, intro=assessment.intro, questions=assessment.questions, version=assessment.version, status=assessment.status)
    elif value.current_release_id:
        current = await db.get(LearningRelease, value.current_release_id)
        if current and current.assessment_version_id:
            published_assessment = await db.get(AssessmentVersion, current.assessment_version_id)
            published_questions = (await db.scalars(select(AssessmentQuestion).where(AssessmentQuestion.assessment_version_id == published_assessment.id).order_by(AssessmentQuestion.position))).all()
            assessment_snapshot = dict(id=str(published_assessment.id), title=published_assessment.title, intro=published_assessment.intro, questions=[dict(q=q.prompt, o=q.options, a=q.correct_option, e=q.explanation) for q in published_questions], version=0, status="published")
    views = [await author_lesson(db, principal, item.id) for item in lessons]
    live = [(item, view) for item, view in zip(lessons, views) if not item.archived]
    has_simulator = any(block.get("type") == "sim" for _, view in live if view["draft"] for block in view["draft"]["blocks"])
    published_only = [item.current_version_id for item, view in live if not view["draft"] and item.current_version_id]
    if not has_simulator and published_only:
        has_simulator = bool(await db.scalar(select(LessonBlock.id).where(LessonBlock.lesson_version_id.in_(published_only), LessonBlock.content["type"].astext == "sim").limit(1)))
    return dict(id=value.id, key=value.key, title=value.title, description=value.description, audience=value.audience, required=value.required, version=value.version, archived=value.archived, current_release_id=value.current_release_id, publish_state=await publish_state(db, value, lessons, views, assessment), has_simulator=has_simulator, stats=await track_stats(db, value.id), lessons=views, assessment=assessment_snapshot, releases=[dict(id=str(r.id), number=r.number, intro=r.intro, published_at=r.published_at.isoformat(), lesson_version_ids=r.lesson_version_ids) for r in releases])


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


async def create_lesson(db, principal, track_id, key, title, stage_title=None):
    permission(principal, "learning.write")
    parent = await track(db, principal, track_id, lock=True)
    if parent.archived:
        raise ApiError(409, "track_archived", "Трек в архиве")
    existing = await db.scalar(select(Lesson.id).where(Lesson.track_id == track_id, Lesson.key == key))
    if existing:
        raise ApiError(409, "lesson_key_exists", "Урок с таким кодом уже существует")
    last = await db.scalar(select(func.max(Lesson.position)).where(Lesson.track_id == track_id))
    # New lessons go to the end of the course; PUT .../structure moves them.
    value = Lesson(foundation_id=principal.foundation_id, track_id=track_id, key=key, position=0 if last is None else last + 1, stage_title=(stage_title or "").strip() or None)
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
        # A copy of the current version is not a change yet: it stays "published" until edited.
        draft = LessonDraft(lesson_id=value.id, foundation_id=principal.foundation_id, title=version.title, minutes=version.minutes, source=version.source, blocks=[deepcopy(block.content) for block in blocks], status="published")
        db.add(draft)
        await db.flush()
    return await author_lesson(db, principal, value.id)


async def save_draft(db, principal, lesson_id, body):
    permission(principal, "learning.write")
    value = await lesson(db, principal, lesson_id, lock=True)
    draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == value.id).with_for_update().execution_options(populate_existing=True))
    if draft is None:
        raise ApiError(409, "draft_missing", "Сначала откройте редактирование урока")
    check_version(draft.version, body.expected_version)
    # Newly bound private assets require owner or platform asset permission.
    await authorize_new_assets(db, principal, value, draft, body.blocks)
    # Preserve arbitrary supported source blocks as JSON snapshots; validation is explicit.
    draft.title, draft.minutes, draft.source, draft.blocks = body.title.strip(), body.minutes, body.source, normalize_blocks(body.blocks)
    draft.version += 1
    draft.status, draft.reviewed_by = "draft", None
    await db.flush()
    return await author_lesson(db, principal, lesson_id)


def question_errors(questions):
    errors = []
    if not isinstance(questions, list):
        return ["Вопросы должны быть списком"]
    if not questions:
        errors.append("Добавьте хотя бы один вопрос")
    for i, question in enumerate(questions):
        if not isinstance(question, dict):
            errors.append(f"Вопрос {i + 1}: некорректный формат")
            continue
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


def normalize_blocks(blocks):
    """External video embeds are always derived by the server from the pasted link."""
    result = deepcopy(blocks)
    for block in result:
        if block.get("type") == "video":
            block.pop("embed_url", None)
            block.pop("provider", None)
            found = video_embed(block.get("url")) if block.get("url") else None
            if found:
                block["provider"], block["embed_url"] = found
    return result


async def block_errors(db, principal, blocks):
    errors = []
    allowed = {"lead", "text", "facts", "timeline", "icards", "story", "rules", "phrases", "quiz", "video", "file", "task", "callout", "image", "sim"}
    if not blocks:
        errors.append("Добавьте хотя бы один блок")
    for i, block in enumerate(blocks):
        kind = block.get("type")
        if kind not in allowed:
            errors.append(f"Блок {i + 1}: неизвестный тип")
        if kind == "task" and "required" in block and type(block["required"]) is not bool:
            errors.append(f"Блок {i + 1}: проверьте обязательность задания")
        if kind in {"lead", "text", "task", "callout"} and not str(block.get("text", "")).strip():
            errors.append(f"Блок {i + 1}: заполните текст")
        if kind in {"facts", "timeline", "icards", "story", "rules", "phrases"}:
            items = block.get("items")
            if not isinstance(items, list) or not items:
                errors.append(f"Блок {i + 1}: заполните элементы")
            elif kind == "rules" and any(not isinstance(item, str) or not item.strip() for item in items):
                errors.append(f"Блок {i + 1}: заполните текст правил")
            elif kind == "icards" and any(not isinstance(item, dict) or not all(isinstance(item.get(key), str) and item[key].strip() for key in ["title", "text"]) for item in items):
                errors.append(f"Блок {i + 1}: заполните карточки")
            elif kind in {"facts", "timeline", "story", "phrases"}:
                count = 3 if kind in {"timeline", "story"} else 2
                if any(not isinstance(item, list) or len(item) < count or any(not isinstance(cell, str) for cell in item) for item in items):
                    errors.append(f"Блок {i + 1}: проверьте строки")
        if kind == "quiz":
            errors += [f"Блок {i + 1}: {error}" for error in question_errors(block.get("items", []))]
        if kind == "sim":
            from app.modules.simulator.models import SimulatorScenario
            try:
                scenario = await db.scalar(select(SimulatorScenario.id).where(SimulatorScenario.id == UUID(str(block.get("scenario_id"))), SimulatorScenario.foundation_id == principal.foundation_id, SimulatorScenario.publication_id.is_not(None), SimulatorScenario.archived_at.is_(None)))
            except (ValueError, TypeError):
                scenario = None
            if scenario is None:
                errors.append(f"Блок {i + 1}: выберите опубликованный сценарий тренажёра")
        if kind == "video" and block.get("url"):
            if block.get("asset_id") or block.get("src"):
                errors.append(f"Блок {i + 1}: оставьте либо файл, либо ссылку на видео")
            elif video_embed(block["url"]) is None:
                errors.append(f"Блок {i + 1}: нужна ссылка на VK Видео, Rutube или YouTube")
            continue
        if kind == "image" and not block.get("asset_id"):
            errors.append(f"Блок {i + 1}: загрузите картинку")
            continue
        if kind in ASSET_BLOCKS:
            # Preserve the source introduction's honest empty-video placeholder.
            if kind == "video" and not block.get("asset_id") and not block.get("src"):
                continue
            if block.get("src"):
                errors.append(f"Блок {i + 1}: используйте защищённый файл, а не внешний адрес")
                continue
            try:
                from app.core.models import MediaAsset
                asset = await db.scalar(select(MediaAsset).where(MediaAsset.id == UUID(str(block.get("asset_id"))), MediaAsset.foundation_id == principal.foundation_id, MediaAsset.state == "ready"))
                if asset is None:
                    raise ApiError(404, "asset_not_found", "Файл недоступен")
                if kind == "video" and not asset.content_type.startswith("video/"):
                    errors.append(f"Блок {i + 1}: нужен видеофайл")
                if kind == "image" and not asset.content_type.startswith("image/"):
                    errors.append(f"Блок {i + 1}: нужна картинка")
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
    draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == lesson_id).with_for_update().execution_options(populate_existing=True))
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
        validation = await validate_lesson(db, principal, lesson_id)
        if not validation["valid"]:
            raise ApiError(422, "lesson_invalid", "Сначала исправьте блоки урока", field_errors={"blocks":validation["errors"]})
        # The exact learner renderer schema, no progress reads or writes.
        blocks = [{**learner_block(LessonBlock(id=uuid4(), content=block)), "id": str(position)} for position, block in enumerate(draft.blocks)]
        return dict(id=value.id, title=draft.title, minutes=draft.minutes, blocks=blocks)
    version = await db.get(LessonVersion, value.current_version_id) if value.current_version_id else None
    if version is None:
        raise ApiError(404, "preview_unavailable", "Нет материала для просмотра")
    blocks = (await db.scalars(select(LessonBlock).where(LessonBlock.lesson_version_id == version.id).order_by(LessonBlock.position))).all()
    return dict(id=value.id, title=version.title, minutes=version.minutes, blocks=[{**learner_block(block), "id": str(position)} for position, block in enumerate(blocks)])


async def save_assessment(db, principal, track_id, body):
    permission(principal, "learning.write")
    await track(db, principal, track_id, lock=True)
    draft = await db.scalar(select(AssessmentDraft).where(AssessmentDraft.track_id == track_id).with_for_update().execution_options(populate_existing=True))
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
    draft = await db.scalar(select(AssessmentDraft).where(AssessmentDraft.track_id == track_id).with_for_update().execution_options(populate_existing=True))
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


async def publish_lesson_version(db, principal, lesson_id, expected_draft_version, expected_publication_revision, *, recording_claims=None):
    """P18E extension: exact draft + pointer CAS; called inside release transaction."""
    permission(principal, "learning.publish")
    from .recording_publication import prepare_recording_assets, validate_recording_assets, record_recording_assets
    if recording_claims is None:
        recording_claims = await prepare_recording_assets(db, principal, [lesson_id], {lesson_id: expected_draft_version})
    value = await lesson(db, principal, lesson_id, lock=True)
    check_version(value.publication_revision, expected_publication_revision)
    draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == lesson_id).with_for_update().execution_options(populate_existing=True))
    if draft is None or draft.status != "reviewed":
        raise ApiError(409, "review_required", "Сначала проверьте и согласуйте редакцию урока")
    check_version(draft.version, expected_draft_version)
    await validate_recording_assets(db, principal, lesson_id, draft.version, draft.blocks, recording_claims)
    validation = await validate_lesson(db, principal, lesson_id)
    if not validation["valid"]:
        raise ApiError(422, "lesson_invalid", "Материал не прошёл проверку", field_errors={"blocks": validation["errors"]})
    number = (await db.scalar(select(func.max(LessonVersion.number)).where(LessonVersion.lesson_id == value.id)) or 0) + 1
    previous = await db.get(LessonVersion, value.current_version_id) if value.current_version_id else None
    version = LessonVersion(lesson_id=value.id, number=number, title=draft.title, minutes=draft.minutes, source=draft.source, presentation_mode=previous.presentation_mode if previous else "feed")
    db.add(version)
    await db.flush()
    for position, block in enumerate(draft.blocks):
        db.add(LessonBlock(lesson_version_id=version.id, position=position, content=deepcopy(block)))
    await db.flush()
    await record_recording_assets(db, principal, lesson_id, draft.version, version.id, recording_claims)
    value.current_version_id = version.id
    value.publication_revision += 1
    draft.status = "published"
    await db.flush()
    return version.id


async def publish_release(db, principal, track_id, body):
    permission(principal, "learning.publish")
    from .recording_publication import prepare_recording_assets
    recording_claims = await prepare_recording_assets(db, principal, body.lesson_ids, body.lesson_draft_versions)
    parent = await track(db, principal, track_id, lock=True)
    check_version(parent.version, body.expected_version)
    if parent.archived or len(body.lesson_ids) != len(set(body.lesson_ids)):
        raise ApiError(422, "release_invalid", "Проверьте состав трека")
    versions = []
    # Lock stable lessons in stable order, avoiding races/deadlocks across release commands.
    locked = {key: await lesson(db, principal, key, lock=True) for key in sorted(body.lesson_ids)}
    # The release follows the course order, never the order of the request.
    ordered = sorted(body.lesson_ids, key=lambda lesson_id: (locked[lesson_id].position, locked[lesson_id].key))
    for lesson_id in ordered:
        value = locked[lesson_id]
        if value.track_id != parent.id or value.archived:
            raise ApiError(422, "release_lesson_invalid", "Урок не входит в активные материалы этого трека")
        draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == value.id).with_for_update().execution_options(populate_existing=True))
        check_version(value.publication_revision, body.lesson_publication_revisions.get(value.id, -1))
        check_version(draft.version if draft else 0, body.lesson_draft_versions.get(value.id, -1))
        if draft and draft.status != "published":
            version_id = await publish_lesson_version(db, principal, value.id, draft.version, value.publication_revision, recording_claims=recording_claims)
        elif value.current_version_id:
            version_id = value.current_version_id
        else:
            raise ApiError(409, "review_required", "Урок ещё не согласован")
        versions.append(str(version_id))
    current = await db.get(LearningRelease, parent.current_release_id) if parent.current_release_id else None
    assessment_id = current.assessment_version_id if current else None
    assessment = await db.scalar(select(AssessmentDraft).where(AssessmentDraft.track_id == parent.id).with_for_update().execution_options(populate_existing=True))
    if assessment and assessment.status != "published":
        check_version(assessment.version, body.assessment_draft_version)
        if assessment.status != "reviewed":
            raise ApiError(409, "assessment_review_required", "Сначала согласуйте тест")
        errors = question_errors(assessment.questions)
        if errors:
            raise ApiError(422, "assessment_invalid", "Проверьте вопросы", field_errors={"questions":errors})
        previous_assessment = await db.get(AssessmentVersion, assessment_id) if assessment_id else None
        version = AssessmentVersion(foundation_id=principal.foundation_id, title=assessment.title, intro=assessment.intro, allow_repeat=previous_assessment.allow_repeat if previous_assessment else parent.key != "introduction")
        db.add(version)
        await db.flush()
        assessment_id = version.id
        for position, question in enumerate(assessment.questions):
            db.add(AssessmentQuestion(assessment_version_id=version.id, position=position, prompt=question["q"], options=deepcopy(question["o"]), correct_option=question["a"], explanation=question["e"]))
        assessment.status = "published"
    number = (await db.scalar(select(func.max(LearningRelease.number)).where(LearningRelease.track_id == parent.id)) or 0) + 1
    stages = [dict(title=title, lesson_version_ids=items) for title, items in stage_groups(zip(versions, [locked[lesson_id].stage_title for lesson_id in ordered]))]
    release = LearningRelease(track_id=parent.id, foundation_id=principal.foundation_id, number=number, title=parent.title, intro=body.intro, lesson_version_ids=versions, stages=stages, assessment_version_id=assessment_id, reacknowledgement_required=body.reacknowledgement_required, changed_required_items=body.changed_required_items)
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
        draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == stable.id).with_for_update().execution_options(populate_existing=True))
        if draft:
            draft.status, draft.reviewed_by = "draft", None
            draft.version += 1
    assessment = await db.scalar(select(AssessmentDraft).where(AssessmentDraft.track_id == parent.id).with_for_update().execution_options(populate_existing=True))
    if assessment:
        assessment.status, assessment.reviewed_by = "draft", None
        assessment.version += 1
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
    if body.application_id:
        if body.user_id or body.registration_id:
            raise ApiError(422, "assignment_owner_required", "Выберите одного получателя")
        from app.modules.applications.service import learning_recipient_owner
        owner_data = await learning_recipient_owner(db, principal, body.application_id)
        body = body.model_copy(update={"user_id": owner_data["user_id"], "registration_id": owner_data["registration_id"]})
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


async def preview_quiz(db, principal, lesson_id, block_position, question_index, selected_option):
    permission(principal, "learning.read")
    value = await lesson(db, principal, lesson_id)
    draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == value.id))
    if draft:
        blocks = draft.blocks
    else:
        blocks = [block.content for block in (await db.scalars(select(LessonBlock).where(LessonBlock.lesson_version_id == value.current_version_id).order_by(LessonBlock.position))).all()]
    if not 0 <= block_position < len(blocks) or blocks[block_position].get("type") != "quiz":
        raise ApiError(404, "question_not_found", "Вопрос не найден")
    items = blocks[block_position].get("items", [])
    if question_index >= len(items):
        raise ApiError(404, "question_not_found", "Вопрос не найден")
    question = items[question_index]
    if selected_option >= len(question.get("o", [])):
        raise ApiError(422, "invalid_option", "Выберите вариант ответа")
    return dict(correct=selected_option == question.get("a"), explanation=question.get("e", ""))


async def archive_lesson(db, principal, lesson_id, expected_revision):
    permission(principal, "learning.publish")
    current = await lesson(db, principal, lesson_id)
    parent = await track(db, principal, current.track_id, lock=True)
    current = await lesson(db, principal, lesson_id, lock=True)
    check_version(current.publication_revision, expected_revision)
    current.archived = True
    current.publication_revision += 1
    parent.version += 1
    return await author_lesson(db, principal, current.id)


async def authorize_new_assets(db, principal, stable, draft, blocks):
    from app.modules.assets.service import require_asset
    previously_bound = {str(block["asset_id"]) for block in (draft.blocks if draft else []) if block.get("asset_id")}
    if stable.current_version_id:
        published = (await db.scalars(select(LessonBlock).where(LessonBlock.lesson_version_id == stable.current_version_id))).all()
        previously_bound.update(str(block.content["asset_id"]) for block in published if block.content.get("asset_id"))
    for block in blocks:
        if block.get("type") in ASSET_BLOCKS and block.get("asset_id"):
            try:
                asset_id = UUID(str(block["asset_id"]))
            except ValueError:
                raise ApiError(422, "invalid_asset", "Файл не найден")
            if str(asset_id) not in previously_bound:
                await require_asset(db, principal, asset_id)


async def preview_asset(db, principal, lesson_id, asset_id):
    from app.core.models import MediaAsset
    from app.modules.assets.service import asset_content
    permission(principal, "learning.read")
    stable = await lesson(db, principal, lesson_id)
    draft = await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id == stable.id))
    if draft:
        blocks = draft.blocks
    else:
        blocks = [block.content for block in (await db.scalars(select(LessonBlock).where(LessonBlock.lesson_version_id == stable.current_version_id))).all()]
    if not any(str(block.get("asset_id")) == str(asset_id) and block.get("type") in ASSET_BLOCKS for block in blocks):
        raise ApiError(404, "asset_not_found", "Файл не найден")
    asset = await db.scalar(select(MediaAsset).where(MediaAsset.id == asset_id, MediaAsset.foundation_id == principal.foundation_id, MediaAsset.state == "ready"))
    if asset is None:
        raise ApiError(404, "asset_not_found", "Файл не найден")
    return await asset_content(db, asset)


async def attach_recording(db,principal,lesson_id,body):
    permission(principal,'learning.write')
    from .recording_publication import prepare_recording_attachment
    claim=await prepare_recording_attachment(db,principal,lesson_id,body.expected_version,body.render_id,body.render_hash)
    value=await lesson(db,principal,lesson_id,lock=True)
    if value.archived:raise ApiError(409,'lesson_archived','Урок в архиве')
    draft=await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id==lesson_id).with_for_update().execution_options(populate_existing=True))
    check_version(draft.version if draft else 0,body.expected_version)
    if draft is None:
        await begin_edit(db,principal,lesson_id)
        draft=await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id==lesson_id).with_for_update())
    if any(block.get('type')=='video' and str(block.get('asset_id'))==str(claim.asset_id) for block in draft.blocks):
        return await author_lesson(db,principal,lesson_id)
    if len(draft.blocks)>=100:raise ApiError(422,'lesson_block_limit','В уроке уже 100 блоков. Освободите место для записи')
    draft.blocks=[*deepcopy(draft.blocks),{'type':'video','title':'Запись урока','asset_id':str(claim.asset_id)}]
    draft.version+=1
    draft.status,draft.reviewed_by='draft',None
    await db.flush()
    return await author_lesson(db,principal,lesson_id)


async def update_track(db, principal, track_id, body):
    permission(principal, "learning.write")
    value = await track(db, principal, track_id, lock=True)
    check_version(value.version, body.expected_version)
    if value.archived:
        raise ApiError(409, "track_archived", "Курс в архиве")
    if body.title is not None:
        if not body.title.strip():
            raise ApiError(422, "title_required", "Введите название курса", field_errors={"title": ["Введите название курса"]})
        value.title = body.title.strip()
    if body.description is not None:
        value.description = body.description.strip()
    if body.audience is not None:
        value.audience = body.audience
    if body.required is not None:
        value.required = body.required
    value.version += 1
    await db.flush()
    return await track_view(db, principal, value.id)


async def save_structure(db, principal, track_id, body):
    """Order and stages of the active lessons; published releases are untouched until the next publication."""
    permission(principal, "learning.write")
    parent = await track(db, principal, track_id, lock=True)
    check_version(parent.version, body.expected_version)
    if parent.archived:
        raise ApiError(409, "track_archived", "Курс в архиве")
    lessons = {item.id: item for item in (await db.scalars(select(Lesson).where(Lesson.track_id == parent.id).with_for_update().execution_options(populate_existing=True))).all()}
    ordered = [lesson_id for stage in body.stages for lesson_id in stage.lesson_ids]
    if len(ordered) != len(set(ordered)) or set(ordered) != {key for key, item in lessons.items() if not item.archived}:
        raise ApiError(422, "structure_invalid", "Укажите каждый урок курса ровно один раз")
    titles = [(stage.title or "").strip() or None for stage in body.stages]
    if any(left == right for left, right in zip(titles, titles[1:])):
        raise ApiError(422, "structure_invalid", "У соседних ступеней должны быть разные названия")
    position = 0
    for title, stage in zip(titles, body.stages):
        for lesson_id in stage.lesson_ids:
            lessons[lesson_id].position, lessons[lesson_id].stage_title = position, title
            position += 1
    for item in sorted((item for item in lessons.values() if item.archived), key=lambda item: (item.position, item.key)):
        item.position = position
        position += 1
    parent.version += 1
    await db.flush()
    return await track_view(db, principal, parent.id)
