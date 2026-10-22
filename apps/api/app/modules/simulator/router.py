from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query, Request
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal, get_principal, require_permission
from app.core.db import get_db
from app.core.errors import ApiError
from . import service
from .commands import execute_command
from .fixtures import authored_drafts
from .models import EvaluationAppeal, SimulationEvaluation, SimulationSession, SimulationSupportRequest, SimulatorScenario, SimulatorScenarioVersion, SimulatorTestRun
from .schemas import SimulatorAppealCommand, SimulatorAppealDetail, SimulatorDraftUpdate, SimulatorExampleCreate, SimulatorHumanReview, SimulatorPublishCommand, SimulatorReviewCommand, SimulatorReviewQueueItem, SimulatorScenarioDraft, SimulatorScenarioPage, SimulatorScenarioPublicView, SimulatorScenarioStaffView, SimulatorSessionPage, SimulatorSessionStart, SimulatorSessionView, SimulatorSimpleResult, SimulatorStaffScenarioPage, SimulatorSupportCommand, SimulatorTestRunView, SimulatorTurnCommand, SimulatorVersionCommand

router = APIRouter(tags=['simulator'])
writer = require_permission('simulator.manage')
reviewer = require_permission('simulator.review')


async def author(principal: Principal = Depends(get_principal)):
    if not (principal.has_permission('simulator.manage') or principal.has_permission('simulator.review')):
        raise ApiError(403, 'permission_denied', 'Недостаточно прав для сценариев.')
    return principal


@router.get('/simulator/scenarios', response_model=SimulatorScenarioPage, operation_id='listSimulatorScenarios')
async def public_scenarios(cursor: UUID | None = None, limit: int = Query(30, ge=1, le=100), principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    query = select(SimulatorScenarioVersion).join(SimulatorScenario, SimulatorScenario.publication_id == SimulatorScenarioVersion.id).where(
        SimulatorScenario.foundation_id == principal.foundation_id, SimulatorScenario.archived_at.is_(None), SimulatorScenarioVersion.withdrawn_at.is_(None))
    if cursor:
        query = query.where(SimulatorScenarioVersion.id > cursor)
    values = list((await db.scalars(query.order_by(SimulatorScenarioVersion.id).limit(limit + 1))).all())
    return SimulatorScenarioPage(items=[await service.public_view(db, value) for value in values[:limit]], next_cursor=values[limit - 1].id if len(values) > limit else None)


@router.get('/simulator/scenarios/{scenario_id}', response_model=SimulatorScenarioPublicView, operation_id='getPublishedSimulatorScenario')
async def public_scenario(scenario_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    entity = await service.find_scenario(db, principal, scenario_id)
    if not entity.publication_id or entity.archived_at:
        raise ApiError(404, 'scenario_not_found', 'Сценарий не опубликован.')
    version = await db.get(SimulatorScenarioVersion, entity.publication_id)
    if version.withdrawn_at:
        raise ApiError(404, 'scenario_not_found', 'Сценарий не опубликован.')
    return await service.public_view(db, version)


@router.get('/coord/simulator/scenarios', response_model=SimulatorStaffScenarioPage, operation_id='listStaffSimulatorScenarios')
async def staff_scenarios(cursor: UUID | None = None, limit: int = Query(30, ge=1, le=100), principal: Principal = Depends(author), db: AsyncSession = Depends(get_db)):
    query = select(SimulatorScenario).where(SimulatorScenario.foundation_id == principal.foundation_id)
    if cursor:
        query = query.where(SimulatorScenario.id > cursor)
    values = list((await db.scalars(query.order_by(SimulatorScenario.id).limit(limit + 1))).all())
    return SimulatorStaffScenarioPage(items=[await service.staff_view(db, value, principal) for value in values[:limit]], next_cursor=values[limit - 1].id if len(values) > limit else None)


@router.get('/coord/simulator/examples', response_model=list[SimulatorScenarioDraft], operation_id='getAuthoredSimulatorExamples')
async def examples(principal: Principal = Depends(writer)):
    return authored_drafts()


@router.post('/coord/simulator/scenarios/from-example', response_model=SimulatorScenarioStaffView, operation_id='createSimulatorScenarioFromExample')
async def from_example(body: SimulatorExampleCreate, request: Request, key: str = Header(alias='Idempotency-Key'), principal: Principal = Depends(writer), db: AsyncSession = Depends(get_db)):
    content = SimulatorScenarioDraft.model_validate(authored_drafts()[body.example_index])
    return await execute_command(db, principal, 'simulator.from-example', key, body, lambda: service.create_scenario(db, principal, content), request, 'simulator.manage')


@router.post('/coord/simulator/scenarios', response_model=SimulatorScenarioStaffView, operation_id='createSimulatorScenario')
async def create(body: SimulatorScenarioDraft, request: Request, key: str = Header(alias='Idempotency-Key'), principal: Principal = Depends(writer), db: AsyncSession = Depends(get_db)):
    return await execute_command(db, principal, 'simulator.create', key, body, lambda: service.create_scenario(db, principal, body), request, 'simulator.manage')


@router.get('/coord/simulator/scenarios/{scenario_id}', response_model=SimulatorScenarioStaffView, operation_id='getStaffSimulatorScenario')
async def detail(scenario_id: UUID, principal: Principal = Depends(author), db: AsyncSession = Depends(get_db)):
    return await service.staff_view(db, await service.find_scenario(db, principal, scenario_id), principal)


@router.patch('/coord/simulator/scenarios/{scenario_id}', response_model=SimulatorScenarioStaffView, operation_id='saveSimulatorScenario')
async def save(scenario_id: UUID, body: SimulatorDraftUpdate, request: Request, key: str = Header(alias='Idempotency-Key'), principal: Principal = Depends(writer), db: AsyncSession = Depends(get_db)):
    return await execute_command(db, principal, f'simulator.save:{scenario_id}', key, body, lambda: service.update_scenario(db, principal, scenario_id, body), request, 'simulator.manage')


@router.post('/coord/simulator/scenarios/{scenario_id}/review', response_model=SimulatorScenarioStaffView, operation_id='reviewSimulatorScenario')
async def review(scenario_id: UUID, body: SimulatorReviewCommand, request: Request, key: str = Header(alias='Idempotency-Key'), principal: Principal = Depends(reviewer), db: AsyncSession = Depends(get_db)):
    return await execute_command(db, principal, f'simulator.review:{scenario_id}', key, body, lambda: service.review_scenario(db, principal, scenario_id, body), request, 'simulator.review')


@router.post('/coord/simulator/scenarios/{scenario_id}/test', response_model=SimulatorTestRunView, operation_id='testSimulatorScenarioDataset')
async def test(scenario_id: UUID, body: SimulatorVersionCommand, request: Request, key: str = Header(alias='Idempotency-Key'), principal: Principal = Depends(writer), db: AsyncSession = Depends(get_db)):
    return await execute_command(db, principal, f'simulator.test:{scenario_id}', key, body, lambda: service.run_scenario_test(db, principal, scenario_id, body), request, 'simulator.manage')


@router.get('/coord/simulator/test-runs/{run_id}', response_model=SimulatorTestRunView, operation_id='getSimulatorDatasetTestRun')
async def test_result(run_id: UUID, principal: Principal = Depends(author), db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(SimulatorTestRun).where(SimulatorTestRun.id == run_id, SimulatorTestRun.foundation_id == principal.foundation_id))
    if row is None:
        raise ApiError(404, 'test_run_not_found', 'Прогон не найден.')
    return await service.test_view(db, row)


@router.post('/coord/simulator/scenarios/{scenario_id}/publish', response_model=SimulatorScenarioStaffView, operation_id='publishReviewedSimulatorScenario')
async def publish(scenario_id: UUID, body: SimulatorPublishCommand, request: Request, key: str = Header(alias='Idempotency-Key'), principal: Principal = Depends(writer), db: AsyncSession = Depends(get_db)):
    return await execute_command(db, principal, f'simulator.publish:{scenario_id}', key, body, lambda: service.publish_scenario(db, principal, scenario_id, body), request, 'simulator.manage')


@router.post('/coord/simulator/scenarios/{scenario_id}/withdraw', response_model=SimulatorScenarioStaffView, operation_id='withdrawSimulatorScenario')
async def withdraw(scenario_id: UUID, body: SimulatorVersionCommand, request: Request, key: str = Header(alias='Idempotency-Key'), principal: Principal = Depends(writer), db: AsyncSession = Depends(get_db)):
    return await execute_command(db, principal, f'simulator.withdraw:{scenario_id}', key, body, lambda: service.withdraw_scenario(db, principal, scenario_id, body), request, 'simulator.manage')


@router.post('/simulation-sessions', response_model=SimulatorSessionView, operation_id='startSimulationSession')
async def start(body: SimulatorSessionStart, request: Request, key: str = Header(alias='Idempotency-Key'), principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return await execute_command(db, principal, 'simulation.start', key, body, lambda: service.start_session(db, principal, body), request)


@router.get('/simulation-sessions', response_model=SimulatorSessionPage, operation_id='listOwnSimulationSessions')
async def own_sessions(cursor: UUID | None = None, limit: int = Query(30, ge=1, le=100), principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    query = select(SimulationSession).where(SimulationSession.foundation_id == principal.foundation_id, service.owner_filter(principal))
    if cursor:
        query = query.where(SimulationSession.id > cursor)
    values = list((await db.scalars(query.order_by(SimulationSession.id).limit(limit + 1))).all())
    return SimulatorSessionPage(items=[await service.session_view(db, value) for value in values[:limit]], next_cursor=values[limit - 1].id if len(values) > limit else None)


@router.get('/simulation-sessions/{session_id}', response_model=SimulatorSessionView, operation_id='getOwnSimulationSession')
async def session(session_id: UUID, principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return await service.session_view(db, await service.find_attempt(db, principal, session_id))


@router.post('/simulation-sessions/{session_id}/turns', response_model=SimulatorSessionView, operation_id='sendSimulationTurn')
async def turn(session_id: UUID, body: SimulatorTurnCommand, request: Request, key: str = Header(alias='Idempotency-Key'), principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return await execute_command(db, principal, f'simulation.turn:{session_id}', key, body, lambda: service.send_turn(db, principal, session_id, body), request)


@router.post('/simulation-evaluations/{evaluation_id}/appeals', response_model=SimulatorSessionView, operation_id='appealSimulationEvaluation')
async def appeal(evaluation_id: UUID, body: SimulatorAppealCommand, request: Request, key: str = Header(alias='Idempotency-Key'), principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return await execute_command(db, principal, f'simulation.appeal:{evaluation_id}', key, body, lambda: service.appeal_evaluation(db, principal, evaluation_id, body), request)


@router.post('/simulation-sessions/{session_id}/support-requests', response_model=SimulatorSessionView, operation_id='requestSimulationHumanSupport')
async def support(session_id: UUID, body: SimulatorSupportCommand, request: Request, key: str = Header(alias='Idempotency-Key'), principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    return await execute_command(db, principal, f'simulation.support:{session_id}', key, body, lambda: service.create_support(db, principal, session_id, body), request)


@router.get('/coord/simulator/appeals', response_model=list[SimulatorReviewQueueItem], operation_id='listSimulatorAppeals')
async def appeal_queue(principal: Principal = Depends(reviewer), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(EvaluationAppeal).where(EvaluationAppeal.foundation_id == principal.foundation_id).order_by(case((EvaluationAppeal.state != 'resolved', 0), else_=1), EvaluationAppeal.created_at.desc()).limit(100))).all()
    result = []
    for row in rows:
        evaluation = await db.get(SimulationEvaluation, row.evaluation_id)
        attempt = await db.get(SimulationSession, evaluation.session_id)
        publication = await db.get(SimulatorScenarioVersion, attempt.scenario_version_id)
        result.append(await service.queue_item(db, row, attempt, publication.content['title'], evaluation))
    return result


@router.get('/coord/simulator/appeals/{appeal_id}', response_model=SimulatorAppealDetail, operation_id='getSimulatorAppealContext')
async def appeal_context(appeal_id: UUID, principal: Principal = Depends(reviewer), db: AsyncSession = Depends(get_db)):
    row = await db.scalar(select(EvaluationAppeal).where(EvaluationAppeal.id == appeal_id, EvaluationAppeal.foundation_id == principal.foundation_id))
    if row is None:
        raise ApiError(404, 'appeal_not_found', 'Обращение не найдено.')
    evaluation = await db.get(SimulationEvaluation, row.evaluation_id)
    attempt = await service.find_attempt(db, principal, evaluation.session_id, reviewer=True)
    view = await service.session_view(db, attempt)
    view.allowed_actions=[]
    return SimulatorAppealDetail(appeal=await service.queue_item(db, row, attempt, view.scenario.title, evaluation), attempt=view)


@router.post('/coord/simulator/appeals/{appeal_id}/resolve', response_model=SimulatorSimpleResult, operation_id='resolveSimulatorAppeal')
async def resolve_appeal(appeal_id: UUID, body: SimulatorHumanReview, request: Request, key: str = Header(alias='Idempotency-Key'), principal: Principal = Depends(reviewer), db: AsyncSession = Depends(get_db)):
    return await execute_command(db, principal, f'simulator.resolve-appeal:{appeal_id}', key, body, lambda: service.resolve_appeal(db, principal, appeal_id, body), request, 'simulator.review')


@router.get('/coord/simulator/support-requests', response_model=list[SimulatorReviewQueueItem], operation_id='listSimulationSupportRequests')
async def support_queue(principal: Principal = Depends(reviewer), db: AsyncSession = Depends(get_db)):
    rows = (await db.scalars(select(SimulationSupportRequest).where(SimulationSupportRequest.foundation_id == principal.foundation_id).order_by(case((SimulationSupportRequest.state != 'resolved', 0), else_=1), SimulationSupportRequest.created_at.desc()).limit(100))).all()
    result = []
    for row in rows:
        attempt = await db.get(SimulationSession, row.session_id)
        publication = await db.get(SimulatorScenarioVersion, attempt.scenario_version_id)
        result.append(await service.queue_item(db, row, attempt, publication.content['title']))
    return result


@router.post('/coord/simulator/support-requests/{support_id}/resolve', response_model=SimulatorSimpleResult, operation_id='resolveSimulationSupportRequest')
async def resolve_support(support_id: UUID, body: SimulatorHumanReview, request: Request, key: str = Header(alias='Idempotency-Key'), principal: Principal = Depends(reviewer), db: AsyncSession = Depends(get_db)):
    return await execute_command(db, principal, f'simulator.resolve-support:{support_id}', key, body, lambda: service.resolve_support(db, principal, support_id, body), request, 'simulator.review')


@router.post('/simulation-sessions/{session_id}/{action}', response_model=SimulatorSessionView, operation_id='changeSimulationSession')
async def change(session_id: UUID, action: str, body: SimulatorVersionCommand, request: Request, key: str = Header(alias='Idempotency-Key'), principal: Principal = Depends(get_principal), db: AsyncSession = Depends(get_db)):
    if action not in ('pause', 'resume', 'stop', 'hint', 'retry-reply', 'finish', 'retry-evaluation'):
        raise ApiError(404, 'simulation_action_not_found', 'Действие не найдено.')
    callback = (lambda: service.finish_session(db, principal, session_id, body, action == 'retry-evaluation')) if action in ('finish', 'retry-evaluation') else (lambda: service.change_session(db, principal, session_id, body, action))
    return await execute_command(db, principal, f'simulation.{action}:{session_id}', key, body, callback, request)


