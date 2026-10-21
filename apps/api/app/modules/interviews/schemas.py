from datetime import date, datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

class WindowInput(BaseModel):
    local_start_date: date
    start_minute: int = Field(ge=0, le=1439)
    end_minute: int = Field(ge=1, le=1440)
    timezone: str = "Europe/Moscow"
    recurrence: Literal["once", "weekly"] = "once"
    interval_weeks: int = Field(default=1, ge=1, le=52)
    weekdays: list[int] = Field(default_factory=list, max_length=7)
    last_date: date | None = None
    duration_minutes: int = Field(default=30, ge=5, le=240)
    buffer_after_minutes: int = Field(default=0, ge=0, le=120)
    venue: str = Field(min_length=1, max_length=500)
    join_url: HttpUrl | None = None
    active: bool = True
    @model_validator(mode="after")
    def valid(self):
        try: ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError): raise ValueError("Укажите существующий часовой пояс")
        if self.end_minute - self.start_minute < self.duration_minutes: raise ValueError("В окно должна помещаться встреча")
        if self.last_date and self.last_date < self.local_start_date: raise ValueError("Последняя дата раньше первой")
        if any(d < 0 or d > 6 for d in self.weekdays) or len(set(self.weekdays)) != len(self.weekdays): raise ValueError("Некорректные дни недели")
        self.venue = self.venue.strip()
        if not self.venue: raise ValueError("Укажите место встречи")
        return self

class WindowUpdate(WindowInput):
    expected_version: int = Field(ge=1)
class VersionCommand(BaseModel):
    expected_version: int = Field(ge=1)
class PauseCommand(VersionCommand):
    active: bool
class ExceptionCommand(VersionCommand):
    origin_date: date
    kind: Literal["skip", "override", "restore"]
    start_minute: int | None = Field(default=None, ge=0, le=1439)
    end_minute: int | None = Field(default=None, ge=1, le=1440)
    @model_validator(mode="after")
    def valid(self):
        if self.kind == "override" and (self.start_minute is None or self.end_minute is None or self.end_minute <= self.start_minute): raise ValueError("Укажите интервал замены")
        return self
class BookingInput(BaseModel):
    slot_id: UUID
    slot_version: int = Field(ge=1)
    application_id: UUID | None = None
class MoveInput(BookingInput):
    expected_version: int = Field(ge=1)
class CancelInput(VersionCommand):
    reason: str = Field(min_length=1, max_length=2000)
class CompleteInput(VersionCommand):
    outcome: str = Field(min_length=1, max_length=200)
    public_agreement: str = Field(min_length=1, max_length=5000)
    private_note: str = Field(default="", max_length=10000)
    next_contact_date: date | None = None
class SlotView(BaseModel):
    id: UUID
    series_id: UUID
    coordinator_id: UUID
    starts_at: datetime
    ends_at: datetime
    timezone: str
    venue: str
    join_url: str | None
    version: int
class WindowView(WindowInput):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    coordinator_id: UUID
    version: int
    exceptions: list[dict] = Field(default_factory=list)
class BookingView(BaseModel):
    id: UUID
    application_id: UUID
    slot_id: UUID
    coordinator_id: UUID
    starts_at: datetime
    ends_at: datetime
    venue: str
    join_url: str | None
    status: str
    version: int
    cancel_reason: str | None
    result: dict | None = None
    events: list[dict] = Field(default_factory=list)
class StaffBookingView(BookingView):
    candidate_name: str
    private_note: str | None = None
