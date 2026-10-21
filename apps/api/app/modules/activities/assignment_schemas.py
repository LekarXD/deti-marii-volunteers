from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator
from .schemas import VersionCommand

class ParticipationResponseCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    message:str=Field(default='',max_length=2000)

class ParticipationDecision(VersionCommand):
    reason:str=Field(min_length=1,max_length=5000)

class ParticipationResponseView(BaseModel):
    id:UUID
    opportunity_id:UUID
    opportunity_title:str
    user_id:UUID
    display_name:str
    state:str
    decision_reason:str
    version:int
    allowed_actions:list[str]
    history:list[dict]

class ParticipationResponsePage(BaseModel):
    items:list[ParticipationResponseView]
    next_cursor:UUID|None=None

class AssignmentInvite(BaseModel):
    model_config=ConfigDict(extra='forbid')
    user_id:UUID
    expected_version:int=Field(gt=0)
    expected_assignment_version:int|None=Field(default=None,gt=0)

class AssignmentRequirementDecision(ParticipationDecision):
    requirement_key:str=Field(min_length=1,max_length=100)
    state:Literal['fulfilled','waived','pending']

class AssignmentReadinessItem(BaseModel):
    key:str
    title:str
    level:Literal['mandatory','recommended']
    state:Literal['fulfilled','waived','pending']
    evidence:dict|None=None

class AssignmentParticipationView(BaseModel):
    id:UUID
    version:int
    user_id:UUID
    display_name:str
    occurrence_id:UUID
    staffing_need_id:UUID
    title:str
    role_title:str
    starts_at:datetime
    ends_at:datetime
    timezone:str
    location:str
    status:str
    approved_at:datetime|None
    confirmed_at:datetime|None
    conditions_version:int
    readiness:list[AssignmentReadinessItem]
    allowed_actions:list[str]
    history:list[dict]
    attendance:dict|None=None

class AssignmentParticipationPage(BaseModel):
    items:list[AssignmentParticipationView]
    next_cursor:UUID|None=None

class AssignmentSuggestion(BaseModel):
    user_id:UUID
    display_name:str
    reasons:list[str]
    missing_data:list[str]

class AttendanceCommand(VersionCommand):
    outcome:Literal['attended','absent']
    minutes:int=Field(ge=0,le=10080)
    reason:str=Field(min_length=1,max_length=5000)
    @model_validator(mode='after')
    def no_show_zero(self):
        if self.outcome=='absent' and self.minutes!=0:raise ValueError('Неучастие не начисляет минуты.')
        return self
