from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator
import unicodedata

ApprovalPolicy = Literal['coordinator', 'self_confirmation']
OpportunityState = Literal['draft', 'published', 'paused', 'closed']


def normalized_title(value: str) -> str:
    return ' '.join(unicodedata.normalize('NFKC', value).split()).casefold()


class PreparationRequirement(BaseModel):
    model_config = ConfigDict(extra='forbid')
    key: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=500)
    level: Literal['recommended', 'mandatory'] = 'recommended'

    @field_validator('key', 'title')
    @classmethod
    def not_blank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Укажите пункт подготовки.')
        return value


class RoleCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    task: str = Field(default='', max_length=20000)
    preparation_defaults: list[PreparationRequirement] = Field(default_factory=list, max_length=100)
    approval_policy: ApprovalPolicy = 'coordinator'

    @field_validator('preparation_defaults')
    @classmethod
    def distinct_requirement_keys(cls, value):
        if len({r.key for r in value}) != len(value):
            raise ValueError('Пункты подготовки не должны повторяться.')
        return value

    @field_validator('title')
    @classmethod
    def valid_title(cls, value):
        value = ' '.join(value.split())
        if not normalized_title(value) or len(normalized_title(value)) > 300:
            raise ValueError('Введите название роли.')
        return value


class RoleUpdate(RoleCreate):
    expected_version: int = Field(gt=0)


class VersionCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_version: int = Field(gt=0)


class RoleView(RoleCreate):
    id: UUID
    version: int
    archived_at: datetime | None
    allowed_actions: list[str]


class OpportunityCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    role_ids: list[UUID] = Field(min_length=1, max_length=30)
    program: str = Field(default='', max_length=200)
    audience: str = Field(default='', max_length=20000)
    task: str | None = Field(default=None, max_length=20000)
    conditions: str = Field(default='', max_length=20000)
    regularity: Literal['regular', 'periodic', 'once', 'tasks'] = 'once'
    location: str = Field(default='', max_length=500)
    schedule: str = Field(default='', max_length=500)
    format: Literal['onsite', 'online', 'hybrid'] = 'onsite'
    preparation_requirements: list[PreparationRequirement] | None = Field(default=None, max_length=100)
    approval_policy: ApprovalPolicy | None = None

    @field_validator('title')
    @classmethod
    def valid_title(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('Введите название возможности.')
        return value

    @field_validator('preparation_requirements')
    @classmethod
    def distinct_requirement_keys(cls, value):
        if value is not None and len({r.key for r in value}) != len(value):
            raise ValueError('Пункты подготовки не должны повторяться.')
        return value

    @field_validator('role_ids')
    @classmethod
    def distinct_roles(cls, value):
        if len(set(value)) != len(value):
            raise ValueError('Роли не должны повторяться.')
        return value


class OpportunityUpdate(OpportunityCreate):
    expected_version: int = Field(gt=0)


class MatchExplanation(BaseModel):
    algorithm_version: Literal['rules-v1'] = 'rules-v1'
    reasons: list[str]
    missing_data: list[str]
    constraints: list[str]


class OpportunityView(OpportunityCreate):
    id: UUID
    version: int
    state: OpportunityState
    task: str
    preparation_requirements: list[PreparationRequirement]
    approval_policy: ApprovalPolicy
    allowed_actions: list[str]
    matching: MatchExplanation


class RolePage(BaseModel):
    items: list[RoleView]
    next_cursor: UUID | None = None


class OpportunityPage(BaseModel):
    items: list[OpportunityView]
    next_cursor: UUID | None = None


class RoleUsage(BaseModel):
    opportunity_count: int
    opportunities: list[dict]
    history_preserved: bool = True


class RevisionView(BaseModel):
    version: int
    snapshot: dict
    created_at: datetime
