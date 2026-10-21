from datetime import date,datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator
class ReportingCommand(BaseModel):
    model_config=ConfigDict(extra='forbid')
class ReportScopeCommand(ReportingCommand):
    scope_type:Literal['foundation','group']='foundation'
    scope_id:UUID|None=None
    @model_validator(mode='after')
    def target(self):
        if (self.scope_type=='group')!=(self.scope_id is not None):raise ValueError('Укажите группу для области группы')
        return self
class ReportPeriodCommand(ReportScopeCommand):
    period_from:date
    period_to:date
    @model_validator(mode='after')
    def dates(self):
        if self.period_to<self.period_from:raise ValueError('Конец периода раньше начала')
        if (self.period_to-self.period_from).days>1826:raise ValueError('Выберите период не длиннее пяти лет')
        return self
class ReportCreateCommand(ReportPeriodCommand):
    kind:Literal['grant','weekly']='grant'
    title:str=Field(min_length=1,max_length=300)
class ReportVersionCommand(ReportingCommand):
    expected_version:int=Field(ge=1)
class ReportSectionCommand(ReportVersionCommand):
    text:str=Field(max_length=16000)
class ReportSectionDecisionCommand(ReportVersionCommand):
    decision:Literal['confirm','reopen']
class ReportExportCommand(ReportVersionCommand):
    format:Literal['csv','pdf','docx']
class ReportScopeView(BaseModel):
    scope_type:str
    scope_id:UUID|None
    label:str
    can_write:bool
    can_export:bool
class ReportMetricView(BaseModel):
    key:str
    label:str
    value:float|int|None
    unit:str
    definition:str
    status:Literal['available','empty','unavailable']
    reason:str=''
    numerator:int|None=None
    denominator:int|None=None
class ReportFactView(BaseModel):
    id:UUID
    user_id:UUID
    display_name:str
    service_date:date
    title:str
    delta_minutes:int
    assignment_id:UUID|None
    occurrence_id:UUID|None
    group_id:UUID|None
    group_title:str|None
    source_kind:str
    source_id:UUID
    source_revision:int
class ReportMetricsView(BaseModel):
    definitions_version:str
    period_from:date
    period_to:date
    scope:ReportScopeView
    metrics:list[ReportMetricView]
    rows:list[ReportFactView]
    source_refs:list[dict]
    source_hash:str
    generated_at:datetime
    timezone:str='Europe/Moscow'
class ReportSectionView(BaseModel):
    key:str
    title:str
    text:str
    confirmed:bool
    source:str
class ReportRevisionView(BaseModel):
    id:UUID
    version:int
    state:str
    reason:str
    created_at:datetime
class ReportView(BaseModel):
    id:UUID
    title:str
    kind:str
    state:str
    version:int
    scope:ReportScopeView
    period_from:date
    period_to:date
    metrics:ReportMetricsView
    sections:list[ReportSectionView]
    revisions:list[ReportRevisionView]
    created_at:datetime
    updated_at:datetime
class ReportSummaryView(BaseModel):
    id:UUID
    title:str
    kind:str
    state:str
    version:int
    scope:ReportScopeView
    period_from:date
    period_to:date
    updated_at:datetime
class ReportExportView(BaseModel):
    id:UUID
    report_id:UUID
    revision_id:UUID
    format:str
    state:str
    asset_id:UUID|None
    created_at:datetime
class DobroMappingColumn(BaseModel):
    internal_key:str
    label:str
    external_field:str|None=None
class DobroPreviewView(BaseModel):
    state:Literal['unavailable']='unavailable'
    reason:str
    mapping:list[DobroMappingColumn]
    rows:list[ReportFactView]
    total_minutes:int
    upload_available:Literal[False]=False
class ReportDigestCommand(ReportScopeCommand):
    expected_version:int=Field(ge=0)
    enabled:bool
    recipient_ids:list[UUID]=Field(max_length=50)
    weekday:int=Field(default=0,ge=0,le=6)
    minute_of_day:int=Field(default=540,ge=0,le=1439)
    timezone:str=Field(default='Europe/Moscow',min_length=1,max_length=100)
class ReportDigestRecipientView(BaseModel):
    user_id:UUID
    display_name:str
class ReportDigestDeliveryView(BaseModel):
    id:UUID
    recipient_id:UUID
    period_from:date
    period_to:date
    state:str
    reason:str
    created_at:datetime
class ReportDigestView(BaseModel):
    id:UUID|None
    version:int
    enabled:bool
    scope:ReportScopeView
    recipients:list[ReportDigestRecipientView]
    weekday:int
    minute_of_day:int
    timezone:str
    state:str
    next_run_at:datetime|None
    last_run_at:datetime|None
    deliveries:list[ReportDigestDeliveryView]
