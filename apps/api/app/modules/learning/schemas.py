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
    assignment_id: UUID
    assessment_version_id: UUID
    state: str
    questions: list[QuestionView]
    answers: list[FeedbackView]
    score: int | None
    total: int


class LessonSummary(BaseModel):
    id: UUID
    lesson_id: UUID
    key: str
    title: str
    minutes: int
    completed: bool


class AssignmentView(BaseModel):
    id: UUID
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
    title: str
    minutes: int
    blocks: list[dict[str, Any]]


class ProgressInput(Command):
    assignment_id: UUID
