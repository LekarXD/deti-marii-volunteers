from datetime import datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class ConsentInput(StrictModel):
    personal_data: bool
    news: bool = False
    document_version: Literal["4"] = "4"

class DraftCommand(StrictModel):
    expected_version: int = Field(ge=0)
    answers: dict[str, Any]
    step: int = Field(default=0, ge=0, le=2)

class SubmissionCommand(StrictModel):
    expected_version: int = Field(ge=0)
    answers: dict[str, Any]
    consents: ConsentInput

class VersionCommand(StrictModel):
    expected_version: int = Field(ge=1)

class ReviewCommand(VersionCommand):
    state: Literal["reviewing", "discussed", "paused", "closed"]
    public_message: str = Field(default="", max_length=4000)
    assigned_coordinator_id: UUID | None = None

class NoteCommand(StrictModel):
    text: str = Field(min_length=1, max_length=8000)

class RequestCommand(StrictModel):
    kind: Literal["alternate_time", "question", "road_help"]
    text: str = Field(min_length=1, max_length=4000)

class ResponseCommand(VersionCommand):
    text: str = Field(min_length=1, max_length=4000)

class FormView(BaseModel):
    id: UUID
    version: int
    content: dict[str, Any]

class DraftView(BaseModel):
    id: UUID | None = None
    version: int
    step: int
    answers: dict[str, Any]
    form: FormView

class RevisionView(BaseModel):
    id: UUID
    number: int
    form_version_id: UUID
    answers: dict[str, Any]
    created_at: datetime

class ReviewEventView(BaseModel):
    id: UUID
    kind: str
    state: str
    public_message: str
    created_at: datetime

class ApplicationSelfView(BaseModel):
    id: UUID
    version: int
    submission_state: str
    review_state: str
    submitted_at: datetime
    revision: RevisionView
    history: list[ReviewEventView]
    consents: dict[str, bool]

class CandidateView(ApplicationSelfView):
    assigned_coordinator_id: UUID | None
    revisions: list[RevisionView]

class CandidateListView(BaseModel):
    items: list[CandidateView]
    total: int
    offset: int
    limit: int

class NoteView(BaseModel):
    id: UUID
    text: str
    author_id: str
    created_at: datetime

class ResponseView(BaseModel):
    id: UUID
    text: str
    created_at: datetime

class RequestView(BaseModel):
    id: UUID
    application_id: UUID
    kind: str
    text: str
    state: str
    version: int
    created_at: datetime
    responses: list[ResponseView]
