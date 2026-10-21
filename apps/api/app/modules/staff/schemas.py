from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,Field,ConfigDict

class StaffPermissionSelection(BaseModel):
    model_config=ConfigDict(extra='forbid')
    permission:str=Field(min_length=3,max_length=100)
    scope_type:Literal['foundation','group','webinar']='foundation'
    scope_id:UUID|None=None
class GrantInput(StaffPermissionSelection):
    user_id:UUID
    expected_version:int|None=Field(default=None,ge=1)
class GrantView(BaseModel):
    id:UUID
    permission:str
    scope_type:str='foundation'
    scope_id:UUID|None=None
    scope_label:str='Весь фонд'
    revoked_at:datetime|None=None
class RevokeView(BaseModel):
    status:str
    version:int|None=None
class StaffVersionCommand(BaseModel):
    expected_version:int=Field(ge=1)
class StaffMemberView(BaseModel):
    user_id:UUID
    display_name:str
    verified_contact:str|None=None
    membership_id:UUID
    state:str
    mfa_state:Literal['not_enrolled','pending','enabled']
    version:int
    grants:list[GrantView]
class StaffDirectoryView(BaseModel):
    items:list[StaffMemberView]
class StaffPermissionOptionView(BaseModel):
    permission:str
    label:str
    description:str
    scope_types:list[str]
class StaffPermissionCatalogView(BaseModel):
    items:list[StaffPermissionOptionView]
class StaffScopeOptionView(BaseModel):
    scope_type:str
    id:UUID|None=None
    label:str
class StaffUserOptionView(BaseModel):
    id:UUID
    display_name:str
    contact:str
    version:int
class StaffInvitationInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    contact:str=Field(min_length=3,max_length=320)
    grants:list[StaffPermissionSelection]=Field(min_length=1,max_length=40)
    expires_in_hours:int=Field(default=72,ge=1,le=168)
class StaffInvitationAcceptInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    token:str=Field(min_length=20,max_length=200)
class StaffInvitationView(BaseModel):
    id:UUID
    contact:str
    state:str
    expires_at:datetime
    grants:list[StaffPermissionSelection]
    delivery_state:str
    version:int
    accepted_user_id:UUID|None=None
    membership_id:UUID|None=None
    next_action:Literal['verify_contact','accept','enroll_mfa','verify_mfa','finalize','complete','none']='none'
