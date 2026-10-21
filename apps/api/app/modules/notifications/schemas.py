from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,Field

class PreferenceCommand(BaseModel):
    expected_version:int=Field(ge=0)
    no_contact:bool
    email_enabled:bool
    in_app_enabled:bool
class PreferenceView(BaseModel):
    no_contact:bool
    email_enabled:bool
    in_app_enabled:bool
    effective_no_contact:bool
    version:int
    email_provider_state:str
class TemplateInput(BaseModel):
    key:str=Field(pattern='^[a-z0-9][a-z0-9_.-]{0,99}$')
    channel:Literal['email','in_app']
    subject:str=Field(min_length=1,max_length=300)
    body:str=Field(min_length=1,max_length=8000)
class TemplateUpdate(BaseModel):
    expected_version:int=Field(ge=1)
    subject:str=Field(min_length=1,max_length=300)
    body:str=Field(min_length=1,max_length=8000)
class VersionCommand(BaseModel):
    expected_version:int=Field(ge=1)
class TemplateView(BaseModel):
    id:UUID
    key:str
    channel:str
    subject:str
    body:str
    state:str
    version:int
    published_version_id:UUID|None
    fields:list[str]
    allowed_actions:list[str]
class TemplateList(BaseModel):
    items:list[TemplateView]
    next_cursor:str|None
class AudienceCommand(BaseModel):
    template_version_id:UUID
    recipient_user_ids:list[UUID]=Field(min_length=1,max_length=500)
class AudienceMember(BaseModel):
    user_id:UUID
    display_name:str
    eligible:bool
    reason:str|None
class AudienceView(BaseModel):
    id:UUID
    template_version_id:UUID
    members:list[AudienceMember]
    eligible_count:int
    preview_hash:str
    expires_at:datetime
class SendAudienceCommand(BaseModel):
    preview_id:UUID
    preview_hash:str=Field(min_length=64,max_length=64)
    confirmed:Literal[True]
class EnqueuedView(BaseModel):
    enqueued:int
    delivery_ids:list[UUID]
    state:Literal['queued']
class DeliveryAttemptView(BaseModel):
    attempt_number:int
    state:str
    error_code:str|None
    started_at:datetime
    completed_at:datetime|None
class DeliveryView(BaseModel):
    id:UUID
    recipient_user_id:UUID|None
    template_version_id:UUID|None
    channel:str
    state:str
    version:int
    attempts:list[DeliveryAttemptView]
    attempts_next_cursor:int|None
class DeliveryList(BaseModel):
    items:list[DeliveryView]
    next_cursor:UUID|None
class WebhookInput(BaseModel):
    event_id:str=Field(min_length=1,max_length=200)
    message_id:str=Field(min_length=1,max_length=200)
    state:Literal['delivered','bounced']
class WebhookView(BaseModel):
    status:Literal['applied','replayed','ignored_stale']

class DeliveryAttemptPage(BaseModel):
    items:list[DeliveryAttemptView]
    next_cursor:int|None
class NotificationReadinessView(BaseModel):
    channel:str
    state:str
    reason:str
    webhook_state:str
    external_send_enabled:bool
