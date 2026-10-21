"""Only authorized deck routes can create this upload purpose."""
from app.modules.assets.registry import register_asset_purpose
from app.core.errors import ApiError
from .service import deck_context
from .slides_convert import sniff,image_ext
from .document_upload import PPTX_MIME

TYPES=frozenset({'application/pdf',PPTX_MIME,'image/png','image/jpeg','image/webp'})
async def authorize(db,principal,resource_type,resource_id):
    if resource_type!='slide_deck':raise ApiError(404,'slide_deck_not_found','Презентация не найдена.')
    await deck_context(db,principal,resource_id,True)

def validate(data,content_type):
    try:
        kind=sniff(data)
        return (kind=='pdf' and content_type=='application/pdf') or (kind=='pptx' and content_type==PPTX_MIME) or (kind=='image' and {'png':'image/png','jpg':'image/jpeg','webp':'image/webp'}.get(image_ext(data))==content_type)
    except Exception:return False

register_asset_purpose('studio.slides',content_types=TYPES,max_bytes=50*1024*1024,authorize=authorize,validate=validate,processor_kind='slides.convert')
