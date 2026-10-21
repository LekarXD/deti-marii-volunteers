from sqlalchemy import select
from app.core.errors import ApiError
from app.modules.assets.registry import register_asset_purpose
from .audio_media import CONTENT_TYPES,MAX_BYTES,validate_audio
from .models import Reflection

PURPOSE='followups.reflection_audio'
RESOURCE='reflection_assignment'

async def authorize_audio_assignment(db,principal,resource_type,assignment_id):
    from .service import own_assignment,utcnow
    if resource_type!=RESOURCE:raise ApiError(404,'audio_not_found','Запись не найдена')
    item,event=await own_assignment(db,principal,assignment_id)
    await db.refresh(item);await db.refresh(event)
    if item.status!='confirmed' or event.status=='cancelled' or event.ends_at>utcnow():
        raise ApiError(403,'audio_access_revoked','Запись недоступна для этого назначения')
    submitted=await db.scalar(select(Reflection.submitted_at).where(Reflection.assignment_id==assignment_id,Reflection.foundation_id==principal.foundation_id))
    if submitted:raise ApiError(403,'reflection_submitted','Рефлексия уже передана координатору')

register_asset_purpose(PURPOSE,content_types=CONTENT_TYPES,max_bytes=MAX_BYTES,authorize=authorize_audio_assignment,validate=validate_audio,processor_kind='followups.audio')
