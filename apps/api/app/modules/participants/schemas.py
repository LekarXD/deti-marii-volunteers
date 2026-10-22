from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MEMO_TAGS_MAX = 12
MEMO_TAG_LENGTH = 40
MEMO_TAG_FIELDS = ("communication_tags", "support_tags", "interests_tags")


class ParticipantInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=200)
    birth_year: int | None = Field(default=None, ge=1900, le=2200)
    about: str = Field(default="", max_length=10000)
    # The text fields are an optional short note next to the memo chips.
    communication: str = Field(default="", max_length=10000)
    support: str = Field(default="", max_length=10000)
    interests: str = Field(default="", max_length=10000)
    communication_tags: list[str] = Field(default_factory=list, max_length=MEMO_TAGS_MAX)
    support_tags: list[str] = Field(default_factory=list, max_length=MEMO_TAGS_MAX)
    interests_tags: list[str] = Field(default_factory=list, max_length=MEMO_TAGS_MAX)
    photo_asset_id: UUID | None = None
    lifecycle: str = Field(default="active", pattern="^(active|archived)$")
    @field_validator("display_name")
    @classmethod
    def clean_name(cls, value):
        if not value.strip():
            raise ValueError("Укажите имя подопечного")
        return value.strip()
    @field_validator(*MEMO_TAG_FIELDS)
    @classmethod
    def clean_tags(cls, value):
        tags = []
        for tag in value:
            tag = " ".join(tag.split())
            if len(tag) > MEMO_TAG_LENGTH:
                raise ValueError(f"Пункт памятки длиннее {MEMO_TAG_LENGTH} символов")
            if tag and tag not in tags:
                tags.append(tag)
        return tags


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
    communication_tags: list[str]
    support_tags: list[str]
    interests_tags: list[str]
    photo_asset_id: UUID | None
    version: int
    lifecycle: str


class ParticipantGroupRef(BaseModel):
    """A current membership as staff see it next to the card; never part of the volunteer DTO."""
    id: UUID
    title: str
    membership_id: UUID
    valid_from: date


class StaffParticipant(SafeParticipant):
    groups: list[ParticipantGroupRef]


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
    items: list[StaffParticipant]
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
    author_name: str
    created_at: datetime


class PrivateNoteList(BaseModel):
    items: list[PrivateNoteView]


class ParticipantOccurrenceVolunteer(BaseModel):
    id: UUID
    display_name: str


class ParticipantOccurrence(BaseModel):
    id: UUID
    title: str
    starts_at: datetime
    ends_at: datetime
    timezone: str
    location: str
    group_title: str
    volunteers: list[ParticipantOccurrenceVolunteer]


class ParticipantOccurrenceList(BaseModel):
    items: list[ParticipantOccurrence]


class AssignmentParticipantList(BaseModel):
    assignment_id: UUID
    items: list[SafeParticipant]


class ParticipantStaffOption(BaseModel):
    id: UUID
    display_name: str


class ParticipantStaffOptions(BaseModel):
    items: list[ParticipantStaffOption]


class AssignmentSafeGroup(BaseModel):
    id: UUID
    title: str


class AssignmentGroupBriefing(AssignmentParticipantList):
    groups: list[AssignmentSafeGroup]
