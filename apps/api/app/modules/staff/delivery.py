"""Trusted purpose registry: canonical invitation validation, never a generic email body."""
import secrets
from uuid import UUID
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.errors import ApiError
from app.integrations.delivery.registry import register_email_purpose
from .models import StaffInvitation
from .service import check_issuer
async def validate(db,outbox,payload):
    try:
        row=await db.get(StaffInvitation,UUID(payload.get('invitation_id','')),populate_existing=True)
        token=payload.get('token')
        if not isinstance(token,str) or not 20<=len(token)<=200:return 'suppressed_stale_invitation'
        if not row or row.foundation_id!=outbox.foundation_id or row.outbox_id!=outbox.id or row.state!='pending' or row.expires_at<=utcnow() or row.version!=payload.get('invitation_version') or row.normalized_contact!=payload.get('to') or str(row.invited_by_user_id)!=payload.get('actor_user_id') or not secrets.compare_digest(row.token_hash,digest(token)):return 'suppressed_stale_invitation'
        await check_issuer(db,row)
    except (ValueError,TypeError,ApiError):return 'suppressed_stale_invitation'
    return None

def render(payload):
    token=payload.get('token','')
    if not isinstance(token,str) or not 20<=len(token)<=200 or any(c.isspace() for c in token):raise ValueError('invalid_invitation_code')
    return ('Опора — приглашение в команду',f'Вас пригласили в команду фонда в Опоре.\n\nВойдите с почтой, на которую пришло это письмо, и откройте страницу «Принять приглашение». Введите код:\n\n{token}\n\nПосле принятия нужно настроить или подтвердить второй фактор и отдельно активировать права. Если вы не ожидали приглашения, не используйте код.')

register_email_purpose('staff_invitation',validate=validate,render=render,required_permission='staff.manage')
