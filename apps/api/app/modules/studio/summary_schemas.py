from datetime import datetime
from uuid import UUID
from pydantic import BaseModel,Field,ConfigDict

class SummaryEditInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=0)
    title:str=Field(min_length=1,max_length=300)
    body:str=Field(min_length=1,max_length=7000)
class SummaryVersionInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=1)
    revision:int=Field(ge=1)
class SummaryRevisionView(BaseModel):
    number:int
    title:str
    body:str
class WebinarSummaryView(BaseModel):
    webinar_id:UUID
    version:int
    draft:SummaryRevisionView|None=None
    reviewed_revision:int|None=None
    published:SummaryRevisionView|None=None
    can_manage:bool=False
    can_send:bool=False
class SummaryAudienceMemberView(BaseModel):
    user_id:UUID
    display_name:str
    enrollment_version:int
    eligible:bool
    reason:str|None=None
class SummaryAudiencePreviewView(BaseModel):
    id:UUID
    published_revision:int
    members:list[SummaryAudienceMemberView]
    eligible_count:int
    preview_hash:str
    expires_at:datetime
class SummarySendInput(SummaryVersionInput):
    preview_id:UUID
    preview_hash:str=Field(min_length=64,max_length=64)
class SummarySendView(BaseModel):
    state:str
    enqueued:int
    delivery_ids:list[UUID]
