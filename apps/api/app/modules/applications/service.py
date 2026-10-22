from datetime import timedelta
from uuid import UUID, uuid5, NAMESPACE_URL
from sqlalchemy import select, text, func, delete, false, or_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal
from app.core.errors import ApiError
from .form import FORM, FORM_VERSION, FORM_VERSIONS, validate_answers
from .models import (Application, ApplicationDraft, ApplicationRevision, FormVersion, ConsentEvent,
    ApplicationReviewEvent, ApplicationPrivateNote, CandidateRequest, CandidateRequestResponse, now)
from .schemas import (ApplicationSelfView, CandidateView, CandidateSummaryView, DraftView, FormView, RevisionView,
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


async def current_form(db, foundation_id, *, create=False, version=FORM_VERSION):
    content=FORM_VERSIONS[version]
    form_id = uuid5(NAMESPACE_URL, f"opora:{foundation_id}:application-form:{version}")
    if create:
        await db.execute(insert(FormVersion).values(id=form_id, foundation_id=foundation_id, version=version, content=content).on_conflict_do_nothing(index_elements=["foundation_id", "version"]))
    stored = (await db.execute(select(FormVersion).where(FormVersion.foundation_id == foundation_id, FormVersion.version == version))).scalar_one_or_none()
    return stored or FormVersion(id=form_id, foundation_id=foundation_id, version=version, content=content)


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


def history_view(e):
    return ReviewEventView(id=e.id, kind=e.kind, state=e.state, public_message=e.public_message, created_at=e.created_at)


async def application_view(db, application, *, coordinator=False):
    if coordinator:
        return (await candidate_views(db, application.foundation_id, [application]))[0]
    revisions = (await db.execute(select(ApplicationRevision).where(ApplicationRevision.application_id == application.id).order_by(ApplicationRevision.number))).scalars().all()
    revision = next((r for r in revisions if r.id == application.submitted_revision_id), None)
    if revision is None:
        raise ApiError(409, "application_incomplete", "Анкета не завершена")
    history = (await db.execute(select(ApplicationReviewEvent).where(ApplicationReviewEvent.application_id == application.id).order_by(ApplicationReviewEvent.created_at, ApplicationReviewEvent.id))).scalars().all()
    from .consents import consent_events
    events = await consent_events(db,application.foundation_id,user_id=application.user_id,application_id=application.id)
    consents = {event.purpose: event.granted for event in events}
    return ApplicationSelfView(id=application.id, version=application.version, submission_state=application.submission_state,
        review_state=application.review_state, submitted_at=application.submitted_at, revision=revision_view(revision),
        history=[history_view(e) for e in history], consents=consents)


async def candidate_views(db, foundation_id, applications, facts=None):
    """Coordinator DTOs for a page of candidates with a fixed number of queries, whatever the page size."""
    if not applications:
        return []
    ids = [a.id for a in applications]
    facts = facts or await candidate_facts(db, foundation_id, applications)
    revisions = {}
    for r in (await db.scalars(select(ApplicationRevision).where(ApplicationRevision.application_id.in_(ids)).order_by(ApplicationRevision.application_id, ApplicationRevision.number))).all():
        revisions.setdefault(r.application_id, []).append(r)
    users = {a.user_id for a in applications if a.user_id}
    owners = ConsentEvent.application_id.in_(ids) | (ConsentEvent.subject_user_id.in_(users) if users else false())
    consents = (await db.scalars(select(ConsentEvent).where(owners).order_by(ConsentEvent.created_at, ConsentEvent.id))).all()
    views = []
    for a in applications:
        own = revisions.get(a.id, [])
        revision = next((r for r in own if r.id == a.submitted_revision_id), None)
        if revision is None:
            raise ApiError(409, "application_incomplete", "Анкета не завершена")
        fact = facts[a.id]
        views.append(CandidateView(id=a.id, version=a.version, submission_state=a.submission_state, review_state=a.review_state,
            submitted_at=a.submitted_at, revision=revision_view(revision), history=[history_view(e) for e in fact["history"]],
            consents={e.purpose: e.granted for e in consents if e.application_id == a.id or (a.user_id and e.subject_user_id == a.user_id)},
            assigned_coordinator_id=a.assigned_coordinator_id, progress=fact["progress"], revisions=[revision_view(r) for r in own],
            stage=fact["stage"], stage_since=fact["since"]))
    return views


def candidate_stage(application, progress, attended=False):
    """One funnel position from the review state, the introduction course and the latest interview booking."""
    if application.submission_state != "submitted" or application.review_state in ("paused", "closed"):
        return "closed"
    if application.review_state == "new":
        return "new"
    if attended:
        return "done"
    interview = progress["interview"]["status"]
    if interview == "completed" or application.review_state == "discussed":
        return "ready"
    if interview in ("booked", "missed", "cancelled") or progress["introduction"]["status"] in ("completed", "unavailable"):
        return "interview"
    return "intro"


def stage_since(application, stage, progress, history):
    accepted = next((e.created_at for e in history if e.state != "new"), None)
    if stage == "new":
        return application.submitted_at
    if stage == "intro":
        return accepted or application.submitted_at
    if stage == "interview":
        return progress["introduction"].get("completed_at") or accepted
    if stage == "ready":
        if progress["interview"]["status"] == "completed":
            return progress["interview"]["starts_at"]
        return next((e.created_at for e in reversed(history) if e.state == "discussed"), None) or accepted
    return history[-1].created_at if history else application.submitted_at


async def candidate_facts(db, foundation_id, applications):
    """Progress, history and funnel stage for many candidates in a fixed number of queries."""
    ids = [a.id for a in applications]
    progress = await candidate_progress_many(db, foundation_id, applications)
    attended = await attended_users(db, foundation_id, {a.user_id for a in applications if a.user_id})
    history = {}
    if ids:
        for e in (await db.scalars(select(ApplicationReviewEvent).where(ApplicationReviewEvent.application_id.in_(ids)).order_by(ApplicationReviewEvent.created_at, ApplicationReviewEvent.id))).all():
            history.setdefault(e.application_id, []).append(e)
    facts = {}
    for a in applications:
        own, value = history.get(a.id, []), progress[a.id]
        stage = candidate_stage(a, value, a.user_id in attended)
        facts[a.id] = dict(progress=value, history=own, stage=stage, since=stage_since(a, stage, value, own))
    return facts


async def attended_users(db, foundation_id, user_ids):
    """Users with at least one attended event: their first outing is behind them."""
    if not user_ids:
        return set()
    try:
        from app.modules.activities.assignment_models import Assignment, Attendance
    except ModuleNotFoundError as error:
        if not (error.name or "").startswith("app.modules.activities"):
            raise
        return set()
    return set((await db.scalars(select(Assignment.user_id).join(Attendance, Attendance.assignment_id == Assignment.id).where(
        Assignment.foundation_id == foundation_id, Assignment.user_id.in_(user_ids), Attendance.outcome == "attended").distinct())).all())


async def verified_questionnaire_email(db, principal):
    from app.core.models import ContactChannel
    email = await db.scalar(select(ContactChannel.normalized_value).where(ContactChannel.user_id == principal.user_id, ContactChannel.type == 'email', ContactChannel.verified_at.is_not(None)).order_by(ContactChannel.created_at).limit(1)) if principal.user_id else None
    if not email:
        raise ApiError(403, 'verified_account_required', 'Подтвердите почту перед заполнением анкеты')
    return email


async def get_draft(db, principal):
    draft = (await db.execute(select(ApplicationDraft).where(ApplicationDraft.foundation_id == principal.foundation_id, owner_condition(ApplicationDraft, principal)))).scalar_one_or_none()
    if draft:
        form=await db.get(FormVersion,draft.form_version_id)
    else:
        application=await own_application(db,principal,required=False)
        revision=await db.get(ApplicationRevision,application.submitted_revision_id) if application else None
        form=await db.get(FormVersion,revision.form_version_id) if revision else await current_form(db,principal.foundation_id)
    return DraftView(id=draft.id if draft else None, version=draft.version if draft else 0, step=draft.step if draft else 0,
        answers={**(draft.answers if draft else {}), **({"email": await verified_questionnaire_email(db, principal)} if principal.user_id else {})}, form=FormView(id=form.id, version=form.version, content=form.content))


async def save_draft(db, principal, command):
    email = await verified_questionnaire_email(db, principal)
    await owner_lock(db, principal)
    draft = (await db.execute(select(ApplicationDraft).where(ApplicationDraft.foundation_id == principal.foundation_id, owner_condition(ApplicationDraft, principal)).with_for_update())).scalar_one_or_none()
    check_version(draft.version if draft else 0, command.expected_version)
    # Drafts permit incomplete/malformed text to survive a reload. The submit schema validates strictly.
    if len(str(command.answers)) > 50000 or set(command.answers) - {f['id'] for step in FORM['steps'] for f in step['fields']}:
        raise ApiError(422, "validation_error", "Не удалось сохранить поля анкеты")
    if draft is None:
        prior=await get_draft(db,principal)
        form=await current_form(db,principal.foundation_id,create=True,version=prior.form.version)
    else:form=await db.get(FormVersion,draft.form_version_id)
    if draft is None:
        draft = ApplicationDraft(foundation_id=principal.foundation_id, user_id=principal.user_id,
            registration_id=None if principal.user_id else principal.registration_id, form_version_id=form.id, version=0)
        db.add(draft)
    draft.answers = {**command.answers, "email": email}
    draft.step = command.step
    draft.version += 1
    draft.updated_at = now()
    await db.flush()
    return await get_draft(db, principal)


async def submit(db, principal, command, *, revision=False):
    email = await verified_questionnaire_email(db, principal)
    await owner_lock(db, principal)
    application = await own_application(db, principal, lock=True, required=False)
    if revision and not application:
        raise ApiError(404, "application_not_found", "Анкета пока не отправлена")
    if application and not revision:
        raise ApiError(409, "already_submitted", "Анкета уже отправлена", current_version=application.version)
    check_version(application.version if application else 0, command.expected_version)
    if application and application.submission_state == "withdrawn":
        raise ApiError(409, "application_withdrawn", "Анкета отозвана. Свяжитесь с координатором")
    draft=await db.scalar(select(ApplicationDraft).where(ApplicationDraft.foundation_id==principal.foundation_id,owner_condition(ApplicationDraft,principal)))
    if draft:form=await db.get(FormVersion,draft.form_version_id)
    elif application:
        prior_revision=await db.get(ApplicationRevision,application.submitted_revision_id)
        form=await db.get(FormVersion,prior_revision.form_version_id)
    else:form=await current_form(db,principal.foundation_id,create=True)
    answers = validate_answers({**command.answers, "email": email}, complete=True,form=form.content)
    answers.pop("consentPD", None)
    answers.pop("consentNews", None)
    if not command.consents.personal_data:
        raise ApiError(422, "consent_required", "Для отправки анкеты нужно согласие на обработку персональных данных", field_errors={"consentPD": "Подтвердите согласие"})
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


async def initialize_registration_user(db, registration_id, user_id):
    """Initialize only a newly-created verified identity before its owned claim.

    P01 invokes this optional hook exclusively for the User it just created.
    Neither contact text nor another application's answers can identify a source.
    """
    from app.core.models import RegistrationSession, User
    from app.modules.profile.models import VolunteerProfile, ProfileRevision
    registration = await db.get(RegistrationSession, registration_id)
    user = await db.scalar(select(User).where(User.id == user_id).with_for_update())
    if not registration or not user or registration.foundation_id != user.foundation_id:
        raise ApiError(409, "registration_scope_conflict", "Не удалось перенести анкету в аккаунт")
    if registration.claimed_user_id != user_id or not registration.verified_email:
        raise ApiError(409, "registration_not_verified", "Сначала подтвердите свою сессию регистрации")
    # Even an explicit new-user callback must not replace an already chosen name
    # or a profile's manual history (including a deliberately chosen placeholder).
    if user.display_name not in ("Волонтёр", ""):
        return
    if await db.scalar(select(VolunteerProfile.user_id).where(VolunteerProfile.user_id == user_id)) or await db.scalar(select(ProfileRevision.id).where(ProfileRevision.user_id == user_id).limit(1)):
        return
    revision = await db.scalar(select(ApplicationRevision).join(Application, (Application.submitted_revision_id == ApplicationRevision.id) & (ApplicationRevision.application_id == Application.id)).where(Application.foundation_id == user.foundation_id, Application.registration_id == registration_id, Application.submission_state == "submitted"))
    if revision is None:
        return
    parts = [revision.answers.get(key) for key in ("firstName", "lastName")]
    if any(not isinstance(value, str) or not value.strip() for value in parts):
        return
    name = " ".join(" ".join(value.split()) for value in parts)
    user.display_name = name[:User.__table__.c.display_name.type.length].rstrip()
    await db.flush()


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


async def candidate_progress(db, application):
    return (await candidate_progress_many(db, application.foundation_id, [application]))[application.id]


async def candidate_progress_many(db, foundation_id, applications):
    """Compose independent read-only projections; unavailable is never zero progress.

    Batched reads of the introduction course (learning) and the latest interview booking (interviews):
    the same rules as their single-candidate projections, a fixed number of queries for any page.
    """
    result = {a.id: dict(introduction=dict(status="unavailable", completed_lessons=0, total_lessons=0),
        interview=dict(status="unavailable", starts_at=None, booking_id=None)) for a in applications}
    if not applications:
        return result
    try:
        from app.modules.learning.models import LearningTrack, LearningRelease, LearningAssignment, LessonProgress
    except ModuleNotFoundError as error:
        if not (error.name or "").startswith("app.modules.learning"):
            raise
    else:
        track = await db.scalar(select(LearningTrack).where(LearningTrack.foundation_id == foundation_id, LearningTrack.key == "introduction"))
        release = await db.get(LearningRelease, track.current_release_id) if track and track.current_release_id else None
        if release is not None:
            users = {a.user_id for a in applications if a.user_id}
            registrations = {a.registration_id for a in applications if not a.user_id and a.registration_id}
            scopes = ([LearningAssignment.user_id.in_(users)] if users else []) + ([LearningAssignment.registration_id.in_(registrations)] if registrations else [])
            items = (await db.scalars(select(LearningAssignment).where(LearningAssignment.foundation_id == foundation_id,
                LearningAssignment.release_id == release.id, or_(*scopes)))).all() if scopes else []
            done = {}
            if items:
                for assignment_id, lesson_id in (await db.execute(select(LessonProgress.assignment_id, LessonProgress.lesson_version_id).where(LessonProgress.assignment_id.in_([i.id for i in items])))).all():
                    done.setdefault(assignment_id, set()).add(str(lesson_id))
            by_user = {i.user_id: i for i in items if i.user_id}
            by_registration = {i.registration_id: i for i in items if i.registration_id}
            lessons = set(release.lesson_version_ids)
            for a in applications:
                item = by_user.get(a.user_id) if a.user_id else by_registration.get(a.registration_id)
                count = len(done.get(item.id, set()) & lessons) if item else 0
                completed = bool(item and item.completed_at)
                result[a.id]["introduction"] = dict(status="completed" if completed else "in_progress" if count else "not_started",
                    completed_lessons=count, total_lessons=len(release.lesson_version_ids), completed_at=item.completed_at if completed else None)
    try:
        from app.modules.interviews.models import InterviewBooking
    except ModuleNotFoundError as error:
        if not (error.name or "").startswith("app.modules.interviews"):
            raise
    else:
        bookings = {}
        for b in (await db.scalars(select(InterviewBooking).where(InterviewBooking.foundation_id == foundation_id,
                InterviewBooking.application_id.in_([a.id for a in applications])).order_by(InterviewBooking.created_at.desc(), InterviewBooking.id.desc()))).all():
            bookings.setdefault(b.application_id, []).append(b)
        for a in applications:
            rows = bookings.get(a.id, [])
            row = next((b for b in rows if b.status == "booked"), rows[0] if rows else None)
            result[a.id]["interview"] = dict(status=row.status if row else "none", starts_at=row.starts_at if row else None, booking_id=row.id if row else None)
    return result


async def candidate_summary(db, principal):
    applications = (await db.scalars(select(Application).where(Application.foundation_id == principal.foundation_id,
        Application.submitted_revision_id.is_not(None)))).all()
    counts = dict.fromkeys(("new", "intro", "interview", "ready", "done", "closed"), 0)
    for fact in (await candidate_facts(db, principal.foundation_id, applications)).values():
        counts[fact["stage"]] += 1
    return CandidateSummaryView(**counts)


def stage_order(stage, view):
    """Who needs the coordinator first: the longest waiting; booked interviews by date after those without one."""
    if stage == "interview":
        booked = view.progress.interview.status == "booked"
        return (booked, view.progress.interview.starts_at if booked else view.stage_since or view.submitted_at)
    since = view.stage_since or view.submitted_at
    return (since.timestamp() * (-1 if stage in ("done", "closed") else 1),)


REMINDER_GAP = timedelta(hours=20)


async def remind(db, principal, application_id, command):
    """One in-app reminder about the introduction course, at most once a day."""
    from app.core.clock import utcnow
    from app.modules.messaging.consumers import enqueue_notice
    application = await coordinator_application(db, principal, application_id, lock=True)
    check_version(application.version, command.expected_version)
    fact = (await candidate_facts(db, principal.foundation_id, [application]))[application.id]
    if fact["stage"] != "intro":
        raise ApiError(409, "reminder_not_needed", "Напоминать нужно только тем, кто проходит знакомство")
    if application.user_id is None:
        raise ApiError(409, "candidate_without_account", "Кандидат ещё не подтвердил почту, напомнить не получится")
    last = max((e.created_at for e in fact["history"] if e.kind == "reminded"), default=None)
    if last and utcnow() - last < REMINDER_GAP:
        raise ApiError(409, "already_reminded", "Напоминание уже отправлено сегодня")
    enqueue_notice(db, application.foundation_id, application.user_id, "Знакомство с фондом",
        "Координатор напоминает: пройдите знакомство с фондом, это несколько коротких уроков.\nОткрыть: /onboarding")
    application.version += 1
    db.add(ApplicationReviewEvent(application_id=application.id, kind="reminded", state=application.review_state,
        public_message="", author_id=principal.actor_id))
    await db.flush()
    return await application_view(db, application, coordinator=True)


async def learning_recipient_options(db, principal, search=""):
    """Internal boundary for a permission-protected learner recipient picker."""
    if not principal.has_permission("candidates.read"):
        raise ApiError(403, "permission_denied", "Недостаточно прав для выбора кандидата")
    query = select(Application, ApplicationRevision).join(ApplicationRevision,
        Application.submitted_revision_id == ApplicationRevision.id).where(
        Application.foundation_id == principal.foundation_id, Application.submission_state == "submitted")
    if search.strip():
        from sqlalchemy import or_
        needle = "%" + search.strip()[:200].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        query = query.where(or_(ApplicationRevision.answers["firstName"].astext.ilike(needle, escape="\\"),
            ApplicationRevision.answers["lastName"].astext.ilike(needle, escape="\\")))
    rows = (await db.execute(query.order_by(Application.submitted_at.desc(), Application.id).limit(50))).all()
    return [{"application_id": application.id, "label": " ".join(str(revision.answers.get(key, "")) for key in ("firstName", "lastName")).strip()}
        for application, revision in rows]


async def learning_recipient_owner(db, principal, application_id):
    """Resolve a stable application ID internally; identity axes never go to the picker."""
    if not principal.has_permission("candidates.read"):
        raise ApiError(403, "permission_denied", "Недостаточно прав для выбора кандидата")
    application = await coordinator_application(db, principal, application_id)
    if application.submission_state != "submitted":
        raise ApiError(409, "application_withdrawn", "Анкета отозвана")
    return dict(user_id=application.user_id, registration_id=application.registration_id,
        foundation_id=application.foundation_id)
