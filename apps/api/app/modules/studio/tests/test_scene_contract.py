from uuid import uuid4
import pytest
from app.core.errors import ApiError
from app.modules.studio.scene import validate_scene,validate_capture_plan

def scene(kind='live_event'):
    return dict(schema_version=1,foundation_id=str(uuid4()),resource_kind=kind,resource_id=str(uuid4()),session_id=str(uuid4()),take_id=None,revision=0,render_profile_version='opora-stage/1',content_kind='camera',content_asset=None,deck_version_id=None,slide_id=None,board_snapshot_id=None,presenter_identity='opora-presenter',presenter_display_name='Test presenter',presenter_camera=False,screen_track_id=None,content_ratio=16/9,layout='camera_only',presenter_size=28,theme_id='opora-warm',recording_policy_id=str(uuid4()))

def test_prepared_recording_scene_uses_shared_schema_but_capture_requires_take():
    value=scene('lesson_recording_project');assert validate_scene(value)==value
    with pytest.raises(ApiError):validate_capture_plan(dict(schema_version=1,foundation_id=value['foundation_id'],resource_id=value['resource_id'],session_id=value['session_id'],take_id=None,generation=1,scene_revision=0,render_profile_version='opora-stage/1',recording_policy_id=value['recording_policy_id'],privacy_state='approved',raw_fallback='forbidden',allowed_tracks=[]))

def test_canonical_scene_rejects_provider_secret_unknown_fields_and_wrong_kind_refs():
    value=scene();value['provider_token']='private'
    with pytest.raises(ApiError):validate_scene(value)
    value=scene();value['content_kind']='slides'
    with pytest.raises(ApiError):validate_scene(value)
    value=scene();value['foundation_id']='not-a-uuid'
    with pytest.raises(ApiError):validate_scene(value)
