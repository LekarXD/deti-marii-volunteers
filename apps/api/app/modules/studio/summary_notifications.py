"""P17 reconstructs published text after current sender/enrollment authorization."""
from uuid import UUID
from sqlalchemy import select
from app.core.auth import load_background_staff_authorization,assert_background_authorizations_locked
from app.core.errors import ApiError
from app.modules.messaging.registry import register_notice_source
from .models import Webinar,WebinarEnrollment
from .summary_models import WebinarSummary,WebinarSummaryDelivery
from .summary_service import revision

async def source_rows(db,outbox,source):
    try:id=UUID(source['delivery_id'])
    except (ValueError,TypeError,KeyError):return None
    return (await db.execute(select(WebinarSummaryDelivery,WebinarSummary).join(WebinarSummary,WebinarSummary.id==WebinarSummaryDelivery.summary_id).where(WebinarSummaryDelivery.id==id,WebinarSummaryDelivery.outbox_id==outbox.id,WebinarSummary.foundation_id==outbox.foundation_id))).one_or_none()
async def lock_subjects(db,outbox,source):
    pair=await source_rows(db,outbox,source)
    return [pair[0].sender_user_id,pair[0].recipient_id] if pair else []
async def resolve_summary(db,outbox,source):
    pair=await source_rows(db,outbox,source)
    if not pair:return 'suppressed_summary_source'
    delivery,summary=pair
    try:assert_background_authorizations_locked(db,outbox.foundation_id,[delivery.sender_user_id,delivery.recipient_id])
    except ApiError:return 'suppressed_summary_authz'
    sender=await load_background_staff_authorization(db,outbox.foundation_id,delivery.sender_user_id)
    if not sender or not sender.has_permission('studio.manage') or not sender.has_permission('notifications.send'):return 'suppressed_summary_sender'
    webinar=await db.scalar(select(Webinar).where(Webinar.id==summary.webinar_id,Webinar.foundation_id==outbox.foundation_id).with_for_update())
    await db.refresh(summary,with_for_update=True)
    if not webinar or webinar.state!='ended' or summary.published_revision!=delivery.published_revision:return 'suppressed_summary_stale'
    enrollment=await db.scalar(select(WebinarEnrollment).where(WebinarEnrollment.webinar_id==webinar.id,WebinarEnrollment.foundation_id==outbox.foundation_id,WebinarEnrollment.user_id==delivery.recipient_id).with_for_update())
    if not enrollment or enrollment.state!='enrolled':return 'suppressed_summary_enrollment'
    content=await revision(db,summary,delivery.published_revision)
    if not content:return 'suppressed_summary_source'
    return dict(recipient_id=str(delivery.recipient_id),subject=content.title,text=content.body,topic='learning')
register_notice_source('webinar_summary',resolve_summary,lock_subjects=lock_subjects)
