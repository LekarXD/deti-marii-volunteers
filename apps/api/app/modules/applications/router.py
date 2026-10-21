from uuid import UUID
from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import select, func, cast, String, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal, get_principal, require_permission, authz_guard
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.audit import audit
from app.core.idempotency import begin_command, finish_command
from . import service
from .models import Application, ApplicationRevision, ApplicationPrivateNote, CandidateRequest
from .schemas import (DraftCommand, SubmissionCommand, VersionCommand, ApplicationReviewCommand, NoteCommand, RequestCommand,
    ResponseCommand, DraftView, ApplicationSelfView, CandidateView, CandidateListView, NoteView, RequestView)

router = APIRouter(prefix="/api/v1", tags=["applications"])


async def run_command(db, principal, operation, key, command, action, *, permission=None):
    await authz_guard(db, principal)
    if operation in ("application.draft", "application.submit", "application.revise"):
        await service.verified_questionnaire_email(db, principal)
    if permission and not principal.has_permission(permission):
        raise ApiError(403, "permission_denied", "Недостаточно прав")
    payload = command.model_dump(mode="json")
    prior = await begin_command(db, principal, operation, key, payload)
    if prior is not None:
        await db.commit()
        return prior
    result = await action()
    encoded = result.model_dump(mode="json") if hasattr(result, "model_dump") else result
    audit(db, principal, operation, "application", encoded.get("application_id", encoded.get("id", "")), payload.keys())
    await finish_command(db, principal, operation, key, encoded)
    await db.commit()
    return encoded


@router.get("/registration/draft", response_model=DraftView)
async def draft(principal: Principal=Depends(get_principal), db: AsyncSession=Depends(get_db)):
    return await service.get_draft(db, principal)


@router.put("/registration/draft", response_model=DraftView)
async def save_draft(command: DraftCommand, principal: Principal=Depends(get_principal), db: AsyncSession=Depends(get_db), idempotency_key: str|None=Header(default=None)):
    return await run_command(db, principal, "application.draft", idempotency_key, command, lambda:service.save_draft(db,principal,command))


@router.post("/applications/submit", response_model=ApplicationSelfView)
async def submit(command: SubmissionCommand, principal: Principal=Depends(get_principal), db: AsyncSession=Depends(get_db), idempotency_key: str|None=Header(default=None)):
    return await run_command(db,principal,"application.submit",idempotency_key,command,lambda:service.submit(db,principal,command))


@router.get("/me/application", response_model=ApplicationSelfView)
async def own(principal: Principal=Depends(get_principal), db: AsyncSession=Depends(get_db)):
    return await service.application_view(db,await service.own_application(db,principal))


@router.post("/me/application/revisions", response_model=ApplicationSelfView)
async def revise(command: SubmissionCommand, principal: Principal=Depends(get_principal), db: AsyncSession=Depends(get_db), idempotency_key: str|None=Header(default=None)):
    return await run_command(db,principal,"application.revise",idempotency_key,command,lambda:service.submit(db,principal,command,revision=True))


@router.post("/me/application/withdraw", response_model=ApplicationSelfView)
async def withdraw(command: VersionCommand, principal: Principal=Depends(get_principal), db: AsyncSession=Depends(get_db), idempotency_key: str|None=Header(default=None)):
    return await run_command(db,principal,"application.withdraw",idempotency_key,command,lambda:service.withdraw(db,principal,command))


@router.get("/coord/candidates", response_model=CandidateListView)
async def candidates(q: str=Query(default="",max_length=200), review_state: str|None=None, assigned_to:UUID|None=None,
    offset:int=Query(default=0,ge=0),limit:int=Query(default=30,ge=1,le=100), principal:Principal=Depends(require_permission("candidates.read")),db:AsyncSession=Depends(get_db)):
    statement=select(Application).join(ApplicationRevision,Application.submitted_revision_id==ApplicationRevision.id).where(Application.foundation_id==principal.foundation_id)
    if q.strip():
        needle=f"%{q.strip().replace('%','').replace('_','')}%"
        statement=statement.where(or_(*(ApplicationRevision.answers[field].astext.ilike(needle) for field in ('firstName','lastName','directions','roles','skills'))))
    if review_state:
        statement=statement.where(Application.review_state==review_state)
    if assigned_to:
        statement=statement.where(Application.assigned_coordinator_id==assigned_to)
    total=(await db.execute(select(func.count()).select_from(statement.subquery()))).scalar_one()
    rows=(await db.execute(statement.order_by(Application.submitted_at.desc(),Application.id).offset(offset).limit(limit))).scalars().all()
    return CandidateListView(items=[await service.application_view(db,row,coordinator=True) for row in rows],total=total,offset=offset,limit=limit)


@router.get("/coord/candidates/{application_id}", response_model=CandidateView)
async def candidate(application_id:UUID,principal:Principal=Depends(require_permission("candidates.read")),db:AsyncSession=Depends(get_db)):
    return await service.application_view(db,await service.coordinator_application(db,principal,application_id),coordinator=True)


@router.post("/coord/candidates/{application_id}/review",response_model=CandidateView)
async def review(application_id:UUID, command:ApplicationReviewCommand,principal:Principal=Depends(require_permission("candidates.review")),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await run_command(db,principal,f"application.review:{application_id}",idempotency_key,command,lambda:service.review(db,principal,application_id,command),permission="candidates.review")


@router.post("/coord/candidates/{application_id}/reopen",response_model=CandidateView)
async def reopen(application_id:UUID,command:VersionCommand,principal:Principal=Depends(require_permission("candidates.review")),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await run_command(db,principal,f"application.reopen:{application_id}",idempotency_key,command,lambda:service.review(db,principal,application_id,command,reopen=True),permission="candidates.review")


@router.get("/coord/candidates/{application_id}/notes",response_model=list[NoteView])
async def notes(application_id:UUID,principal:Principal=Depends(require_permission("candidates.notes")),db:AsyncSession=Depends(get_db)):
    await service.coordinator_application(db,principal,application_id)
    rows=(await db.execute(select(ApplicationPrivateNote).where(ApplicationPrivateNote.application_id==application_id).order_by(ApplicationPrivateNote.created_at))).scalars().all()
    return [NoteView(id=n.id,text=n.text,author_id=n.author_id,created_at=n.created_at) for n in rows]


@router.post("/coord/candidates/{application_id}/notes",response_model=NoteView)
async def add_note(application_id:UUID,command:NoteCommand,principal:Principal=Depends(require_permission("candidates.notes")),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    async def action():
        await service.coordinator_application(db,principal,application_id)
        if not command.text.strip():raise ApiError(422,"validation_error","Напишите заметку")
        note=ApplicationPrivateNote(application_id=application_id,text=command.text.strip(),author_id=principal.actor_id)
        db.add(note);await db.flush()
        return NoteView(id=note.id,text=note.text,author_id=note.author_id,created_at=note.created_at)
    return await run_command(db,principal,f"application.note:{application_id}",idempotency_key,command,action,permission="candidates.notes")


@router.post("/me/candidate-requests",response_model=RequestView)
async def create_request(command:RequestCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await run_command(db,principal,"candidate_request.create",idempotency_key,command,lambda:service.create_request(db,principal,command))


async def request_list(db,principal,coordinator=False):
    query=select(CandidateRequest).join(Application,CandidateRequest.application_id==Application.id).where(Application.foundation_id==principal.foundation_id)
    if not coordinator:query=query.where(service.owner_condition(Application,principal))
    rows=(await db.execute(query.order_by(CandidateRequest.created_at.desc(),CandidateRequest.id).limit(200))).scalars().all()
    return [await service.request_view(db,row) for row in rows]


@router.get("/me/candidate-requests",response_model=list[RequestView])
async def my_requests(principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await request_list(db,principal)


@router.get("/me/candidate-requests/{request_id}",response_model=RequestView)
async def my_request(request_id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.request_view(db,await service.get_request(db,principal,request_id))


@router.get("/coord/candidate-requests",response_model=list[RequestView])
async def all_requests(principal:Principal=Depends(require_permission("candidates.read")),db:AsyncSession=Depends(get_db)):
    return await request_list(db,principal,True)


@router.post("/coord/candidate-requests/{request_id}/respond",response_model=RequestView)
async def respond(request_id:UUID,command:ResponseCommand,principal:Principal=Depends(require_permission("candidates.review")),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await run_command(db,principal,f"candidate_request.respond:{request_id}",idempotency_key,command,lambda:service.respond_request(db,principal,request_id,command),permission="candidates.review")


@router.post("/coord/candidate-requests/{request_id}/resolve",response_model=RequestView)
async def resolve(request_id:UUID,command:VersionCommand,principal:Principal=Depends(require_permission("candidates.review")),db:AsyncSession=Depends(get_db),idempotency_key:str|None=Header(default=None)):
    return await run_command(db,principal,f"candidate_request.resolve:{request_id}",idempotency_key,command,lambda:service.respond_request(db,principal,request_id,command,resolve=True),permission="candidates.review")
