from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
class Command(BaseModel):
    model_config=ConfigDict(extra='forbid')
class SourceCreate(Command):
    title:str=Field(min_length=1,max_length=300)
    body:str=Field(default='',max_length=200000)
    visibility:Literal['all','staff']='all'
    asset_id:UUID|None=None
    lesson_version_id:UUID|None=None
class SourceSave(SourceCreate):
    expected_version:int=Field(ge=1)
class VersionInput(Command):
    expected_version:int=Field(ge=1)
class EmptyInput(Command):
    pass
class MentorInput(Command):
    question:str=Field(min_length=2,max_length=3000)
class AnswerInput(Command):
    body:str=Field(min_length=1,max_length=12000)
    expected_version:int=Field(ge=0)
    citation_ids:list[UUID]=Field(default_factory=list,max_length=8)
class SourceView(BaseModel):
    id:UUID
    title:str
    kind:str
    body:str
    visibility:str
    version:int
    reviewed_version:int|None
    current_version_id:UUID|None
    archived:bool
    index_state:str
    index_error:str|None
    ingest_state:str|None
    ingest_error:str|None
    can_edit:bool
class FragmentView(BaseModel):
    id:UUID
    source_id:UUID
    source_version_id:UUID
    title:str
    text:str
class QuestionView(BaseModel):
    id:UUID
    report_evidence:dict[str,Any]|None
    text:str
    kind:str
    state:str
    version:int
    answer:dict[str,Any]|None
class MentorView(BaseModel):
    id:UUID
    question:str
    state:str
    answer:str|None
    fragments:list[FragmentView]
    citations:list[FragmentView]
    question_id:UUID|None
    error_code:str|None
    model:str|None
    prompt_version:str|None
    # Child-safety disclosure in the question (see safety.py); the UI asks to tell the leader at once.
    urgent:bool=False
class LibraryItemView(BaseModel):
    id:UUID
    title:str
    kind:Literal['article','memo']
class LibraryTextView(LibraryItemView):
    text:str
class BuilderAIInput(Command):
    request:str=Field(min_length=3,max_length=2000)
    source_chunk_ids:list[UUID]=Field(min_length=1,max_length=8)
class ApplyBuilderAI(Command):
    run_id:UUID
    expected_version:int=Field(ge=1)
class AISettingsInput(Command):
    expected_version:int=Field(ge=0)
    enabled:bool
    daily_tokens:int=Field(ge=1000,le=10000000)
    daily_requests:int=Field(ge=1,le=10000)
    max_concurrent:int=Field(ge=1,le=10)
    timeout_seconds:int=Field(ge=5,le=90)
class AIRunView(BaseModel):
    id:UUID
    state:str
    error_code:str|None
    task:str
    model:str
    prompt_version:str
    output:dict[str,Any]|None
    charged_tokens:int
class AISettingsView(BaseModel):
    configured:bool
    enabled:bool
    model:str|None
    daily_tokens:int
    daily_requests:int
    max_concurrent:int
    timeout_seconds:int
    version:int
    circuit_open:bool
    charged_tokens:int
    reserved_tokens:int
    requests:int


class ProfileAIInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_profile_version: int = Field(ge=0)

class ProfileAIRunView(BaseModel):
    id: UUID
    state: str
    error_code: str | None = None
    profile_version: int
    suggestion_id: UUID | None = None
