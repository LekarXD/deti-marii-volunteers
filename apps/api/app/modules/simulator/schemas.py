from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SimulatorCriterion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    guidance: str = Field(min_length=1, max_length=5000)
    critical: bool = False


class SimulatorExampleTurn(BaseModel):
    model_config = ConfigDict(extra='forbid')
    speaker: Literal['character', 'volunteer']
    content: str = Field(min_length=1, max_length=4000)


class SimulatorEvaluationCase(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    turns: list[SimulatorExampleTurn] = Field(min_length=2, max_length=30)
    expected_scores: dict[str, Literal[0, 1, 2]]


class SimulatorScenarioDraft(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    character_name: str = Field(default='', max_length=100)
    character_profile: str = Field(default='', max_length=5000)
    situation: str = Field(default='', max_length=5000)
    first_turn: str = Field(default='', max_length=5000)
    warning: str = Field(default='', max_length=2000)
    methods: list[str] = Field(default_factory=list, max_length=30)
    hints: list[str] = Field(default_factory=list, max_length=30)
    criteria: list[SimulatorCriterion] = Field(default_factory=list, max_length=20)
    evaluation_cases: list[SimulatorEvaluationCase] = Field(default_factory=list, max_length=20)

    @field_validator('title')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('Заполните поле.')
        return value.strip()

    @model_validator(mode='after')
    def unique_contracts(self):
        keys = {criterion.key for criterion in self.criteria}
        if len(keys) != len(self.criteria):
            raise ValueError('Ключи критериев не должны повторяться.')
        if len({case.key for case in self.evaluation_cases}) != len(self.evaluation_cases):
            raise ValueError('Ключи примеров не должны повторяться.')
        for case in self.evaluation_cases:
            if set(case.expected_scores) - keys:
                raise ValueError('Эталонная оценка ссылается на неизвестный критерий.')
            if not any(turn.speaker == 'volunteer' for turn in case.turns):
                raise ValueError('В примере нужен ответ волонтёра.')
        return self


class SimulatorVersionCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(gt=0)


class SimulatorDraftUpdate(SimulatorScenarioDraft):
    expected_version: int = Field(gt=0)


class SimulatorReviewCommand(SimulatorVersionCommand):
    decision: Literal['approved', 'changes_requested']
    reason: str = Field(min_length=1, max_length=5000)


class SimulatorPublishCommand(SimulatorVersionCommand):
    review_id: UUID
    test_run_id: UUID


class SimulatorScenarioStaffView(BaseModel):
    id: UUID
    version: int
    draft: SimulatorScenarioDraft
    publication_id: UUID | None
    archived_at: datetime | None
    reviews: list[dict]
    test_runs: list[dict]
    allowed_actions: list[str]
    published_version: int | None = None
    published_draft_version: int | None = None
    finished_count: int = 0


class SimulatorScenarioPublicView(BaseModel):
    id: UUID
    publication_id: UUID
    version: int
    title: str
    character_name: str
    character_profile: str
    situation: str
    warning: str
    methods: list[str]
    criteria: list[SimulatorCriterion]
    allowed_actions: list[str]
    provider_state: str


class SimulatorScenarioPage(BaseModel):
    items: list[SimulatorScenarioPublicView]
    next_cursor: UUID | None = None


class SimulatorStaffScenarioPage(BaseModel):
    items: list[SimulatorScenarioStaffView]
    next_cursor: UUID | None = None


class SimulatorTurnView(BaseModel):
    id: UUID
    ordinal: int
    speaker: str
    content: str
    source: str
    created_at: datetime


class SimulatorEvidence(BaseModel):
    model_config = ConfigDict(extra='forbid')
    turn_id: UUID
    quote: str = Field(min_length=1, max_length=1500)


class SimulatorCriterionAssessment(BaseModel):
    model_config = ConfigDict(extra='forbid')
    criterion_key: str = Field(min_length=1, max_length=100)
    score: Literal[0, 1, 2]
    explanation: str = Field(min_length=1, max_length=2000)
    evidence: list[SimulatorEvidence] = Field(default_factory=list, max_length=5)
    suggestion: str = Field(default='', max_length=2000)

    @model_validator(mode='after')
    def positive_requires_evidence(self):
        if self.score > 0 and not self.evidence:
            raise ValueError('Положительная оценка требует фрагмента ответа волонтёра.')
        return self


class SimulatorAssessmentOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    summary: str = Field(min_length=1, max_length=3000)
    criteria: list[SimulatorCriterionAssessment] = Field(min_length=1, max_length=20)


class SimulatorCharacterOutput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    content: str = Field(min_length=1, max_length=5000)


class SimulatorAppealView(BaseModel):
    id: UUID
    version: int
    state: str
    text: str
    response: str | None = None
    corrected_result: SimulatorAssessmentOutput | None = None


class SimulatorEvaluationView(BaseModel):
    id: UUID
    version: int
    state: str
    rubric_version_id: UUID
    prompt_version: str
    model: str
    result: SimulatorAssessmentOutput | None
    appeal: SimulatorAppealView | None = None


class SimulatorSessionView(BaseModel):
    id: UUID
    version: int
    state: str
    scenario: SimulatorScenarioPublicView
    rubric_version_id: UUID
    turns: list[SimulatorTurnView]
    evaluation: SimulatorEvaluationView | None
    provider_state: str | None
    provider_error: str | None
    support_requests: list[dict]
    allowed_actions: list[str]


class SimulatorSessionStart(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario_id: UUID
    publication_id: UUID | None = None
    parent_session_id: UUID | None = None


class SimulatorTurnCommand(SimulatorVersionCommand):
    content: str = Field(min_length=1, max_length=5000)

    @field_validator('content')
    @classmethod
    def not_blank(cls, value):
        if not value.strip():
            raise ValueError('Напишите ответ.')
        return value.strip()


class SimulatorAppealCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=5000)


class SimulatorHumanReview(SimulatorVersionCommand):
    response: str = Field(min_length=1, max_length=5000)
    corrected_result: SimulatorAssessmentOutput | None = None


class SimulatorTestRunView(BaseModel):
    id: UUID
    state: str
    draft_version: int
    dataset_hash: str
    limits: dict
    cases: list[dict]
    completed_at: datetime | None


class SimulatorSupportCommand(SimulatorVersionCommand):
    text: str = Field(min_length=1, max_length=5000)


class SimulatorExampleCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    example_index: int = Field(ge=0, le=5)


class SimulatorSimpleResult(BaseModel):
    id: UUID
    version: int
    state: str
    response: str | None = None


class SimulatorSessionPage(BaseModel):
    items: list[SimulatorSessionView]
    next_cursor: UUID | None = None


class SimulatorReviewQueueItem(BaseModel):
    id: UUID
    version: int
    state: str
    text: str
    title: str
    session_id: UUID
    response: str | None = None
    created_at: datetime | None = None
    author_name: str | None = None
    critical: bool = False


class SimulatorAppealDetail(BaseModel):
    appeal: SimulatorReviewQueueItem
    attempt: SimulatorSessionView
