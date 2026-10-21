from datetime import date, datetime, time
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from .schemas import ApprovalPolicy, PreparationRequirement, VersionCommand


class RecurrenceRule(BaseModel):
    model_config=ConfigDict(extra='forbid')
    frequency:Literal['once','weekly','biweekly','monthly']='once'
    weekdays:list[int]=Field(default_factory=list,max_length=7)
    until:date|None=None
    exceptions:list[date]=Field(default_factory=list,max_length=500)
    @field_validator('weekdays')
    @classmethod
    def days(cls,value):
        if len(set(value))!=len(value) or any(day<0 or day>6 for day in value):raise ValueError('Дни недели: 0–6 без повторов.')
        return sorted(value)
    @model_validator(mode='after')
    def weekly_days(self):
        if self.frequency in ('weekly','biweekly') and not self.weekdays:raise ValueError('Выберите дни недели.')
        return self


class StaffingNeedInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    role_id:UUID
    capacity_required:int=Field(ge=0,le=1000)
    preparation_requirements:list[PreparationRequirement]|None=None
    approval_policy:ApprovalPolicy|None=None


class EventSeriesCreate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    title:str=Field(min_length=1,max_length=200)
    program:str=Field(default='',max_length=200)
    group_id:UUID|None=None
    start_date:date
    start_time:time
    timezone:str='Europe/Moscow'
    duration_minutes:int=Field(gt=0,le=10080)
    recurrence:RecurrenceRule=Field(default_factory=RecurrenceRule)
    kind:Literal['activity','workshop','event','trip']='activity'
    format:Literal['onsite','online','hybrid']='onsite'
    location:str=Field(min_length=1,max_length=500)
    audience:str=Field(default='',max_length=20000)
    staffing_needs:list[StaffingNeedInput]=Field(default_factory=list,max_length=30)
    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls,value):
        try:ZoneInfo(value)
        except ZoneInfoNotFoundError:raise ValueError('Неизвестный часовой пояс.')
        return value
    @field_validator('title','location')
    @classmethod
    def not_blank(cls,value):
        if not value.strip():raise ValueError('Заполните поле.')
        return value.strip()
    @field_validator('start_time')
    @classmethod
    def local_time(cls,value):
        if value.tzinfo or value.second or value.microsecond:raise ValueError('Укажите локальное время с точностью до минуты.')
        return value
    @model_validator(mode='after')
    def valid_rule(self):
        if self.recurrence.until and self.recurrence.until<self.start_date:raise ValueError('Последняя дата раньше первой.')
        if len({need.role_id for need in self.staffing_needs})!=len(self.staffing_needs):raise ValueError('Одна потребность на роль в занятии.')
        return self


class EventSeriesUpdate(EventSeriesCreate):
    expected_version:int=Field(gt=0)


class EventSeriesApply(EventSeriesUpdate):
    preview_hash:str=Field(min_length=64,max_length=64)


class EventSeriesView(EventSeriesCreate):
    id:UUID
    version:int
    state:Literal['active','cancelled']
    allowed_actions:list[str]


class StaffingNeedView(BaseModel):
    id:UUID
    role_id:UUID
    role_version_id:UUID
    role_title:str
    version:int
    required:int
    invited:int
    confirmed:int
    missing:int
    preparation_requirements:list[PreparationRequirement]
    approval_policy:ApprovalPolicy


class EventOccurrenceView(BaseModel):
    id:UUID
    version:int
    series_id:UUID
    series_version:int
    origin_local_date:date
    origin_local_time:time
    starts_at:datetime
    ends_at:datetime
    timezone:str
    group_id:UUID|None
    title:str
    program:str
    kind:str
    format:str
    location:str
    audience:str
    status:Literal['scheduled','cancelled','completed']
    has_override:bool
    staffing_needs:list[StaffingNeedView]
    allowed_actions:list[str]


class EventOccurrenceUpdate(VersionCommand):
    title:str=Field(min_length=1,max_length=200)
    group_id:UUID|None=None
    starts_at:datetime
    ends_at:datetime
    location:str=Field(min_length=1,max_length=500)
    @model_validator(mode='after')
    def interval(self):
        if not self.starts_at.tzinfo or not self.ends_at.tzinfo or self.ends_at<=self.starts_at:raise ValueError('Укажите время окончания после начала с часовым поясом.')
        return self


class StaffingNeedsUpdate(VersionCommand):
    staffing_needs:list[StaffingNeedInput]=Field(max_length=30)


class EventOccurrencePage(BaseModel):
    items:list[EventOccurrenceView]
    next_cursor:UUID|None=None
    expansion_pending:bool=False


class SeriesChangePreview(BaseModel):
    series_id:UUID
    expected_version:int
    preview_hash:str
    affected_occurrence_ids:list[UUID]
    retained_override_ids:list[UUID]
    conflicts:list[dict]
    needs_reconfirmation_ids:list[UUID]
    can_apply:bool
