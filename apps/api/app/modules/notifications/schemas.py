from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,Field,model_validator
from zoneinfo import ZoneInfo,ZoneInfoNotFoundError

Topic = Literal['assignments','learning','messages','news']
class NotificationTopics(BaseModel):
    assignments:bool=True
    learning:bool=True
    messages:bool=True
    news:bool=False
class NotificationPreferenceCommand(BaseModel):
    expected_version:int=Field(ge=0)
    no_contact:bool
    email_enabled:bool
    in_app_enabled:bool
    topics:NotificationTopics|None=None
    quiet_enabled:bool|None=None
    quiet_from:int|None=Field(None,ge=0,lt=1440)
    quiet_to:int|None=Field(None,ge=0,lt=1440)
    timezone:str|None=Field(None,max_length=80)
    @model_validator(mode='after')
    def valid_timezone(self):
        if self.timezone:
            try:ZoneInfo(self.timezone)
            except (ZoneInfoNotFoundError,ValueError):raise ValueError('Неизвестный часовой пояс')
        return self
class PreferenceView(BaseModel):
    no_contact:bool
    email_enabled:bool
    in_app_enabled:bool
    effective_no_contact:bool
    version:int
    email_provider_state:str
    topics:NotificationTopics
    quiet_enabled:bool
    quiet_from:int
    quiet_to:int
    timezone:str
    news_consent:bool
class TemplateInput(BaseModel):
    key:str=Field(pattern='^[a-z0-9][a-z0-9_.-]{0,99}$')
    channel:Literal['email','in_app']
    topic:Topic='messages'
    subject:str=Field(min_length=1,max_length=300)
    body:str=Field(min_length=1,max_length=8000)
class TemplateUpdate(BaseModel):
    topic:Topic|None=None
    expected_version:int=Field(ge=1)
    subject:str=Field(min_length=1,max_length=300)
    body:str=Field(min_length=1,max_length=8000)
class NotificationVersionCommand(BaseModel):
    expected_version:int=Field(ge=1)
class TemplateView(BaseModel):
    id:UUID
    key:str
    channel:str
    topic:Topic
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
    next_attempt_at:datetime|None
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
class NotificationChannelReadiness(BaseModel):
    channel:str
    state:str
    reason:str
class NotificationReadinessView(BaseModel):
    channel:str
    state:str
    reason:str
    webhook_state:str
    external_send_enabled:bool
    channels:list[NotificationChannelReadiness]

class NotificationRecipient(BaseModel):
    id:UUID
    display_name:str
class NotificationRecipientPage(BaseModel):
    items:list[NotificationRecipient]
    next_cursor:UUID|None
