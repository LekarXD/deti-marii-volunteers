from datetime import datetime
from uuid import UUID
from pydantic import BaseModel

class AdminAuditEventView(BaseModel):
    id:UUID
    created_at:datetime
    actor_id:str|None
    actor_label:str
    command:str
    entity_type:str
    entity_id:str|None
    changed_fields:list[str]
    request_id:str|None

class AdminAuditPageView(BaseModel):
    items:list[AdminAuditEventView]
    next_cursor:str|None
    snapshot_at:datetime
