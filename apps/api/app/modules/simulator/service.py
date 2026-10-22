from datetime import datetime
from uuid import UUID, uuid5
from sqlalchemy import func, or_, select, update
from app.core.auth import resolve_principal
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.idempotency import payload_hash
from app.core.models import Session, User
from app.integrations.ai.models import AIRun, AISettings
from app.integrations.ai.provider import ProviderConfig
from app.integrations.ai.service import enqueue_ai_run
from .models import EvaluationAppeal, RubricVersion, SimulationEvaluation, SimulationSession, SimulationSupportRequest, SimulationTurn, SimulatorScenario, SimulatorScenarioReview, SimulatorScenarioVersion, SimulatorTestCaseRun, SimulatorTestRun
from .schemas import SimulatorAssessmentOutput, SimulatorEvaluationView, SimulatorReviewQueueItem, SimulatorScenarioDraft, SimulatorScenarioPublicView, SimulatorScenarioStaffView, SimulatorSessionView, SimulatorTestRunView, SimulatorTurnView
from . import jobs  # register source-controlled gateway tasks for API and worker


def check_version(entity, expected):
    if entity.version != expected:
        raise ApiError(409, 'version_conflict', 'Данные изменились. Обновите страницу.', current_version=entity.version)


def owner_filter(principal):
    if principal.user_id is not None:
        return SimulationSession.user_id == principal.user_id
    if principal.registration_id is not None:
        return SimulationSession.registration_id == principal.registration_id
    raise ApiError(403, 'owner_required', 'Нужна личная сессия.')


async def find_scenario(db, principal, id, lock=False):
    query = select(SimulatorScenario).where(SimulatorScenario.id == id, SimulatorScenario.foundation_id == principal.foundation_id)
    value = await db.scalar(query.with_for_update() if lock else query)
    if value is None:
        raise ApiError(404, 'scenario_not_found', 'Сценарий не найден.')
    return value


async def find_attempt(db, principal, id, lock=False, reviewer=False):
    query = select(SimulationSession).where(SimulationSession.id == id, SimulationSession.foundation_id == principal.foundation_id)
    if not reviewer:
        query = query.where(owner_filter(principal))
    elif not principal.has_permission('simulator.review'):
        raise ApiError(403, 'permission_denied', 'Недостаточно прав для просмотра попытки.')
    value = await db.scalar(query.with_for_update() if lock else query)
    if value is None:
        raise ApiError(404, 'simulation_not_found', 'Попытка не найдена.')
    return value


async def provider_state(db, foundation_id):
    config = ProviderConfig()
    policy = await db.get(AISettings, foundation_id)
    return 'ready' if config.configured() and (policy.enabled if policy else config.enabled) else 'unavailable'


def ensure_draft_ready(content):
    draft = SimulatorScenarioDraft.model_validate(content)
    if not all([draft.character_name.strip(), draft.character_profile.strip(), draft.situation.strip(), draft.first_turn.strip()]) or not draft.criteria or len(draft.evaluation_cases) < 2:
        raise ApiError(422, 'scenario_incomplete', 'Заполните персонажа, ситуацию, первую реплику, критерии и не менее двух эталонных примеров.')
    keys = {criterion.key for criterion in draft.criteria}
    if any(set(case.expected_scores) != keys for case in draft.evaluation_cases):
        raise ApiError(422, 'dataset_incomplete', 'У каждого примера должны быть эталонные оценки всех критериев.')
    return draft


async def staff_view(db, entity, principal):
    reviews = (await db.scalars(select(SimulatorScenarioReview).where(SimulatorScenarioReview.scenario_id == entity.id).order_by(SimulatorScenarioReview.created_at.desc()).limit(50))).all()
    tests = (await db.scalars(select(SimulatorTestRun).where(SimulatorTestRun.scenario_id == entity.id).order_by(SimulatorTestRun.created_at.desc()).limit(50))).all()
    actions = []
    if principal.has_permission('simulator.manage'):
        actions += ['update', 'test', 'publish', 'withdraw' if entity.publication_id else 'archive']
    if principal.has_permission('simulator.review'):
        actions.append('review')
    # The editor shows which draft revision volunteers see; publishing bumps the draft revision by one.
    publication = await db.get(SimulatorScenarioVersion, entity.publication_id) if entity.publication_id else None
    published_review = await db.get(SimulatorScenarioReview, publication.review_id) if publication else None
    owner = func.coalesce(SimulationSession.user_id, SimulationSession.registration_id)
    finished = await db.scalar(select(func.count(func.distinct(owner))).select_from(SimulationSession).join(SimulatorScenarioVersion, SimulatorScenarioVersion.id == SimulationSession.scenario_version_id)
        .where(SimulatorScenarioVersion.scenario_id == entity.id, SimulationSession.state == 'finished'))
    return SimulatorScenarioStaffView(id=entity.id, version=entity.version, draft=entity.draft, publication_id=entity.publication_id,
        archived_at=entity.archived_at, reviews=[{'id': str(row.id), 'draft_version': row.draft_version, 'decision': row.decision, 'reason': row.reason, 'at': row.created_at.isoformat()} for row in reviews],
        test_runs=[{'id': str(row.id), 'draft_version': row.draft_version, 'state': row.state, 'at': row.created_at.isoformat()} for row in tests], allowed_actions=actions,
        published_version=publication.version if publication else None, published_draft_version=published_review.draft_version if published_review else None, finished_count=finished or 0)


async def queue_item(db, row, attempt, title, evaluation=None):
    """A reviewer queue row: who asked, when, and whether the AI scored a critical criterion at zero."""
    user = await db.get(User, attempt.user_id) if attempt.user_id else None
    critical = False
    if evaluation is not None and evaluation.result:
        rubric = await db.get(RubricVersion, evaluation.rubric_version_id)
        flagged = {criterion['key'] for criterion in rubric.criteria if criterion.get('critical')} if rubric else set()
        critical = any(item['criterion_key'] in flagged and item['score'] == 0 for item in evaluation.result.get('criteria', []))
    return SimulatorReviewQueueItem(id=row.id, version=row.version, state=row.state, text=row.text, response=row.response, title=title, session_id=attempt.id,
        created_at=row.created_at, author_name=user.display_name if user else None, critical=critical)


async def public_view(db, version):
    content = version.content
    return SimulatorScenarioPublicView(id=version.scenario_id, publication_id=version.id, version=version.version, title=content['title'],
        character_name=content['character_name'], character_profile=content['character_profile'], situation=content['situation'], warning=content.get('warning', ''),
        methods=content.get('methods', []), criteria=content['criteria'], allowed_actions=['start'] if version.withdrawn_at is None else [], provider_state=await provider_state(db, version.foundation_id))


async def create_scenario(db, principal, body):
    value = SimulatorScenario(foundation_id=principal.foundation_id, title=body.title, draft=body.model_dump(mode='json'), updated_by=principal.actor_id)
    db.add(value)
    await db.flush()
    return await staff_view(db, value, principal)


async def update_scenario(db, principal, id, body):
    value = await find_scenario(db, principal, id, True)
    check_version(value, body.expected_version)
    value.title = body.title
    value.draft = body.model_dump(mode='json', exclude={'expected_version'})
    value.version += 1
    value.updated_at = utcnow()
    value.updated_by = principal.actor_id
    return await staff_view(db, value, principal)


async def review_scenario(db, principal, id, body):
    value = await find_scenario(db, principal, id, True)
    check_version(value, body.expected_version)
    if body.decision == 'approved':
        ensure_draft_ready(value.draft)
    row = SimulatorScenarioReview(scenario_id=id, draft_version=value.version, content_hash=payload_hash(value.draft), decision=body.decision, reason=body.reason, reviewer_id=principal.actor_id)
    db.add(row)
    await db.flush()
    return await staff_view(db, value, principal)


async def test_view(db, row):
    cases = (await db.scalars(select(SimulatorTestCaseRun).where(SimulatorTestCaseRun.test_run_id == row.id).order_by(SimulatorTestCaseRun.case_key))).all()
    return SimulatorTestRunView(id=row.id, state=row.state, draft_version=row.draft_version, dataset_hash=row.dataset_hash, limits=row.limits,
        cases=[{'key': case.case_key, 'state': case.state, 'expected_scores': case.expected_scores, 'result': case.result} for case in cases], completed_at=row.completed_at)


def scenario_context(content):
    return {key: content[key] for key in ('title', 'character_name', 'character_profile', 'situation', 'warning') if key in content}


async def run_scenario_test(db, principal, id, body):
    value = await find_scenario(db, principal, id, True)
    check_version(value, body.expected_version)
    draft = ensure_draft_ready(value.draft)
    approved = await db.scalar(select(SimulatorScenarioReview).where(SimulatorScenarioReview.scenario_id == id, SimulatorScenarioReview.draft_version == value.version,
        SimulatorScenarioReview.content_hash == payload_hash(value.draft)).order_by(SimulatorScenarioReview.created_at.desc(),SimulatorScenarioReview.id.desc()).limit(1))
    if approved is None or approved.decision != 'approved':
        raise ApiError(409, 'dataset_review_required', 'Сначала специалист должен одобрить сценарий, рубрику и эталонные примеры этой версии.')
    row = SimulatorTestRun(foundation_id=principal.foundation_id, scenario_id=id, draft_version=value.version, content_hash=payload_hash(value.draft), scenario_snapshot=value.draft,
        dataset_hash=payload_hash([case.model_dump(mode='json') for case in draft.evaluation_cases]), limits={'max_cases': 20, 'max_turns_per_case': 30, 'max_output_tokens': 2000, 'maximum_score_delta': 0}, actor_id=principal.actor_id)
    db.add(row)
    await db.flush()
    for case in draft.evaluation_cases:
        turns = [{'id': str(uuid5(row.id, f'{case.key}:{index}')), **turn.model_dump(mode='json')} for index, turn in enumerate(case.turns)]
        run = await enqueue_ai_run(db, principal, 'simulator.dataset', {'scenario': scenario_context(value.draft), 'criteria': value.draft['criteria'], 'turns': turns, 'test_run_id': str(row.id), 'case_key': case.key}, max_output_tokens=2000)
        db.add(SimulatorTestCaseRun(test_run_id=row.id, case_key=case.key, ai_run_id=run.id, expected_scores=case.expected_scores, state='pending' if run.state == 'queued' else run.state))
    await db.flush()
    await finalize_test_run(db, row)
    return await test_view(db, row)


async def finalize_test_run(db, row):
    cases = (await db.scalars(select(SimulatorTestCaseRun).where(SimulatorTestCaseRun.test_run_id == row.id))).all()
    states = [case.state for case in cases]
    if any(state == 'pending' for state in states):
        row.state = 'running'
    elif states and all(state == 'passed' for state in states):
        row.state = 'succeeded'
        row.completed_at = utcnow()
    else:
        row.state = 'unavailable' if any(state in ('unavailable', 'budget_exceeded', 'unknown', 'cancelled') for state in states) else 'failed'
        row.completed_at = utcnow()


async def publish_scenario(db, principal, id, body):
    entity = await find_scenario(db, principal, id, True)
    check_version(entity, body.expected_version)
    ensure_draft_ready(entity.draft)
    content_hash = payload_hash(entity.draft)
    review = await db.scalar(select(SimulatorScenarioReview).where(SimulatorScenarioReview.scenario_id==id,SimulatorScenarioReview.draft_version==entity.version).order_by(SimulatorScenarioReview.created_at.desc(),SimulatorScenarioReview.id.desc()).limit(1))
    test = await db.get(SimulatorTestRun, body.test_run_id)
    if not review or review.id != body.review_id or review.scenario_id != id or review.decision != 'approved' or review.draft_version != entity.version or review.content_hash != content_hash:
        raise ApiError(409, 'scenario_review_required', 'Нужно одобрение специалиста для текущей версии сценария и рубрики.')
    if not test or test.scenario_id != id or test.draft_version != entity.version or test.content_hash != content_hash or test.state != 'succeeded':
        raise ApiError(409, 'scenario_test_required', 'Нужен успешный прогон утверждённых эталонных примеров текущей версии.')
    number = (await db.scalar(select(func.max(SimulatorScenarioVersion.version)).where(SimulatorScenarioVersion.scenario_id == id)) or 0) + 1
    rubric = RubricVersion(scenario_id=id, version=number, criteria=entity.draft['criteria'])
    db.add(rubric)
    await db.flush()
    content = {key: value for key, value in entity.draft.items() if key != 'evaluation_cases'}
    content['reply_prompt_version'] = jobs.REPLY_PROMPT_VERSION
    content['assessment_prompt_version'] = jobs.ASSESSMENT_PROMPT_VERSION
    version = SimulatorScenarioVersion(foundation_id=principal.foundation_id, scenario_id=id, version=number, content=content, rubric_version_id=rubric.id, review_id=review.id, test_run_id=test.id, published_by=principal.actor_id)
    db.add(version)
    await db.flush()
    entity.publication_id = version.id
    entity.archived_at = None
    entity.version += 1
    entity.updated_at = utcnow()
    entity.updated_by = principal.actor_id
    return await staff_view(db, entity, principal)


async def withdraw_scenario(db, principal, id, body):
    entity = await find_scenario(db, principal, id, True)
    check_version(entity, body.expected_version)
    if entity.publication_id:
        publication = await db.get(SimulatorScenarioVersion, entity.publication_id)
        publication.withdrawn_at = utcnow()
    entity.publication_id = None
    entity.archived_at = utcnow()
    entity.version += 1
    entity.updated_at = utcnow()
    return await staff_view(db, entity, principal)


async def session_view(db, entity):
    publication = await db.get(SimulatorScenarioVersion, entity.scenario_version_id)
    turns = (await db.scalars(select(SimulationTurn).where(SimulationTurn.session_id == entity.id).order_by(SimulationTurn.ordinal))).all()
    evaluation = await db.scalar(select(SimulationEvaluation).where(SimulationEvaluation.session_id == entity.id).order_by(SimulationEvaluation.version.desc()).limit(1))
    appeal = await db.scalar(select(EvaluationAppeal).where(EvaluationAppeal.evaluation_id == evaluation.id)) if evaluation else None
    support = (await db.scalars(select(SimulationSupportRequest).where(SimulationSupportRequest.session_id == entity.id).order_by(SimulationSupportRequest.created_at))).all()
    pending = await db.get(AIRun, entity.pending_ai_run_id) if entity.pending_ai_run_id else None
    actions = ['support']
    if entity.state == 'active': actions += ['turn', 'hint', 'pause', 'finish', 'stop']
    elif entity.state == 'paused': actions += ['stop', 'finish'] + (['retry-reply'] if entity.pending_kind == 'reply' else ['resume'])
    elif entity.state == 'waiting_reply': actions += ['pause', 'stop']
    elif entity.state == 'finished':
        actions += ['retry']
        if evaluation and evaluation.state in ('unavailable', 'failed', 'unknown', 'budget_exceeded', 'cancelled'): actions.append('retry-evaluation')
        if evaluation and evaluation.state == 'ready' and appeal is None: actions.append('appeal')
    elif entity.state == 'stopped': actions += ['retry']
    scenario = await db.get(SimulatorScenario, publication.scenario_id)
    if publication.withdrawn_at or scenario.archived_at:
        actions = [action for action in actions if action != 'retry']
    return SimulatorSessionView(id=entity.id, version=entity.version, state=entity.state, scenario=await public_view(db, publication), rubric_version_id=entity.rubric_version_id,
        turns=[SimulatorTurnView(id=turn.id, ordinal=turn.ordinal, speaker=turn.speaker, content=turn.content, source=turn.source, created_at=turn.created_at) for turn in turns],
        evaluation=SimulatorEvaluationView(id=evaluation.id, version=evaluation.version, state=evaluation.state, rubric_version_id=evaluation.rubric_version_id,
            prompt_version=evaluation.prompt_version, model=evaluation.model, result=evaluation.result,
            appeal={'id': str(appeal.id), 'state': appeal.state, 'text': appeal.text, 'response': appeal.response, 'corrected_result': appeal.corrected_result, 'version': appeal.version} if appeal else None) if evaluation else None,
        provider_state=pending.state if pending else None, provider_error=entity.provider_error,
        support_requests=[{'id': str(row.id), 'state': row.state, 'text': row.text, 'response': row.response} for row in support], allowed_actions=actions)


async def append_turn(db, entity, speaker, content, source, run_id=None):
    ordinal = (await db.scalar(select(func.max(SimulationTurn.ordinal)).where(SimulationTurn.session_id == entity.id)) or 0) + 1
    row = SimulationTurn(session_id=entity.id, ordinal=ordinal, speaker=speaker, content=content, source=source, ai_run_id=run_id)
    db.add(row)
    await db.flush()
    return row


async def start_session(db, principal, body):
    owner_filter(principal)
    scenario = await find_scenario(db, principal, body.scenario_id)
    if scenario.publication_id is None or scenario.archived_at:
        raise ApiError(404, 'scenario_not_found', 'Сценарий не опубликован.')
    publication = await db.get(SimulatorScenarioVersion, body.publication_id or scenario.publication_id)
    if publication is None or publication.scenario_id != scenario.id or publication.foundation_id != principal.foundation_id:
        raise ApiError(404,'scenario_version_not_found','Версия сценария не найдена.')
    if body.parent_session_id:
        previous = await find_attempt(db, principal, body.parent_session_id)
        original = await db.get(SimulatorScenarioVersion, previous.scenario_version_id)
        if original.scenario_id != scenario.id or original.withdrawn_at:
            raise ApiError(409, 'scenario_version_unavailable', 'Эта версия больше не доступна для новой попытки.')
        publication = original
    if publication.withdrawn_at:
        raise ApiError(404, 'scenario_not_found', 'Сценарий не опубликован.')
    entity = SimulationSession(foundation_id=principal.foundation_id, user_id=principal.user_id, registration_id=None if principal.user_id else principal.registration_id,
        scenario_version_id=publication.id, rubric_version_id=publication.rubric_version_id, parent_session_id=body.parent_session_id)
    db.add(entity)
    await db.flush()
    await append_turn(db, entity, 'character', publication.content['first_turn'], 'authored')
    return await session_view(db, entity)


async def conversation_input(db, entity):
    publication = await db.get(SimulatorScenarioVersion, entity.scenario_version_id)
    turns = (await db.scalars(select(SimulationTurn).where(SimulationTurn.session_id == entity.id, SimulationTurn.speaker.in_(['character', 'volunteer'])).order_by(SimulationTurn.ordinal))).all()
    return publication, [{'id': str(turn.id), 'speaker': turn.speaker, 'content': turn.content} for turn in turns]


async def enqueue_reply(db, principal, entity):
    publication, turns = await conversation_input(db, entity)
    if publication.content.get('reply_prompt_version') != jobs.REPLY_PROMPT_VERSION:
        raise ApiError(409, 'prompt_version_unavailable', 'Для этой версии сейчас нельзя продолжить диалог. Сохранённая история доступна.')
    run = await enqueue_ai_run(db, principal, 'simulator.reply', {'scenario': scenario_context(publication.content), 'turns': turns,
        'target_session_id': str(entity.id), 'expected_session_version': entity.version}, source_refs=[str(publication.id)], max_output_tokens=1200)
    entity.pending_ai_run_id = run.id
    entity.pending_kind = 'reply'
    entity.provider_error = run.error_code
    entity.state = 'waiting_reply' if run.state == 'queued' else 'paused'
    return run


async def send_turn(db, principal, id, body):
    entity = await find_attempt(db, principal, id, True)
    check_version(entity, body.expected_version)
    if entity.state != 'active' or entity.pending_kind:
        raise ApiError(409, 'simulation_not_active', 'Сначала дождитесь ответа или вернитесь к диалогу.')
    count = await db.scalar(select(func.count()).select_from(SimulationTurn).where(SimulationTurn.session_id == id))
    if count >= 100:
        raise ApiError(409, 'simulation_turn_limit', 'Диалог достиг предела длины. Завершите попытку и откройте разбор.')
    await append_turn(db, entity, 'volunteer', body.content, 'volunteer')
    entity.version += 1
    entity.updated_at = utcnow()
    await enqueue_reply(db, principal, entity)
    return await session_view(db, entity)


async def change_session(db, principal, id, body, action):
    entity = await find_attempt(db, principal, id, True)
    check_version(entity, body.expected_version)
    if action == 'pause' and entity.state in ('active', 'waiting_reply'):
        entity.state = 'paused'
    elif action == 'resume' and entity.state == 'paused' and entity.pending_kind is None:
        entity.state = 'active'
    elif action == 'stop' and entity.state not in ('finished', 'stopped'):
        entity.state = 'stopped'
    elif action == 'retry-reply' and entity.state == 'paused' and entity.pending_kind == 'reply':
        old_run = await db.get(AIRun, entity.pending_ai_run_id)
        if old_run and old_run.state in ('queued', 'calling'):
            raise ApiError(409, 'reply_pending', 'Ответ ещё обрабатывается.')
        entity.version += 1
        await enqueue_reply(db, principal, entity)
        entity.updated_at = utcnow()
        return await session_view(db, entity)
    elif action == 'hint' and entity.state == 'active':
        publication = await db.get(SimulatorScenarioVersion, entity.scenario_version_id)
        hints = publication.content.get('hints', [])
        if not hints:
            raise ApiError(409, 'hint_unavailable', 'Для этого сценария подсказка не подготовлена.')
        await append_turn(db, entity, 'hint', hints[min(entity.hint_count, len(hints) - 1)], 'authored')
        entity.hint_count += 1
    else:
        raise ApiError(409, 'simulation_state_conflict', 'Состояние попытки изменилось. Обновите страницу.')
    entity.version += 1
    entity.updated_at = utcnow()
    return await session_view(db, entity)


async def finish_session(db, principal, id, body, retry=False):
    entity = await find_attempt(db, principal, id, True)
    check_version(entity, body.expected_version)
    if not retry and entity.state not in ('active', 'paused') or retry and entity.state != 'finished':
        raise ApiError(409, 'simulation_state_conflict', 'Сейчас нельзя запросить разбор.')
    if entity.pending_ai_run_id:
        old = await db.get(AIRun, entity.pending_ai_run_id)
        if old and old.state in ('queued', 'calling'):
            raise ApiError(409, 'reply_pending', 'Сначала дождитесь завершения ответа или остановите попытку.')
    publication, turns = await conversation_input(db, entity)
    if not any(turn['speaker'] == 'volunteer' for turn in turns):
        raise ApiError(409, 'simulation_empty', 'Сначала ответьте персонажу хотя бы один раз.')
    if publication.content.get('assessment_prompt_version') != jobs.ASSESSMENT_PROMPT_VERSION:
        raise ApiError(409, 'prompt_version_unavailable', 'Разбор этой версии сейчас недоступен.')
    version = (await db.scalar(select(func.max(SimulationEvaluation.version)).where(SimulationEvaluation.session_id == id)) or 0) + 1
    evaluation_id = uuid5(entity.id, f'evaluation:{version}')
    rubric = await db.get(RubricVersion, entity.rubric_version_id)
    run = await enqueue_ai_run(db, principal, 'simulator.evaluate', {'scenario': scenario_context(publication.content), 'criteria': rubric.criteria, 'turns': turns,
        'target_session_id': str(id), 'evaluation_id': str(evaluation_id), 'rubric_version_id': str(rubric.id)}, source_refs=[str(publication.id), str(rubric.id)], max_output_tokens=2000)
    evaluation = SimulationEvaluation(id=evaluation_id, session_id=id, rubric_version_id=rubric.id, version=version, ai_run_id=run.id, prompt_version=run.prompt_version, model=run.model,
        state='pending' if run.state == 'queued' else run.state, completed_at=utcnow() if run.state != 'queued' else None)
    db.add(evaluation)
    entity.pending_ai_run_id = run.id
    entity.pending_kind = 'evaluation'
    entity.provider_error = run.error_code
    entity.state = 'evaluating' if run.state == 'queued' else 'finished'
    entity.version += 1
    entity.updated_at = utcnow()
    await db.flush()
    return await session_view(db, entity)


def validate_assessment(output, criteria, turns):
    assessment = SimulatorAssessmentOutput.model_validate(output)
    expected = {criterion['key'] for criterion in criteria}
    actual = [item.criterion_key for item in assessment.criteria]
    if set(actual) != expected or len(actual) != len(expected):
        raise ValueError('criterion_set_mismatch')
    by_id = {str(turn['id']): turn for turn in turns}
    for item in assessment.criteria:
        for evidence in item.evidence:
            turn = by_id.get(str(evidence.turn_id))
            if turn is None or turn['speaker'] != 'volunteer' or evidence.quote not in turn['content']:
                raise ValueError('evidence_not_in_volunteer_turn')
    return assessment.model_dump(mode='json')


async def callback_principal(db, run):
    session = await db.get(Session, run.request_session_id, populate_existing=True)
    if session is None or session.revoked_at or session.expires_at <= utcnow():
        return None
    try:
        principal = await resolve_principal(db, session)
    except ApiError:
        return None
    if principal.foundation_id != run.foundation_id or principal.actor_id != run.actor_id:
        return None
    return principal


async def apply_ai_result(db, run, context):
    await context.fence(db)
    principal = await callback_principal(db, run)
    if run.task == 'simulator.dataset':
        case = await db.scalar(select(SimulatorTestCaseRun).where(SimulatorTestCaseRun.ai_run_id == run.id).with_for_update())
        if case is None or case.state != 'pending':
            return
        test = await db.scalar(select(SimulatorTestRun).where(SimulatorTestRun.id == case.test_run_id, SimulatorTestRun.foundation_id == run.foundation_id).with_for_update())
        if test is None:
            return
        if principal is None or not principal.has_permission('simulator.manage'):
            case.state = 'cancelled'
        elif run.state != 'succeeded':
            case.state = run.state
        else:
            try:
                validated = validate_assessment(run.output, run.input_data['criteria'], run.input_data['turns'])
                scores = {item['criterion_key']: item['score'] for item in validated['criteria']}
                case.result = {'assessment': validated, 'actual_scores': scores, 'prompt_version': run.prompt_version, 'model': run.model}
                case.state = 'passed' if scores == case.expected_scores else 'failed'
            except (ValueError, KeyError, TypeError):
                case.state = 'failed'
                case.result = {'error_code': 'invalid_evidence'}
        await db.flush()
        await finalize_test_run(db, test)
        return
    raw_id = run.input_data.get('target_session_id')
    if not raw_id:
        return
    entity = await db.scalar(select(SimulationSession).where(SimulationSession.id == UUID(raw_id), SimulationSession.foundation_id == run.foundation_id).with_for_update())
    if entity is None or entity.pending_ai_run_id != run.id or entity.state == 'stopped':
        return
    if principal is None or entity.user_id != principal.user_id or entity.registration_id != principal.registration_id:
        error = 'session_revoked'
    else:
        error = run.error_code if run.state != 'succeeded' else None
    publication, turns = await conversation_input(db, entity)
    if payload_hash(turns) != payload_hash(run.input_data.get('turns', [])):
        error = 'conversation_changed'
    if run.task == 'simulator.reply':
        if error is None and run.state == 'succeeded':
            # Matching pending run plus the parent row lock makes callback replay harmless.
            await append_turn(db, entity, 'character', run.output['content'], 'ai', run.id)
            entity.pending_ai_run_id = None
            entity.pending_kind = None
            entity.provider_error = None
            entity.state = 'paused' if entity.state == 'paused' else 'active'
        else:
            entity.state = 'paused'
            entity.provider_error = error or run.state
    elif run.task == 'simulator.evaluate':
        evaluation = await db.scalar(select(SimulationEvaluation).where(SimulationEvaluation.ai_run_id == run.id).with_for_update())
        if evaluation is None or evaluation.state != 'pending':
            return
        evaluation.state = run.state if run.state != 'succeeded' else 'ready'
        if error is None and run.state == 'succeeded':
            rubric = await db.get(RubricVersion, evaluation.rubric_version_id)
            try:
                evaluation.result = validate_assessment(run.output, rubric.criteria, turns)
            except (ValueError, KeyError, TypeError):
                evaluation.state = 'failed'
                error = 'invalid_evidence'
        elif error:
            evaluation.state = 'cancelled' if error == 'session_revoked' else 'failed' if run.state == 'succeeded' else run.state
        evaluation.completed_at = utcnow()
        entity.state = 'finished'
        entity.provider_error = error
        entity.pending_ai_run_id = None
        entity.pending_kind = None
    entity.version += 1
    entity.updated_at = utcnow()


async def appeal_evaluation(db, principal, id, body):
    evaluation = await db.get(SimulationEvaluation, id)
    if evaluation is None:
        raise ApiError(404, 'evaluation_not_found', 'Разбор не найден.')
    entity = await find_attempt(db, principal, evaluation.session_id, True)
    if evaluation.state != 'ready':
        raise ApiError(409, 'evaluation_unavailable', 'Обсудить можно готовый разбор.')
    if await db.scalar(select(EvaluationAppeal.id).where(EvaluationAppeal.evaluation_id == id)):
        raise ApiError(409, 'appeal_exists', 'Обращение по этому разбору уже сохранено.')
    row = EvaluationAppeal(foundation_id=principal.foundation_id, evaluation_id=id, text=body.text)
    db.add(row)
    entity.version += 1
    entity.updated_at = utcnow()
    await db.flush()
    return await session_view(db, entity)


async def resolve_appeal(db, principal, id, body):
    row = await db.scalar(select(EvaluationAppeal).where(EvaluationAppeal.id == id, EvaluationAppeal.foundation_id == principal.foundation_id).with_for_update())
    if row is None:
        raise ApiError(404, 'appeal_not_found', 'Обращение не найдено.')
    check_version(row, body.expected_version)
    if row.state == 'resolved':
        raise ApiError(409, 'appeal_resolved', 'Ответ уже сохранён.')
    evaluation = await db.get(SimulationEvaluation, row.evaluation_id)
    entity = await find_attempt(db, principal, evaluation.session_id, True, reviewer=True)
    if body.corrected_result is not None:
        rubric = await db.get(RubricVersion, evaluation.rubric_version_id)
        _, turns = await conversation_input(db, entity)
        try:
            row.corrected_result = validate_assessment(body.corrected_result.model_dump(mode='json'), rubric.criteria, turns)
        except ValueError as error:
            raise ApiError(422, 'invalid_review_evidence', 'Исправление должно ссылаться на реальные ответы этой попытки.') from error
    row.state = 'resolved'
    row.response = body.response
    row.reviewer_id = principal.actor_id
    row.reviewed_at = utcnow()
    row.version += 1
    entity.version += 1
    entity.updated_at = utcnow()
    await db.flush()
    return {'id': str(row.id), 'version': row.version, 'state': row.state, 'response': row.response}


async def create_support(db, principal, id, body):
    entity = await find_attempt(db, principal, id, True)
    check_version(entity,body.expected_version)
    row = SimulationSupportRequest(foundation_id=principal.foundation_id, session_id=id, text=body.text)
    db.add(row)
    # The request is an actual staff queue item. No named person/delivery is invented.
    if entity.state not in ('finished', 'stopped'):
        entity.state = 'paused'
    entity.version += 1
    entity.updated_at = utcnow()
    await db.flush()
    return await session_view(db, entity)


async def resolve_support(db, principal, id, body):
    row = await db.scalar(select(SimulationSupportRequest).where(SimulationSupportRequest.id == id, SimulationSupportRequest.foundation_id == principal.foundation_id).with_for_update())
    if row is None:
        raise ApiError(404, 'support_request_not_found', 'Запрос не найден.')
    check_version(row, body.expected_version)
    row.response = body.response
    row.state = 'resolved'
    row.reviewer_id = principal.actor_id
    row.responded_at = utcnow()
    row.version += 1
    return {'id': str(row.id), 'version': row.version, 'state': row.state, 'response': row.response}


async def claim_registration(db, registration_id, user_id):
    from app.core.models import User
    user = await db.get(User, user_id)
    await db.execute(update(SimulationSession).where(SimulationSession.registration_id == registration_id,
        SimulationSession.foundation_id == user.foundation_id).values(registration_id=None, user_id=user_id))
