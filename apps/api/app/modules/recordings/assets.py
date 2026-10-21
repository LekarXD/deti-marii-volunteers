from app.core.errors import ApiError
from app.modules.assets.registry import register_asset_purpose
from .models import RecordingRenderVersion
from . import service
async def authorize(db,p,resource_type,resource_id):
    if resource_type!='recording_render':service.deny()
    render=await db.get(RecordingRenderVersion,resource_id)
    if render is None:service.deny()
    await service.project(db,p,render.project_id)

def validate(data,content_type):
    # Full ffprobe decode/media validation is owned by the fenced renderer job before asset creation.
    return content_type=='video/mp4' and len(data)>32 and data[4:8]==b'ftyp'
register_asset_purpose('recording.output',content_types={'video/mp4'},max_bytes=500*1024*1024,authorize=authorize,validate=validate)
