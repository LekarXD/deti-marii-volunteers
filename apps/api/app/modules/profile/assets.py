"""Resource-bound document access is re-evaluated on every download."""
import io,json,zipfile
from sqlalchemy import select
from app.core.errors import ApiError
from app.modules.assets.registry import register_asset_purpose
from .models import ProfileDocument,ProfileDataRequest

async def authorize_document(db,principal,resource_type,resource_id):
    if resource_type!='profile_document':raise ApiError(404,'asset_not_found','Файл не найден')
    row=await db.scalar(select(ProfileDocument).where(ProfileDocument.id==resource_id,ProfileDocument.foundation_id==principal.foundation_id))
    if row is None or not ((principal.user_id is not None and row.user_id==principal.user_id) or principal.has_permission('recognition.manage')):raise ApiError(404,'asset_not_found','Файл не найден')
async def authorize_export(db,principal,resource_type,resource_id):
    if resource_type!='profile_data_request':raise ApiError(404,'asset_not_found','Файл не найден')
    row=await db.scalar(select(ProfileDataRequest).where(ProfileDataRequest.id==resource_id,ProfileDataRequest.foundation_id==principal.foundation_id))
    if row is None or not ((principal.user_id is not None and row.user_id==principal.user_id) or principal.has_permission('profile.requests.review')):raise ApiError(404,'asset_not_found','Файл не найден')
def validate_pdf(data,content_type):
    if content_type!='application/pdf' or not data.startswith(b'%PDF-'):return False
    try:
        from pypdf import PdfReader
        document=PdfReader(io.BytesIO(data),strict=True)
        return not document.is_encrypted and 1<=len(document.pages)<=20 and not document.trailer['/Root'].get('/OpenAction') and all(not page.get('/AA') for page in document.pages)
    except Exception:return False

def validate_export(data,content_type):
    if content_type!='application/zip':return False
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos=archive.infolist()
            if len(infos)!=1 or infos[0].filename!='my-data.json' or infos[0].file_size>10*1024*1024:return False
            return isinstance(json.loads(archive.read('my-data.json')),dict)
    except (ValueError,KeyError,zipfile.BadZipFile):return False

register_asset_purpose('profile_document',content_types={'application/pdf'},max_bytes=5*1024*1024,authorize=authorize_document,validate=validate_pdf)
register_asset_purpose('profile_data_request',content_types={'application/zip'},max_bytes=10*1024*1024,authorize=authorize_export,validate=validate_export)
