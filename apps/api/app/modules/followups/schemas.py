from datetime import date,datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field,model_validator

class FollowupCommand(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=0)

class ChecklistCommand(FollowupCommand):
    checklist_version:int=1
    checked_keys:list[Literal['group','contact','clothes']]=Field(default_factory=list,max_length=3)
    @model_validator(mode='after')
    def unique_keys(self):
        if len(set(self.checked_keys))!=len(self.checked_keys):raise ValueError('Пункты не должны повторяться')
        return self

class ChecklistItem(BaseModel):
    key:str
    title:str
    checked:bool
    href:str|None=None

class PreparationContact(BaseModel):
    display_name:str
    role:str

class AssignmentQuestionInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['question','alternate_date']='question'
    text:str=Field(min_length=1,max_length=6000)
    restricted:bool=False

class AssignmentQuestionView(BaseModel):
    id:UUID
    kind:str
    text:str
    restricted:bool
    public_answer:str
    created_at:datetime
    answered_at:datetime|None
    version:int

class AssignmentPreparationView(BaseModel):
    assignment_id:UUID
    assignment_version:int
    status:str
    title:str
    starts_at:datetime
    ends_at:datetime
    timezone:str
    location:str
    role_title:str
    tasks:str
    contacts:list[PreparationContact]
    checklist_version:int
    version:int
    checklist:list[ChecklistItem]
    questions:list[AssignmentQuestionView]
    group_briefing_available:bool
    allowed_actions:list[str]

class ReflectionDraftCommand(FollowupCommand):
    mood:Literal['great','good','ok','hard','awful']|None=None
    text:str=Field(default='',max_length=12000)
    unexpected:str=Field(default='',max_length=6000)
    help:Literal['later','yes','no']='later'
    help_text:str=Field(default='',max_length=6000)
    continuation:Literal['discuss','yes','other','pause','finish']='discuss'
    restricted:bool=False

class ReflectionReviewCommand(FollowupCommand):
    decision:Literal['next_date','other_role','discussion','pause','finish']
    public_message:str=Field(min_length=1,max_length=6000)
    assigned_user_id:UUID
    next_date:date|None=None
    internal_note:str=Field(default='',max_length=12000)
    @model_validator(mode='after')
    def follow_up_date(self):
        if self.decision in ('next_date','other_role','discussion') and self.next_date is None:raise ValueError('Укажите дату следующего действия')
        if not self.public_message.strip():raise ValueError('Напишите договорённость для волонтёра')
        return self

class PublicReflectionReview(BaseModel):
    id:UUID
    revision:int
    decision:str
    public_message:str
    next_date:date|None
    assigned_staff_name:str
    created_at:datetime

class OwnReflectionView(BaseModel):
    id:UUID|None
    assignment_id:UUID
    title:str
    version:int
    mood:str|None
    text:str
    unexpected:str
    help:str
    help_text:str
    continuation:str
    restricted:bool
    submitted_at:datetime|None
    can_submit:bool
    follow_up_registered:bool
    review:PublicReflectionReview|None
    voice_available:bool=False
    voice_unavailable_reason:str='Голосовой ввод пока недоступен. Можно написать текст.'

class StaffReflectionView(OwnReflectionView):
    user_id:UUID
    display_name:str
    signal_id:UUID|None

class ReflectionStaffPage(BaseModel):
    items:list[StaffReflectionView]

class ReflectionPrivateNoteView(BaseModel):
    review_id:UUID
    text:str
    author_id:UUID
    created_at:datetime

class SignalEventView(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    revision:int
    action:str
    reason:str
    author_id:str
    created_at:datetime

class SupportSignalView(BaseModel):
    id:UUID
    version:int
    reflection_id:UUID|None
    question_id:UUID|None
    subject_user_id:UUID
    display_name:str
    group_id:UUID|None
    restricted:bool
    priority:str
    state:str
    assigned_user_id:UUID|None
    assigned_staff_name:str|None
    follow_up_task_id:UUID|None
    summary:str
    details:str
    public_answer:str|None
    history:list[SignalEventView]

class SupportSignalPage(BaseModel):
    items:list[SupportSignalView]

class SignalActionCommand(FollowupCommand):
    assigned_user_id:UUID|None=None
    priority:Literal['normal','high','urgent']|None=None
    reason:str=Field(min_length=1,max_length=6000)

class QuestionAnswerCommand(FollowupCommand):
    public_answer:str=Field(min_length=1,max_length=6000)

class FollowupStaffOption(BaseModel):
    id:UUID
    display_name:str
    restricted_eligible:bool

class FollowupStaffOptions(BaseModel):
    items:list[FollowupStaffOption]
