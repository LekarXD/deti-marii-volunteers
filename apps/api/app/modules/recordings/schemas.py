from datetime import datetime
from typing import Annotated,Literal
from uuid import UUID
from pydantic import BaseModel,Field,WithJsonSchema,AfterValidator,ConfigDict
from app.modules.studio.scene import validator,validate_scene,validate_capture_plan
CanonicalScene=Annotated[dict,AfterValidator(validate_scene),WithJsonSchema(validator('scene.schema.json').schema)]
CanonicalCapturePlan=Annotated[dict,AfterValidator(validate_capture_plan),WithJsonSchema(validator('capture-plan.schema.json').schema)]
class RecordingProjectInput(BaseModel):
    title:str=Field(min_length=1,max_length=300)
    target_lesson_id:UUID|None=None
    mode:Literal['solo']='solo'
class LiveRecordingProjectInput(BaseModel):
    studio_session_id:UUID
    expected_scene_revision:int=Field(ge=0)
class RecordingVersionCommand(BaseModel):
    expected_version:int=Field(ge=1)
class RecordingProjectUpdate(RecordingVersionCommand):
    title:str|None=Field(None,min_length=1,max_length=300)
    target_lesson_id:UUID|None=None
class RecordingCapabilities(BaseModel):
    max_duration_seconds:int
    capture_limit_reason:str
    capture_available:bool
    capture_reason:str
    private_renderer_available:bool
    raw_fallback:Literal['forbidden']='forbidden'
class RecordingProjectView(BaseModel):
    id:UUID
    owner_user_id:UUID
    title:str
    mode:str
    live_event_id:UUID|None
    target_lesson_id:UUID|None
    state:str
    privacy_state:str
    version:int
    studio_session_id:UUID|None
    takes:list[UUID]
    takes_next_cursor:int|None
    capabilities:RecordingCapabilities
class RecordingProjectPage(BaseModel):
    items:list[RecordingProjectView]
    next_cursor:UUID|None
class RecordingTakeInput(RecordingVersionCommand):
    expected_scene_revision:int=Field(ge=0)
class RecordingPolicyTrack(BaseModel):
    model_config=ConfigDict(extra='forbid')
    identity:str=Field(min_length=1,max_length=128)
    track_id:str=Field(min_length=1,max_length=128)
    source:Literal['camera','screen','microphone','screen_audio']
    kind:Literal['video','audio']
    required:bool=True
class RecordingTakeView(BaseModel):
    max_duration_seconds:int
    stop_reason:Literal['owner_requested','duration_limit']|None
    privacy_state:Literal['unknown','approved','blocked']
    policy_scene_revision:int
    policy_tracks:list[RecordingPolicyTrack]
    id:UUID
    project_id:UUID
    number:int
    generation:int
    state:str
    version:int
    renderer_state_version:int
    projection_hash:str
    readiness_state:str
    capture_job_id:UUID|None
    capture_phase:str|None
    started_at:datetime|None
    stopped_at:datetime|None
    error_code:str|None
class RecordingTakePage(BaseModel):
    items:list[RecordingTakeView]
    next_cursor:int|None
class ResolvedRendererAsset(BaseModel):
    asset_id:UUID
    sha256:str
    width:int
    height:int
class RendererProviderGrant(BaseModel):
    provider:Literal['livekit']='livekit'
    url:str
    token:str
    identity:str
    session_id:UUID
    generation:int
    expires_in:int
class RendererSceneTransition(BaseModel):
    from_renderer_state_version:int
    from_projection_hash:str
    expires_at:datetime
class RendererStateView(BaseModel):
    resource_kind:Literal['live_event','lesson_recording_project']
    resource_id:UUID
    foundation_id:UUID
    project_id:UUID
    take_id:UUID
    session_id:UUID
    generation:int
    renderer_state_version:int
    projection_hash:str
    scene:CanonicalScene
    capture_plan:CanonicalCapturePlan
    resolved_assets:list[ResolvedRendererAsset]
    provider_grant:RendererProviderGrant|None=None
    invalidated:bool=False
    scene_transition:RendererSceneTransition|None=None
class RendererBootstrapView(RendererStateView):
    access_token:str
    expires_at:datetime
class RendererObservedTrack(BaseModel):
    model_config=ConfigDict(extra='forbid')
    identity:str=Field(min_length=1,max_length=128)
    track_id:str=Field(min_length=1,max_length=128)
    source:Literal['camera','screen','microphone','screen_audio']
    kind:Literal['video','audio']
    privacy_state:Literal['approved','unknown','blocked']
    state:Literal['ready','muted','missing']
class RendererAssetProof(BaseModel):
    asset_id:UUID
    sha256:str=Field(pattern='^[0-9a-f]{64}$')
class RendererReadinessInput(BaseModel):
    media_state:Literal['connected','connecting','blocked','disconnected','reconnecting']|None=None
    readiness_sequence:int=Field(ge=1)
    visual_ready:bool
    renderer_state_version:int=Field(ge=1)
    projection_hash:str=Field(pattern='^[0-9a-f]{64}$')
    viewport_width:int=Field(ge=1,le=16384)
    viewport_height:int=Field(ge=1,le=16384)
    device_pixel_ratio:float=Field(gt=0,le=8)
    render_profile_version:Literal['opora-stage/1']
    observed_tracks:list[RendererObservedTrack]=Field(max_length=64)
    asset_proofs:list[RendererAssetProof]=Field(max_length=64)
class RendererReadinessView(BaseModel):
    readiness_sequence:int
    ready:bool
    reasons:list[str]
    renderer_state_version:int
    projection_hash:str
    capture_state:str
    valid_until:datetime|None
class RecordingReviewCommand(RecordingVersionCommand):
    render_hash:str=Field(pattern='^[0-9a-f]{64}$')
    reason:str=Field(default='',max_length=4000)
class RecordingRenderView(BaseModel):
    id:UUID
    project_id:UUID
    take_id:UUID
    generation:int
    state:str
    version:int
    asset_id:UUID|None
    render_hash:str
    content_hash:str|None
    duration_ms:int|None
    quality:str
    error_code:str|None
    approval_state:str

class RecordingPolicyCommand(RecordingVersionCommand):
    expected_scene_revision:int=Field(ge=0)
    approved:bool
    tracks:list[RecordingPolicyTrack]=Field(max_length=64)
class RecordingRenderPage(BaseModel):
    items:list[RecordingRenderView]
    next_cursor:UUID|None
