from datetime import datetime
from typing import Literal
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field

class TelegramLinkCommand(BaseModel):
    model_config=ConfigDict(extra='forbid')
class TelegramDisconnectCommand(TelegramLinkCommand):
    expected_version:int=Field(ge=0)
class TelegramBindingView(BaseModel):
    state:Literal['unavailable','disconnected','pending','linked','conflict']
    configured:bool
    delivery_available:Literal[False]=False
    binding_id:UUID|None=None
    version:int=0
    verified_at:datetime|None=None
    token_id:UUID|None=None
    token_expires_at:datetime|None=None
    reason:str
class TelegramLinkTokenView(BaseModel):
    id:UUID
    state:Literal['issued','consumed','expired','revoked']
    expires_at:datetime
    start_url:str|None=None
class TelegramWebhookView(BaseModel):
    state:Literal['linked','ignored','conflict']
