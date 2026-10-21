from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ParticipantInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    birth_year: int | None = Field(default=None, ge=1900, le=2200)
    about: str = Field(default="", max_length=10000)
    communication: str = Field(default="", max_length=10000)
    support: str = Field(default="", max_length=10000)
    interests: str = Field(default="", max_length=10000)
    photo_asset_id: UUID | None = None
    lifecycle: str = Field(default="active", pattern="^(active|archived)$")
    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("Укажите имя участника")
        return value.strip()


class ParticipantUpdate(ParticipantInput):
    expected_version: int = Field(ge=1)


class SafeParticipant(BaseModel):
    id: UUID
    display_name: str
    birth_year: int | None
    about: str
    communication: str
    support: str
    interests: str
    photo_asset_id: UUID | None
    version: int
    lifecycle: str


class GroupInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    schedule: str = Field(default="", max_length=5000)
    location: str = Field(default="", max_length=5000)
    leader_id: UUID | None = None
    coordinator_id: UUID | None = None
    lifecycle: str = Field(default="active", pattern="^(active|archived)$")
    @field_validator("title")
    @classmethod
    def clean_title(cls, value):
        if not value.strip():
            raise ValueError("Укажите название группы")
        return value.strip()


class GroupUpdate(GroupInput):
    expected_version: int = Field(ge=1)


class GroupView(GroupInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version: int


class MembershipInput(BaseModel):
    participant_id: UUID
    valid_from: date
    valid_until: date | None = None
    expected_version: int = Field(ge=1)
    @model_validator(mode="after")
    def valid_interval(self):
        if self.valid_until is not None and self.valid_until <= self.valid_from:
            raise ValueError("Дата окончания должна быть позже даты начала")
        return self


class MembershipEnd(BaseModel):
    valid_until: date
    expected_version: int = Field(ge=1)


class PrivateNoteInput(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Введите заметку")
        return value.strip()


class ParticipantList(BaseModel):
    items: list[SafeParticipant]
    limit: int
    offset: int


class GroupList(BaseModel):
    items: list[GroupView]


class MembershipView(BaseModel):
    id: UUID
    participant_id: UUID
    valid_from: date
    valid_until: date | None


class MembershipResult(MembershipView):
    group_version: int


class GroupMember(MembershipView):
    participant: SafeParticipant


class GroupDetail(GroupView):
    at: date
    members: list[GroupMember]


class PrivateNoteView(BaseModel):
    id: UUID
    text: str
    author_id: UUID
    created_at: datetime


class PrivateNoteList(BaseModel):
    items: list[PrivateNoteView]


class AssignmentParticipantList(BaseModel):
    assignment_id: UUID
    items: list[SafeParticipant]


class ParticipantStaffOption(BaseModel):
    id: UUID
    display_name: str


class ParticipantStaffOptions(BaseModel):
    items: list[ParticipantStaffOption]
