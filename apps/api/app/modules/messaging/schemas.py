from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator

class ConversationCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    member_ids: list[UUID] = Field(min_length=1, max_length=100)
class DirectCreate(BaseModel):
    recipient_id: UUID
class MemberCommand(BaseModel):
    user_id: UUID
    expected_version: int = Field(ge=1)
class MessageCreate(BaseModel):
    text: str = Field(default="", max_length=8000)
    photo_policy: Literal["not_applicable", "no_people"] = "not_applicable"
    asset_ids: list[UUID] = Field(default_factory=list, max_length=10)
    @model_validator(mode="after")
    def meaningful(self):
        self.text = self.text.strip()
        if not self.text and not self.asset_ids:
            raise ValueError("Введите сообщение или приложите файл")
        if len(set(self.asset_ids)) != len(self.asset_ids):
            raise ValueError("Файлы не должны повторяться")
        return self
class ReadCommand(BaseModel):
    last_read_seq: int = Field(ge=0)
class ConversationMemberView(BaseModel):
    user_id: UUID
    display_name: str
class AttachmentView(BaseModel):
    id: UUID
    content_type: str
    size: int
    content_url: str
class MessageView(BaseModel):
    id: UUID
    conversation_id: UUID
    author_user_id: UUID | None
    author_name: str
    seq: int
    text: str
    created_at: datetime
    assets: list[AttachmentView]
class ConversationView(BaseModel):
    id: UUID
    title: str
    kind: Literal["direct", "group", "system"]
    version: int
    last_seq: int
    last_read_seq: int
    unread_count: int
    last_message: MessageView | None
    members: list[ConversationMemberView]
    allowed_actions: list[str]
    external_delivery: Literal["unavailable"] = "unavailable"
class ConversationPage(BaseModel):
    items: list[ConversationView]
    next_cursor: str | None
class MessagePage(BaseModel):
    items: list[MessageView]
    next_before_seq: int | None
    has_more: bool
    revision: int
class ConversationSyncView(BaseModel):
    conversation: ConversationView
    messages: list[MessageView]
    has_more: bool
    next_after_seq: int
class ReadCursorView(BaseModel):
    last_read_seq: int
    unread_count: int
class MembershipView(BaseModel):
    version: int
    user_id: UUID
    active: bool
class DeliveryReadinessView(BaseModel):
    channel: str
    state: Literal["available", "unavailable", "development_only"]
    reason: str

class ContactView(BaseModel):
    user_id: UUID
    display_name: str
    is_coordinator: bool
class ContactPage(BaseModel):
    items: list[ContactView]
    next_cursor: UUID | None
