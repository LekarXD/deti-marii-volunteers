from datetime import date,datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator

class StrictModel(BaseModel):
    model_config=ConfigDict(extra='forbid')
class ProfileTagValue(StrictModel):
    kind:Literal['skill','interest','age_interest','place_interest']
    label:str=Field(min_length=1,max_length=120)
    level:Literal['learn','sure']='learn'
class ProfileUpdateCommand(StrictModel):
    expected_version:int=Field(ge=0)
    display_name:str=Field(min_length=1,max_length=200)
    about:str=Field(default='',max_length=8000)
    tags:list[ProfileTagValue]=Field(default_factory=list,max_length=80)
    lifecycle:Literal['active','paused']='active'
    paused_until:date|None=None
    photo_asset_id:UUID|None=None
    ai_about:bool=False
    ai_skills:bool=False
    ai_interests:bool=False
class ProfileContactView(BaseModel):
    type:str
    value:str
    verified_at:datetime
class ProfileRevisionView(BaseModel):
    id:UUID
    number:int
    source:str
    created_at:datetime
    snapshot:dict
class ProfileView(BaseModel):
    user_id:UUID
    version:int
    display_name:str
    about:str
    lifecycle:str
    paused_until:date|None
    photo_asset_id:UUID|None
    ai_about:bool
    ai_skills:bool
    ai_interests:bool
    tags:list[ProfileTagValue]
    contacts:list[ProfileContactView]
    revisions:list[ProfileRevisionView]
class ProfileConsentCommand(StrictModel):
    purpose:Literal['news','personal_data']
    granted:bool
    document_version:str=Field(min_length=1,max_length=32)
class ProfileConsentView(BaseModel):
    id:UUID
    purpose:str
    granted:bool
    document:str
    document_version:str
    source:str
    created_at:datetime
class ProfileVersionCommand(StrictModel):
    expected_version:int=Field(ge=0)
class SuggestionDecisionCommand(ProfileVersionCommand):
    decision:Literal['accept','reject','revert']
class ProfileSuggestionView(BaseModel):
    id:UUID
    base_version:int
    before:dict
    patch:dict
    source_refs:list[dict]
    producer:dict
    state:str
    applied_revision_id:UUID|None
    reverted_revision_id:UUID|None
    created_at:datetime
class ManualTimeCommand(StrictModel):
    title:str=Field(min_length=1,max_length=400)
    service_date:date
    requested_minutes:int=Field(ge=1,le=1440)
class ManualTimeReviewCommand(ProfileVersionCommand):
    decision:Literal['approved','rejected']
    approved_minutes:int=Field(ge=0,le=1440)
    reason:str=Field(min_length=3,max_length=4000)
    @model_validator(mode='after')
    def decision_minutes(self):
        if self.decision=='rejected' and self.approved_minutes:raise ValueError('Для отказа укажите 0 минут')
        if self.decision=='approved' and not self.approved_minutes:raise ValueError('Укажите подтверждённые минуты')
        return self
class ManualTimeReviewView(BaseModel):
    id:UUID
    version:int
    decision:str
    approved_minutes:int
    reason:str
    actor_id:str
    created_at:datetime
class ManualTimeView(BaseModel):
    id:UUID
    user_id:UUID
    display_name:str
    title:str
    service_date:date
    requested_minutes:int
    approved_minutes:int
    state:str
    version:int
    created_at:datetime
    reviews:list[ManualTimeReviewView]
class ServiceTimeEntryView(BaseModel):
    id:UUID
    service_date:date
    title:str
    delta_minutes:int
    source_kind:str
    source_id:UUID
    source_revision:int
    assignment_id:UUID|None
    reason:str
    created_at:datetime
class AchievementView(BaseModel):
    key:str
    title:str
    earned:bool
    progress:int
    target:int
    rule:str
class GratitudeView(BaseModel):
    id:UUID
    text:str
    author:str
    created_at:datetime
    basis_current:bool
class HoursView(BaseModel):
    total_minutes:int
    confirmed_assignments:int
    pending_minutes:int
    ledger_pending:int
    entries:list[ServiceTimeEntryView]
    manual_requests:list[ManualTimeView]
    achievements:list[AchievementView]
    gratitudes:list[GratitudeView]
class ProfileDocumentCommand(StrictModel):
    kind:Literal['certificate','letter']
    period_from:date
    period_to:date
    recipient:str=Field(min_length=1,max_length=240)
    @model_validator(mode='after')
    def period(self):
        if self.period_to<self.period_from:raise ValueError('Конец периода раньше начала')
        return self
class ProfileDocumentReviewCommand(ProfileVersionCommand):
    decision:Literal['approved','rejected']
    body:str=Field(default='',max_length=12000)
    public_response:str=Field(min_length=1,max_length=4000)
class ProfileDocumentView(BaseModel):
    display_name:str=''
    id:UUID
    user_id:UUID
    kind:str
    period_from:date
    period_to:date
    recipient:str
    body:str
    total_minutes:int
    state:str
    version:int
    asset_id:UUID|None
    public_response:str
    created_at:datetime
class GratitudeCommand(StrictModel):
    user_id:UUID
    basis_entry_id:UUID
    text:str=Field(min_length=3,max_length=4000)
class ProfileDataCommand(StrictModel):
    kind:Literal['export','deletion']
    reason:str=Field(default='',max_length=4000)
class ProfileDataReviewCommand(ProfileVersionCommand):
    decision:Literal['in_review','approved','rejected','completed']
    public_response:str=Field(min_length=1,max_length=4000)
    retention_note:str=Field(default='',max_length=4000)
    scheduled_for:date|None=None
class ProfileDataView(BaseModel):
    display_name:str=''
    id:UUID
    user_id:UUID
    kind:str
    state:str
    version:int
    reason:str
    public_response:str
    retention_note:str
    scheduled_for:date|None
    asset_id:UUID|None
    created_at:datetime
    updated_at:datetime

class RecognitionBasisView(BaseModel):
    entry_id:UUID
    user_id:UUID
    display_name:str
    title:str
    service_date:date
    confirmed_minutes:int

class StaffDocumentCommand(ProfileDocumentCommand):
    user_id:UUID
    basis_entry_id:UUID
