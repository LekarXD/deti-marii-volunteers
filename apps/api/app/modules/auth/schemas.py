from typing import Literal
from uuid import UUID
from pydantic import BaseModel

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
