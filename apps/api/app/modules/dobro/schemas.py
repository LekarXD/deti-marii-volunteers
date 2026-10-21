from datetime import date, datetime
from typing import Literal
from uuid import UUID
import re
from urllib.parse import urlsplit, urlunsplit
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DobroState = Literal['none', 'applied', 'approved', 'not_needed']

def dobro_url(value: str, profile=False, optional=False):
    value = value.strip()
    if not value and optional:
        return ''
    if any(ord(char) < 33 for char in value) or '\\' in value:
        raise ValueError('Укажите безопасную ссылку на Добро.рф.')
    parsed = urlsplit(value)
    try:
        host = (parsed.hostname or '').encode('idna').decode('ascii').lower()
        allowed = {'dobro.ru', 'добро.рф'.encode('idna').decode('ascii')}
        if parsed.scheme != 'https' or host not in allowed or parsed.port is not None or parsed.username or parsed.password or parsed.fragment:
            raise ValueError()
    except (ValueError, UnicodeError):
        raise ValueError('Нужна HTTPS-ссылка на dobro.ru или добро.рф без пароля, порта и фрагмента.')
    if profile and (not re.fullmatch(r'/volunteers/[1-9][0-9]*/?', parsed.path) or parsed.query):
        raise ValueError('Ссылка на профиль: https://dobro.ru/volunteers/12345')
    if not profile and not parsed.path.startswith('/'):
        parsed = parsed._replace(path='/')
    # Percent escapes cannot turn a permitted host into another origin. Queries are
    # allowed only for configured registration referrals; no server follows URLs.
    return urlunsplit(('https', host, parsed.path, parsed.query, ''))

class DobroCommand(BaseModel):
    model_config = ConfigDict(extra='forbid')

class DobroActivityCommand(DobroCommand):
    url: str = Field(max_length=1500)
    kind: Literal['long_term', 'one_off'] = 'long_term'
    title: str = Field(min_length=1, max_length=300)
    valid_from: date
    valid_until: date
    @field_validator('url')
    @classmethod
    def link(cls, value): return dobro_url(value)
    @field_validator('title')
    @classmethod
    def title_valid(cls, value):
        if not value.strip(): raise ValueError('Укажите название.')
        return value.strip()
    @model_validator(mode='after')
    def dates(self):
        if self.valid_until < self.valid_from: raise ValueError('Окончание раньше начала.')
        if self.valid_until.year > 9998: raise ValueError('Укажите год окончания до 9999, чтобы сохранить срок переноса.')
        return self

class DobroActivityView(DobroActivityCommand):
    id: UUID
    opportunity_id: UUID
    version: int
    can_edit: bool = False

class DobroActivityUpdate(DobroActivityCommand):
    expected_version: int = Field(gt=0)

class DobroProfileCommand(DobroCommand):
    profile_url: str = Field(default='', max_length=1500)
    expected_version: int = Field(ge=0)
    @field_validator('profile_url')
    @classmethod
    def link(cls, value): return dobro_url(value, profile=True, optional=True)

class DobroEnrollmentCommand(DobroCommand):
    state: DobroState
    expected_version: int = Field(ge=0)

class DobroEnrollmentView(BaseModel):
    state: DobroState
    version: int

class DobroProfileView(BaseModel):
    profile_url: str
    version: int

class DobroSeriesCommand(DobroCommand):
    opportunity_id: UUID
    expected_version: int = Field(ge=0)

class DobroSeriesView(BaseModel):
    series_id: UUID
    opportunity_id: UUID | None
    opportunity_title: str = ''
    version: int
    locked: bool

class DobroSettingsCommand(DobroCommand):
    expected_version: int = Field(ge=0)
    organization_url: str = Field(default='', max_length=1500)
    registration_url: str = Field(default='', max_length=1500)
    verified: bool = False
    monthly_day: int = Field(default=5, ge=1, le=28)
    hard_deadline_days: int = Field(default=60, ge=1, le=365)
    risk_days: int = Field(default=7, ge=1, le=60)
    rules_confirmed: bool = False
    reminders_enabled: bool = False
    reminder_template: str = Field(min_length=1, max_length=3000)
    @field_validator('organization_url', 'registration_url')
    @classmethod
    def links(cls, value): return dobro_url(value, optional=True)
    @field_validator('reminder_template')
    @classmethod
    def template(cls, value):
        if '{имя}' not in value or '{ссылка}' not in value: raise ValueError('Оставьте в шаблоне {имя} и {ссылка}.')
        return value

class DobroSettingsView(BaseModel):
    organization_url: str = ''
    registration_url: str = ''
    verified: bool = False
    monthly_day: int = 5
    hard_deadline_days: int = 60
    risk_days: int = 7
    rules_confirmed: bool = False
    reminders_enabled: bool = False
    reminder_template: str = '{имя}, чтобы мы внесли твои часы в электронную книжку Добро.рф, откликнись один раз на доброе дело: {ссылка}. Потом нажми «Я откликнулся» в Опоре.'
    version: int = 0
    rules_note: str = 'Опора готовит целые часы; оставшиеся минуты переходят дальше. Приём дробных часов и накопительной суммы за длительное доброе дело нужно сверить в CRM Добро.рф. Отметка здесь — подтверждение координатора, а не ответ Добро.рф.'

class DobroTransferHistoryView(BaseModel):
    id: UUID
    period: str
    hours_delta: int
    minutes_due_snapshot: int
    note: str
    entered_at: datetime

class DobroTransferRowView(BaseModel):
    id: UUID
    user_id: UUID
    display_name: str
    profile_url: str | None
    state: DobroState
    enrollment_version: int
    minutes_in_period: int
    eligible_minutes: int
    capped_minutes: int
    overlap_minutes: int = 0
    duration_trimmed_minutes: int = 0
    carry_minutes: int
    entered_hours: int
    hours_due: int
    target_total_hours: int
    correction_hours: int
    hard_deadline: date
    deadline_state: Literal['open', 'risk', 'overdue', 'complete']
    can_mark: bool
    historical: bool
    snapshot_hash: str
    history: list[DobroTransferHistoryView]
    reminder_text: str

class DobroTransferGroupView(BaseModel):
    activity: DobroActivityView
    rows: list[DobroTransferRowView]

class DobroTransferPeriodView(BaseModel):
    period: str
    groups: list[DobroTransferGroupView]
    total_hours_due: int
    total_people: int
    work_deadline: date
    at_risk_count: int
    rules_note: str

class DobroMarkRow(DobroCommand):
    id: UUID
    user_id: UUID
    activity_id: UUID
    period: str = Field(pattern=r'^\d{4}-(0[1-9]|1[0-2])$')
    snapshot_hash: str = Field(pattern=r'^[a-f0-9]{64}$')
    hours_delta: int = Field(ge=-100000, le=100000)

class DobroMarkCommand(DobroCommand):
    confirmed: Literal[True]
    note: str = Field(default='', max_length=3000)
    rows: list[DobroMarkRow] = Field(min_length=1, max_length=200)
    @model_validator(mode='after')
    def rows_valid(self):
        if len({row.id for row in self.rows}) != len(self.rows) or len({row.period for row in self.rows}) != 1:
            raise ValueError('Одна строка на человека и доброе дело; один месяц на подтверждение.')
        if any(row.hours_delta < 0 for row in self.rows) and not self.note.strip():
            raise ValueError('Для уменьшения часов укажите причину исправления.')
        return self

class DobroOwnActivityView(BaseModel):
    activity: DobroActivityView
    state: DobroState
    enrollment_version: int
    eligible_minutes: int
    entered_hours: int
    hours_due: int
    carry_minutes: int
    can_apply: bool

class DobroOwnView(BaseModel):
    profile_url: str = ''
    profile_version: int = 0
    registration_url: str = ''
    verified_organization: bool = False
    total_minutes: int
    entered_hours: int
    hours_due: int
    activities: list[DobroOwnActivityView]
    rules_note: str

class DobroTeamPersonView(BaseModel):
    user_id: UUID
    display_name: str
    state: DobroState
    enrollment_version: int
    reminder_text: str

class DobroPreparationView(BaseModel):
    key: Literal['publish_activity', 'enter_hours']
    title: str
    date: date
    note: str

class DobroTeamView(BaseModel):
    activity: DobroActivityView | None = None
    people: list[DobroTeamPersonView] = Field(default_factory=list)
    preparation: list[DobroPreparationView] = Field(default_factory=list)
