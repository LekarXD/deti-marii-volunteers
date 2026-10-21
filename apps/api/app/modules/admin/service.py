"""Foundation-scoped keyset audit pages; no change bodies or contact joins."""
import json,re
from datetime import datetime,timezone
from uuid import UUID
from cryptography.fernet import InvalidToken
from sqlalchemy import select,cast,String,and_,tuple_
from app.core.clock import utcnow
from app.core.crypto import seal,unseal
from app.core.errors import ApiError
from app.core.models import AuditEvent,User
from .schemas import AdminAuditEventView,AdminAuditPageView

IDENTIFIER=re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.:-]{0,119}\Z')
FIELD=re.compile(r'[A-Za-z_][A-Za-z0-9_.:-]{0,79}\Z')
def timestamp(value):
    if value is None:return None
    if value.tzinfo is None:raise ApiError(422,'audit_timezone_required','Укажите часовой пояс для границ периода')
    return value.astimezone(timezone.utc).isoformat()
def uuid_text(value):
    try:return str(UUID(str(value)))
    except (ValueError,TypeError,AttributeError):return None

def cursor_value(cursor,scope):
    if not cursor:return utcnow(),None
    try:
        value=json.loads(unseal(cursor))
        if not isinstance(value,dict) or set(value)!={'scope','snapshot_at','created_at','id'} or value['scope']!=scope:raise ValueError()
        anchor=datetime.fromisoformat(value['snapshot_at']);created=datetime.fromisoformat(value['created_at']);row_id=UUID(value['id'])
        if not anchor.tzinfo or not created.tzinfo or created>anchor:raise ValueError()
        return anchor,(created,row_id)
    except (InvalidToken,ValueError,TypeError,KeyError,OverflowError):raise ApiError(422,'invalid_audit_cursor','Страница журнала недействительна. Начните просмотр заново') from None

async def audit_page(db,principal,*,limit,cursor,from_at,until_at,command):
    lower,upper=timestamp(from_at),timestamp(until_at)
    if from_at and until_at and from_at>=until_at:raise ApiError(422,'invalid_audit_period','Конец периода должен быть позже начала')
    if command and not IDENTIFIER.fullmatch(command):raise ApiError(422,'invalid_audit_command','Укажите технический код действия без пробелов')
    scope=dict(foundation_id=str(principal.foundation_id),from_at=lower,until_at=upper,command=command or None)
    anchor,before=cursor_value(cursor,scope)
    query=select(AuditEvent,User.display_name).outerjoin(User,and_(cast(User.id,String)==AuditEvent.actor_id,User.foundation_id==principal.foundation_id)).where(AuditEvent.foundation_id==principal.foundation_id,AuditEvent.created_at<=anchor)
    if from_at:query=query.where(AuditEvent.created_at>=from_at)
    if until_at:query=query.where(AuditEvent.created_at<until_at)
    if command:query=query.where(AuditEvent.command==command)
    if before:query=query.where(tuple_(AuditEvent.created_at,AuditEvent.id)<tuple_(*before))
    rows=(await db.execute(query.order_by(AuditEvent.created_at.desc(),AuditEvent.id.desc()).limit(limit+1))).all()
    items=[]
    for row,label in rows[:limit]:
        items.append(AdminAuditEventView(id=row.id,created_at=row.created_at,actor_id=uuid_text(row.actor_id),actor_label=label or 'Участник системы',command=row.command if IDENTIFIER.fullmatch(row.command) else 'unknown',entity_type=row.entity_type if IDENTIFIER.fullmatch(row.entity_type) else 'unknown',entity_id=row.entity_id if IDENTIFIER.fullmatch(row.entity_id) else None,changed_fields=list(dict.fromkeys(field for field in row.changed_fields if isinstance(field,str) and FIELD.fullmatch(field)))[:100],request_id=uuid_text(row.request_id)))
    next_cursor=None
    if len(rows)>limit:
        last=rows[limit-1][0];next_cursor=seal(json.dumps(dict(scope=scope,snapshot_at=anchor.isoformat(),created_at=last.created_at.isoformat(),id=str(last.id)),separators=(',',':')))
    return AdminAuditPageView(items=items,next_cursor=next_cursor,snapshot_at=anchor)
