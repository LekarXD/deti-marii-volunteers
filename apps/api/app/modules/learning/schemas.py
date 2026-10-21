from typing import Any
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field


class Command(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AnswerInput(Command):
    question_id: UUID
    selected_option: int = Field(ge=0)


class MiniQuizInput(Command):
    question_index: int = Field(ge=0)
    selected_option: int = Field(ge=0)


class AcknowledgeInput(Command):
    assignment_id: UUID


class StartAttemptInput(Command):
    assignment_id: UUID | None = None


class EmptyCommand(Command):
    pass


class QuestionView(BaseModel):
    id: UUID
    prompt: str
    options: list[str]


class FeedbackView(BaseModel):
    question_id: UUID
    selected_option: int
    correct: bool
    explanation: str


class AttemptView(BaseModel):
    id: UUID
    title: str
    intro: str
    assignment_id: UUID
    assessment_version_id: UUID
    state: str
    questions: list[QuestionView]
    answers: list[FeedbackView]
    score: int | None
    total: int


class LessonSummary(BaseModel):
    id: UUID
    mode: str = "feed"
    lesson_id: UUID
    key: str
    title: str
    minutes: int
    completed: bool


class AssignmentView(BaseModel):
    id: UUID
    source_revision: str | None = None
    source_hash: str | None = None
    change_note: str = ""
    track_id: UUID
    track_key: str
    release_id: UUID
    release_number: int
    title: str
    intro: str
    lessons: list[LessonSummary]
    assessment_version_id: UUID | None
    completed: bool
    acknowledged: bool
    latest_attempt_id: UUID | None
    latest_attempt_state: str | None
    reacknowledgement_required: bool


class PreparationView(BaseModel):
    assignments: list[AssignmentView]
    introduction_completed: bool
    booking_requires_introduction: bool = False


class LessonView(BaseModel):
    id: UUID
    mode: str = "feed"
    title: str
    minutes: int
    blocks: list[dict[str, Any]]


class ProgressInput(Command):
    assignment_id: UUID


class TrackCreate(Command):
    key: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=300)


class LessonCreate(TrackCreate):
    track_id: UUID


class DraftSave(Command):
    expected_version: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=300)
    minutes: int = Field(ge=0, le=600)
    source: str = Field(default="", max_length=3000)
    blocks: list[dict[str, Any]] = Field(max_length=100)


class VersionCommand(Command):
    expected_version: int = Field(ge=0)


class AssessmentSave(Command):
    expected_version: int = Field(ge=0)
    title: str = Field(min_length=1, max_length=300)
    intro: str = Field(default="", max_length=3000)
    questions: list[dict[str, Any]] = Field(max_length=100)


class ReleasePublish(VersionCommand):
    assessment_draft_version: int | None = None
    lesson_draft_versions: dict[UUID, int]
    lesson_publication_revisions: dict[UUID, int]
    intro: str = Field(default="", max_length=3000)
    lesson_ids: list[UUID] = Field(min_length=1, max_length=100)
    reacknowledgement_required: bool = False
    changed_required_items: list[str] = Field(default_factory=list, max_length=100)


class ReleaseRollback(VersionCommand):
    release_id: UUID


class AssignmentCreate(Command):
    application_id: UUID | None = None
    release_id: UUID
    user_id: UUID | None = None
    registration_id: UUID | None = None


class LessonDraftView(BaseModel):
    id: UUID
    version: int
    title: str
    minutes: int
    source: str
    blocks: list[dict[str, Any]]
    status: str


class AssessmentDraftView(BaseModel):
    id: UUID
    version: int
    title: str
    intro: str
    questions: list[dict[str, Any]]
    status: str


class AuthorLessonView(BaseModel):
    id: UUID
    title: str
    track_id: UUID
    key: str
    current_version_id: UUID | None
    publication_revision: int
    archived: bool
    draft: LessonDraftView | None


class TrackView(BaseModel):
    id: UUID
    key: str
    title: str
    version: int
    archived: bool
    current_release_id: UUID | None
    lessons: list[AuthorLessonView]
    assessment: AssessmentDraftView | None
    releases: list[dict[str, Any]]


class TaskSubmit(VersionCommand):
    assignment_id: UUID
    answer_text: str = Field(min_length=1, max_length=12000)


class TaskSubmissionView(BaseModel):
    block_id: UUID
    answer_text: str
    version: int
