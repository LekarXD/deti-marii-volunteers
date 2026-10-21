from datetime import datetime
from uuid import UUID
from pydantic import BaseModel,ConfigDict,Field
class SignalThresholds(BaseModel):
    model_config=ConfigDict(extra='forbid')
    miss:int=Field(default=2,ge=1,le=1000,strict=True)
    quiet:int=Field(default=21,ge=1,le=3650,strict=True)
    learn:int=Field(default=14,ge=1,le=3650,strict=True)
    app:int=Field(default=3,ge=1,le=3650,strict=True)
    shift:int=Field(default=7,ge=1,le=365,strict=True)
class SignalRulesInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=0)
    thresholds:SignalThresholds
class SignalRulesVersionInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=0)
class SignalRulesView(BaseModel):
    thresholds:SignalThresholds
    defaults:SignalThresholds
    version:int
    can_manage:bool
    last_run_at:datetime|None=None
    next_run_at:datetime|None=None
    last_result:dict={}
class RuleSignalView(BaseModel):
    id:UUID
    rule:str
    title:str
    details:dict
    state:str
    version:int
    observed_at:datetime
    can_manage:bool
    href:str
class RuleSignalDecision(SignalRulesVersionInput):
    reason:str=Field(min_length=3,max_length=4000)
