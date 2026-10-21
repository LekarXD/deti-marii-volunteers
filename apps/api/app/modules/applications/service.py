from uuid import UUID, uuid5, NAMESPACE_URL
from sqlalchemy import select, text, func, delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal
from app.core.errors import ApiError
from .form import FORM, validate_answers
from .models import (Application, ApplicationDraft, ApplicationRevision, FormVersion, ConsentEvent,
    ApplicationReviewEvent, ApplicationPrivateNote, CandidateRequest, CandidateRequestResponse, now)
from .schemas import (ApplicationSelfView, CandidateView, DraftView, FormView, RevisionView,
    ReviewEventView, RequestView, ResponseView, NoteView)


def owner_condition(model, principal):
    if principal.user_id:
        return model.user_id == principal.user_id
    if principal.registration_id:
        return model.registration_id == principal.registration_id
    raise ApiError(401, "session_required", "Откройте новую сессию")


async def owner_lock(db, principal):
    # Serializes creation across different idempotency keys/tabs, without contact lookup.
    key = f"application:{principal.foundation_id}:{principal.user_id or principal.registration_id}"
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})


async def current_form(db, foundation_id, *, create=False):
    form_id = uuid5(NAMESPACE_URL, f"opora:{foundation_id}:application-form:4")
    if create:
        await db.execute(insert(FormVersion).values(id=form_id, foundation_id=foundation_id, version=4, content=FORM).on_conflict_do_nothing(index_elements=["foundation_id", "version"]))
    stored = (await db.execute(select(FormVersion).where(FormVersion.foundation_id == foundation_id, FormVersion.version == 4))).scalar_one_or_none()
    return stored or FormVersion(id=form_id, foundation_id=foundation_id, version=4, content=FORM)


async def own_application(db: AsyncSession, principal: Principal, lock=False, required=True):
    statement = select(Application).where(Application.foundation_id == principal.foundation_id, owner_condition(Application, principal))
    if lock:
        statement = statement.with_for_update()
    result = (await db.execute(statement)).scalar_one_or_none()
    if required and result is None:
        raise ApiError(404, "application_not_found", "Анкета пока не отправлена")
    return result


async def coordinator_application(db, principal, application_id, lock=False):
    # Permission dependency is evaluated before this scoped repository lookup.
    statement = select(Application).where(Application.foundation_id == principal.foundation_id, Application.id == application_id)
    if lock:
        statement = statement.with_for_update()
    result = (await db.execute(statement)).scalar_one_or_none()
    if not result:
        raise ApiError(404, "candidate_not_found", "Кандидат не найден")
    return result


def check_version(actual, expected):
    if actual != expected:
        raise ApiError(409, "version_conflict", "Данные изменились. Обновите страницу и повторите действие", current_version=actual)


def revision_view(revision):
    return RevisionView(id=revision.id, number=revision.number, form_version_id=revision.form_version_id,
        answers=revision.answers, created_at=revision.created_at)


async def application_view(db, application, *, coordinator=False):
    revisions = (await db.execute(select(ApplicationRevision).where(ApplicationRevision.application_id == application.id).order_by(ApplicationRevision.number))).scalars().all()
    revision = next((r for r in revisions if r.id == application.submitted_revision_id), None)
    if revision is None:
        raise ApiError(409, "application_incomplete", "Анкета не завершена")
    history = (await db.execute(select(ApplicationReviewEvent).where(ApplicationReviewEvent.application_id == application.id).order_by(ApplicationReviewEvent.created_at, ApplicationReviewEvent.id))).scalars().all()
    events = (await db.execute(select(ConsentEvent).where(ConsentEvent.application_id == application.id).order_by(ConsentEvent.created_at, ConsentEvent.id))).scalars().all()
    consents = {event.purpose: event.granted for event in events}
    values = dict(id=application.id, version=application.version, submission_state=application.submission_state,
        review_state=application.review_state, submitted_at=application.submitted_at, revision=revision_view(revision),
        history=[ReviewEventView(id=e.id, kind=e.kind, state=e.state, public_message=e.public_message, created_at=e.created_at) for e in history], consents=consents)
    if coordinator:
        return CandidateView(**values, assigned_coordinator_id=application.assigned_coordinator_id, revisions=[revision_view(r) for r in revisions])
    return ApplicationSelfView(**values)


async def get_draft(db, principal):
    draft = (await db.execute(select(ApplicationDraft).where(ApplicationDraft.foundation_id == principal.foundation_id, owner_condition(ApplicationDraft, principal)))).scalar_one_or_none()
    form = await current_form(db, principal.foundation_id)
    return DraftView(id=draft.id if draft else None, version=draft.version if draft else 0, step=draft.step if draft else 0,
        answers=draft.answers if draft else {}, form=FormView(id=form.id, version=form.version, content=form.content))


async def save_draft(db, principal, command):
    await owner_lock(db, principal)
    draft = (await db.execute(select(ApplicationDraft).where(ApplicationDraft.foundation_id == principal.foundation_id, owner_condition(ApplicationDraft, principal)).with_for_update())).scalar_one_or_none()
    check_version(draft.version if draft else 0, command.expected_version)
    # Drafts permit incomplete/malformed text to survive a reload. The submit schema validates strictly.
    if len(str(command.answers)) > 50000 or set(command.answers) - {f['id'] for step in FORM['steps'] for f in step['fields']}:
        raise ApiError(422, "validation_error", "Не удалось сохранить поля анкеты")
    form = await current_form(db, principal.foundation_id, create=True)
    if draft is None:
        draft = ApplicationDraft(foundation_id=principal.foundation_id, user_id=principal.user_id,
            registration_id=None if principal.user_id else principal.registration_id, form_version_id=form.id, version=0)
        db.add(draft)
    draft.answers = command.answers
    draft.step = command.step
    draft.version += 1
    draft.updated_at = now()
    await db.flush()
    return await get_draft(db, principal)


async def submit(db, principal, command, *, revision=False):
    await owner_lock(db, principal)
    application = await own_application(db, principal, lock=True, required=False)
    if revision and not application:
        raise ApiError(404, "application_not_found", "Анкета пока не отправлена")
    if application and not revision:
        raise ApiError(409, "already_submitted", "Анкета уже отправлена", current_version=application.version)
    check_version(application.version if application else 0, command.expected_version)
    if application and application.submission_state == "withdrawn":
        raise ApiError(409, "application_withdrawn", "Анкета отозвана. Свяжитесь с координатором")
    answers = validate_answers(command.answers, complete=True)
    answers.pop("consentPD", None)
    answers.pop("consentNews", None)
    if not command.consents.personal_data:
        raise ApiError(422, "consent_required", "Для отправки анкеты нужно согласие на обработку персональных данных", field_errors={"consentPD": "Подтвердите согласие"})
    form = await current_form(db, principal.foundation_id, create=True)
    if application is None:
        application = Application(foundation_id=principal.foundation_id, user_id=principal.user_id,
            registration_id=None if principal.user_id else principal.registration_id, version=0)
        db.add(application)
        await db.flush()
    number = (await db.execute(select(func.coalesce(func.max(ApplicationRevision.number), 0)).where(ApplicationRevision.application_id == application.id))).scalar_one() + 1
    snapshot = ApplicationRevision(application_id=application.id, form_version_id=form.id,
        number=number, answers=answers, author_id=principal.actor_id)
    db.add(snapshot)
    await db.flush()
    application.submitted_revision_id = snapshot.id
    application.version += 1
    application.submission_state = "submitted"
    for purpose, granted in (("personal_data", command.consents.personal_data), ("news", command.consents.news)):
        db.add(ConsentEvent(application_id=application.id, document="privacy" if purpose == "personal_data" else "news",
            document_version=command.consents.document_version, purpose=purpose, granted=granted, author_id=principal.actor_id))
    db.add(ApplicationReviewEvent(application_id=application.id, kind="revised" if revision else "submitted",
        state=application.review_state, public_message="Анкета обновлена" if revision else "Анкета отправлена", author_id=principal.actor_id))
    await db.execute(delete(ApplicationDraft).where(ApplicationDraft.foundation_id == principal.foundation_id, owner_condition(ApplicationDraft, principal)))
    await db.flush()
    return await application_view(db, application)


async def withdraw(db, principal, command):
    application = await own_application(db, principal, lock=True)
    check_version(application.version, command.expected_version)
    if application.submission_state != "submitted":
        raise ApiError(409, "already_withdrawn", "Анкета уже отозвана")
    application.submission_state = "withdrawn"
    application.version += 1
    db.add(ApplicationReviewEvent(application_id=application.id, kind="withdrawn", state=application.review_state,
        public_message="Анкета отозвана", author_id=principal.actor_id))
    await db.flush()
    return await application_view(db, application)


async def review(db, principal, application_id, command, *, reopen=False):
    application = await coordinator_application(db, principal, application_id, lock=True)
    check_version(application.version, command.expected_version)
    if reopen:
        if application.review_state not in ("closed", "paused"):
            raise ApiError(409, "cannot_reopen", "Повторно открыть можно закрытую или приостановленную анкету")
        application.review_state = "reviewing"
        message = "Координатор вернулся к рассмотрению анкеты"
    else:
        if application.review_state == "closed":
            raise ApiError(409, "closed_application", "Сначала повторно откройте анкету")
        application.review_state = command.state
        # Assignment only to active scoped staff, never arbitrary user IDs.
        if command.assigned_coordinator_id:
            from app.core.models import StaffMembership
            assigned = (await db.execute(select(StaffMembership).where(StaffMembership.foundation_id == principal.foundation_id,
                StaffMembership.user_id == command.assigned_coordinator_id, StaffMembership.revoked_at.is_(None)))).scalars().first()
            if not assigned or (hasattr(assigned, "active") and not assigned.active):
                raise ApiError(422, "invalid_coordinator", "Координатор не найден в команде фонда")
        application.assigned_coordinator_id = command.assigned_coordinator_id
        message = command.public_message.strip()
    application.version += 1
    db.add(ApplicationReviewEvent(application_id=application.id, kind="reopened" if reopen else "reviewed",
        state=application.review_state, public_message=message, author_id=principal.actor_id))
    await db.flush()
    return await application_view(db, application, coordinator=True)


async def request_view(db, request):
    replies = (await db.execute(select(CandidateRequestResponse).where(CandidateRequestResponse.request_id == request.id)
        .order_by(CandidateRequestResponse.created_at, CandidateRequestResponse.id))).scalars().all()
    return RequestView(id=request.id, application_id=request.application_id, kind=request.kind, text=request.text,
        state=request.state, version=request.version, created_at=request.created_at,
        responses=[ResponseView(id=r.id, text=r.text, created_at=r.created_at) for r in replies])


async def get_request(db, principal, request_id, *, coordinator=False, lock=False):
    query = select(CandidateRequest).join(Application, CandidateRequest.application_id == Application.id).where(
        Application.foundation_id == principal.foundation_id, CandidateRequest.id == request_id)
    if not coordinator:
        query = query.where(owner_condition(Application, principal))
    if lock:
        query = query.with_for_update(of=CandidateRequest)
    result = (await db.execute(query)).scalar_one_or_none()
    if result is None:
        raise ApiError(404, "request_not_found", "Обращение не найдено")
    return result


async def create_request(db, principal, command):
    application = await own_application(db, principal)
    if not command.text.strip():
        raise ApiError(422, "validation_error", "Напишите обращение", field_errors={"text": "Обязательное поле"})
    request = CandidateRequest(application_id=application.id, kind=command.kind, text=command.text.strip())
    db.add(request)
    await db.flush()
    return await request_view(db, request)


async def respond_request(db, principal, request_id, command, *, resolve=False):
    request = await get_request(db, principal, request_id, coordinator=True, lock=True)
    check_version(request.version, command.expected_version)
    if resolve:
        request.state = "resolved"
    else:
        if not command.text.strip():
            raise ApiError(422, "validation_error", "Напишите ответ", field_errors={"text": "Обязательное поле"})
        db.add(CandidateRequestResponse(request_id=request.id, text=command.text.strip(), author_id=principal.actor_id))
        request.state = "answered"
    request.version += 1
    await db.flush()
    return await request_view(db, request)


async def claim_registration(db, registration_id, user_id):
    """Called only inside P01's successful contact verification transaction.

    A verified user keeps stable application UUID/history. An existing application
    is never silently replaced by a new registration's answers.
    """
    from app.core.models import RegistrationSession, User
    registration = await db.get(RegistrationSession, registration_id)
    user = await db.get(User, user_id)
    if not registration or not user or registration.foundation_id != user.foundation_id:
        raise ApiError(409, "registration_scope_conflict", "Не удалось перенести анкету в аккаунт")
    for owner in sorted((str(registration_id), str(user_id))):
        key = f"application:{registration.foundation_id}:{owner}"
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"), {"key": key})
    for model in (Application, ApplicationDraft):
        source = (await db.execute(select(model).where(model.foundation_id == registration.foundation_id,
            model.registration_id == registration_id).with_for_update())).scalar_one_or_none()
        if not source:
            continue
        target = (await db.execute(select(model).where(model.foundation_id == registration.foundation_id,
            model.user_id == user_id).with_for_update())).scalar_one_or_none()
        if target:
            raise ApiError(409, "registration_application_conflict", "В аккаунте уже есть анкета. Новый черновик сохранён; обратитесь к координатору")
        source.user_id = user_id
        source.registration_id = None
    await db.flush()
