from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,Field
from .schemas import ApprovalPolicy,PreparationRequirement,VersionCommand


class SignUpCommand(VersionCommand):
    message:str=Field(default='',max_length=2000)


class ReserveView(BaseModel):
    id:UUID
    version:int
    occurrence_id:UUID
    staffing_need_id:UUID
    state:Literal['waiting','offered','closed']
    position:int|None=None
    offered_assignment_id:UUID|None=None
    queued_at:datetime
    allowed_actions:list[str]


class VolunteerEventNeed(BaseModel):
    """One role on the occurrence. Counts only, never other volunteers' names."""
    id:UUID
    version:int
    role_id:UUID
    role_title:str
    task:str
    required:int
    confirmed:int
    missing:int
    approval_policy:ApprovalPolicy
    preparation_requirements:list[PreparationRequirement]
    allowed_actions:list[Literal['sign-up','reserve']]


class VolunteerEventAssignment(BaseModel):
    id:UUID
    version:int
    staffing_need_id:UUID
    status:str
    origin:str
    approved_at:datetime|None


class VolunteerEventCard(BaseModel):
    occurrence_id:UUID
    series_id:UUID
    title:str
    program:str
    kind:str
    format:str
    location:str
    audience:str
    status:str
    starts_at:datetime
    ends_at:datetime
    timezone:str
    needs:list[VolunteerEventNeed]
    best_need_id:UUID|None
    reasons:list[str]
    full:bool
    conflict:bool
    my_assignment:VolunteerEventAssignment|None=None
    my_reserve:ReserveView|None=None


class VolunteerEventFeed(BaseModel):
    algorithm_version:str
    can_sign_up:bool
    locked_reason:str|None=None
    locked_message:str|None=None
    items:list[VolunteerEventCard]


class VolunteerEventDate(BaseModel):
    occurrence_id:UUID
    starts_at:datetime
    ends_at:datetime
    full:bool
    mine:bool


class VolunteerEventDetail(VolunteerEventCard):
    algorithm_version:str
    can_sign_up:bool
    locked_reason:str|None=None
    locked_message:str|None=None
    other_dates:list[VolunteerEventDate]


class MatchingOptionsView(BaseModel):
    directions:list[str]
    skills:list[str]
