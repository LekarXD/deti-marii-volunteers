from datetime import datetime
from typing import Literal
from pydantic import AwareDatetime,BaseModel

InboxKind=Literal['invitation','place_confirmed','occurrence_cancelled','question_answered','reflection_review','prize_issued','prize_rejected','gratitude']


class InboxItem(BaseModel):
    key:str
    kind:InboxKind
    title:str
    text:str
    at:datetime
    href:str


class InboxView(BaseModel):
    items:list[InboxItem]
    unread:int


class InboxSeenCommand(BaseModel):
    at:AwareDatetime
