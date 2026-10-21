from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class Command(BaseModel):
    model_config=ConfigDict(extra="forbid")

class CrmVersionCommand(Command):
    expected_version:int=Field(ge=1)

class CreateVolunteerCommand(Command):
    application_id:UUID

class AgreementCommand(CrmVersionCommand):
    text:str=Field(min_length=1,max_length=8000)
    role_context:str=Field(default="",max_length=400)
    valid_until:date|None=None
    relationship_state:Literal['contacted','awaiting_reply','ready','active','paused','unavailable','unreachable','closed']|None=None

class ContactCommand(CrmVersionCommand):
    kind:Literal['phone','telegram','meeting','email','other']
    text:str=Field(min_length=1,max_length=8000)
    direction:Literal['incoming','outgoing','recorded']='recorded'
    occurred_at:datetime|None=None

class AvailabilityWindowInput(Command):
    weekday:int=Field(ge=0,le=6)
    start_minute:int=Field(ge=0,lt=1440)
    end_minute:int=Field(gt=0,le=1440)

class AvailabilityInput(Command):
    summary:str=Field(min_length=1,max_length=4000)
    timezone:str=Field(default='Europe/Moscow',max_length=80)
    preferred_channel:Literal['telegram','phone','email','max','whatsapp','other']='phone'
    windows:list[AvailabilityWindowInput]=Field(default_factory=list,max_length=28)

class AvailabilityCommand(CrmVersionCommand,AvailabilityInput):
    pass

class VerificationCommand(CrmVersionCommand):
    valid_until:date
    source:str=Field(min_length=1,max_length=80)

class CrmPreferenceCommand(CrmVersionCommand):
    no_contact:bool
    reason:str=Field(min_length=1,max_length=4000)
    renewed_consent_confirmed:bool=False

class CrmReviewCommand(CrmVersionCommand):
    outcome:Literal['unverified','contacted','awaiting_reply','ready','paused','unavailable','unreachable']
    note:str=Field(min_length=1,max_length=8000)
    no_contact:bool=False
    availability:AvailabilityInput|None=None
    valid_until:date|None=None
    agreement_text:str=Field(default='',max_length=8000)

class TaskCreateCommand(CrmVersionCommand):
    title:str=Field(min_length=1,max_length=400)
    due_on:date
    assigned_user_id:UUID

class TaskUpdateCommand(CrmVersionCommand):
    state:Literal['open','done','cancelled']|None=None
    title:str|None=Field(default=None,min_length=1,max_length=400)
    due_on:date|None=None
    assigned_user_id:UUID|None=None
    reason:str=Field(min_length=1,max_length=4000)

class MergeCommand(CrmVersionCommand):
    target_id:UUID
    target_expected_version:int=Field(ge=1)
    reason:str=Field(min_length=1,max_length=4000)

class ImportMappingCommand(CrmVersionCommand):
    mapping:dict[str,str]
    source_system:str=Field(min_length=1,max_length=80)

class ImportRowResolutionCommand(CrmVersionCommand):
    decision:Literal['create','link','skip']
    volunteer_id:UUID|None=None
    reason:str=Field(min_length=1,max_length=4000)

class AgreementView(BaseModel):
    id:UUID
    text:str
    role_context:str
    valid_until:date|None
    created_at:datetime

class ContactEventView(BaseModel):
    id:UUID
    kind:str
    direction:str
    text:str
    occurred_at:datetime

class AvailabilityView(BaseModel):
    id:UUID
    number:int
    summary:str
    timezone:str
    preferred_channel:str
    windows:list[AvailabilityWindowInput]
    verified_at:datetime|None
    valid_until:date|None
    verified:bool

class FollowUpTaskView(BaseModel):
    id:UUID
    volunteer_id:UUID
    application_id:UUID|None
    assigned_user_id:UUID
    due_on:date
    title:str
    state:str
    version:int
    source_type:str
    source_id:UUID
    source_revision:int
    completed_at:datetime|None

class ReserveReviewView(BaseModel):
    id:UUID
    outcome:str
    note:str
    no_contact:bool
    created_at:datetime

class CrmVolunteerSummary(BaseModel):
    id:UUID
    application_id:UUID|None
    display_name:str
    contacts:dict[str,str]
    context:str
    relationship_state:str
    no_contact:bool
    version:int
    merged_into_id:UUID|None
    can_invite:bool
    blocked_reasons:list[str]
    availability:AvailabilityView|None
    next_task:FollowUpTaskView|None

class CrmReflectionReviewView(BaseModel):
    id:UUID
    revision:int
    decision:str
    public_message:str
    next_date:date|None
    assigned_staff_name:str
    created_at:datetime

class CrmReflectionView(BaseModel):
    id:UUID
    assignment_id:UUID
    text:str
    unexpected:str
    help:str
    continuation:str
    submitted_at:datetime
    can_review:bool
    review:CrmReflectionReviewView|None

class CrmVolunteerView(CrmVolunteerSummary):
    latest_reflection:CrmReflectionView|None=None
    agreements:list[AgreementView]
    contact_events:list[ContactEventView]
    follow_up_tasks:list[FollowUpTaskView]
    reviews:list[ReserveReviewView]
    merged_record_ids:list[UUID]
    import_provenance:list[dict[str,Any]]

class CrmVolunteerListView(BaseModel):
    items:list[CrmVolunteerSummary]
    total:int
    offset:int
    limit:int

class ImportRowView(BaseModel):
    id:UUID
    line_number:int
    raw:dict[str,Any]
    normalized:dict[str,Any]
    decision:str
    volunteer_id:UUID|None
    errors:list[str]
    resolution_reason:str

class ImportBatchSummary(BaseModel):
    id:UUID
    checksum:str
    filename:str
    columns:list[str]
    mapping:dict[str,str]
    source_system:str
    state:str
    version:int
    created_at:datetime
    applied_at:datetime|None
    counts:dict[str,int]

class ImportBatchView(ImportBatchSummary):
    rows:list[ImportRowView]

class OwnAvailabilityView(BaseModel):
    volunteer_id:UUID|None
    version:int
    availability:AvailabilityView|None
    no_contact:bool

class SelfAvailabilityCommand(AvailabilityInput):
    expected_version:int=Field(ge=0)

class StaffOptionView(BaseModel):
    id:UUID
    display_name:str

class CrmApplicationOptionView(BaseModel):
    application_id:UUID
    label:str

class FirstVisitOutcomeCommand(CrmVersionCommand):
    outcome:Literal['next_activity','preparation','different_role','pause','finish']
    note:str=Field(min_length=1,max_length=8000)
    due_on:date|None=None
    assigned_user_id:UUID|None=None
