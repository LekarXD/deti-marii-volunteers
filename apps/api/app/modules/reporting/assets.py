import csv,io,zipfile
from sqlalchemy import select
from defusedxml.ElementTree import fromstring
from app.core.errors import ApiError
from app.modules.assets.registry import register_asset_purpose
from app.modules.profile.assets import validate_pdf
from .models import ReportExport,ReportDraft
from .scopes import authorize_scope

async def authorize_export(db,principal,resource_type,resource_id):
    if resource_type!='report_export':raise ApiError(404,'asset_not_found','Файл не найден')
    pair=(await db.execute(select(ReportExport,ReportDraft).join(ReportDraft,ReportDraft.id==ReportExport.report_id).where(ReportExport.id==resource_id,ReportExport.foundation_id==principal.foundation_id,ReportDraft.foundation_id==principal.foundation_id))).one_or_none()
    if pair is None or pair[1].state=='withdrawn':raise ApiError(404,'asset_not_found','Файл не найден')
    _,report=pair
    await authorize_scope(db,principal,principal.foundation_id,report.scope_type,report.scope_id)
    await authorize_scope(db,principal,principal.foundation_id,report.scope_type,report.scope_id,'reports.export')

def validate_docx(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            infos=archive.infolist()
            if len(infos)>2000 or sum(info.file_size for info in infos)>50*1024*1024:return False
            if '[Content_Types].xml' not in archive.namelist() or 'word/document.xml' not in archive.namelist():return False
            for info in infos:
                if '..' in info.filename.split('/') or info.filename.startswith('/') or info.file_size>10*1024*1024:return False
                if info.filename.endswith(('.xml','.rels')):
                    blob=archive.read(info.filename);root=fromstring(blob)
                    if any(element.attrib.get('TargetMode')=='External' for element in root.iter()):return False
                    if b'macroEnabled' in blob or b'vbaProject' in blob:return False
            return True
    except Exception:return False

def validate_export(data,content_type):
    if content_type=='application/pdf':return validate_pdf(data,content_type)
    if content_type=='application/vnd.openxmlformats-officedocument.wordprocessingml.document':return validate_docx(data)
    if content_type=='text/csv':
        try:
            text=data.decode('utf-8-sig');rows=csv.reader(io.StringIO(text),delimiter=';')
            return 0<len(text)<=10*1024*1024 and sum(1 for _ in rows)<=51000 and '\x00' not in text
        except (UnicodeError,csv.Error):return False
    return False
register_asset_purpose('report_export',content_types={'text/csv','application/pdf','application/vnd.openxmlformats-officedocument.wordprocessingml.document'},max_bytes=10*1024*1024,authorize=authorize_export,validate=validate_export)
