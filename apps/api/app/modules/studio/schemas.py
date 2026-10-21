from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,Field,ConfigDict,model_validator

class WebinarInput(BaseModel):
    title:str=Field(min_length=1,max_length=300)
    description:str=Field(default='',max_length=10000)
    starts_at:datetime
    duration_minutes:int=Field(default=60,ge=5,le=480)
    require_strict_revocation:bool=True
    @model_validator(mode='after')
    def timezone_required(self):
        if self.starts_at.tzinfo is None:raise ValueError('Укажите часовой пояс времени начала')
        if not self.title.strip():raise ValueError('Укажите название')
        return self
class StudioVersionCommand(BaseModel):
    expected_version:int=Field(ge=1)
class WebinarUpdate(WebinarInput):
    expected_version:int=Field(ge=1)
class WebinarView(WebinarInput):
    model_config=ConfigDict(from_attributes=True)
    id:UUID
    host_user_id:UUID
    state:str
    version:int
    enrollment_state:str|None=None
    session_id:UUID|None=None
class StudioSessionCreate(BaseModel):
    resource_kind:Literal['live_event','lesson_recording_project']
    resource_id:UUID
class StudioSessionView(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id:UUID
    resource_kind:str
    resource_id:UUID
    host_user_id:UUID
    state:str
    generation:int
    scene:dict
    scene_revision:int
    version:int
    capabilities:dict
    can_host:bool
    board_available:bool
class StudioSceneCommand(BaseModel):
    expected_revision:int=Field(ge=0)
    scene:dict
class StudioJoinView(BaseModel):
    provider:Literal['livekit']='livekit'
    url:str
    token:str
    identity:str
    host_identity:str
    role:Literal['host','audience']
    session_id:UUID
    generation:int
    expires_in:int
    strict_revocation:bool
class StudioEnrollmentView(BaseModel):
    webinar_id:UUID
    state:str
    version:int
class StudioBoardGrantInput(StudioVersionCommand):
    user_id:UUID
    can_draw:bool
class StudioBoardPass(BaseModel):
    url:str
    token:str
    can_draw:bool
    expires_in:int
class SlideUploadInput(BaseModel):
    resource_kind:Literal['live_event','lesson_recording_project']
    resource_id:UUID
    title:str=Field(min_length=1,max_length=300)
    content_type:str
    expected_size:int=Field(gt=0,le=50*1024*1024)
    checksum:str=Field(pattern='^[a-f0-9]{64}$')
class SlidePageView(BaseModel):
    id:UUID
    ordinal:int
    asset_id:UUID
    sha256:str
    width:int
    height:int
    content_url:str
class SlideDeckView(BaseModel):
    id:UUID
    title:str
    state:str
    error_code:str|None
    version:int
    deck_version_id:UUID|None=None
    pages:list[SlidePageView]=Field(default_factory=list)
    upload:dict|None=None
class StudioBoardSnapshotInput(BaseModel):
    asset_id:UUID
    taken_at:datetime|None=None
