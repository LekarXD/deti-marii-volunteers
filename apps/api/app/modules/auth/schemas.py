from typing import Literal
from uuid import UUID
from pydantic import BaseModel,Field
from datetime import datetime

class AuthSessionView(BaseModel):
    user_id: UUID | None
    registration_id: UUID | None
    foundation_id: UUID
    is_staff: bool
    permissions: list[str]
    csrf_token: str
    actor_id: str
    mfa_required: bool

class MfaSessionView(AuthSessionView):
    recovery_codes: list[str]

class ChallengeView(BaseModel):
    challenge_id: UUID
    status: Literal["queued"]
    delivery: Literal["dev_inbox", "pending"]

class MfaEnrollmentView(BaseModel):
    secret: str
    provisioning_uri: str

class AuthStatusView(BaseModel):
    status: Literal["logged_out", "revoked"]

class ContactChangeRequestCommand(BaseModel):
    email:str=Field(min_length=3,max_length=320)
class ContactChangeVerifyCommand(BaseModel):
    challenge_id:UUID
    token:str=Field(min_length=20,max_length=200)
class ContactChangeChallengeView(BaseModel):
    challenge_id:UUID
    expires_at:datetime
    delivery_state:Literal['dev_inbox','pending']
