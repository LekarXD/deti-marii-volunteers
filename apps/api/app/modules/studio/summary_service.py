from datetime import timedelta
import hashlib,json
from uuid import UUID,uuid4
from sqlalchemy import select
from app.core.auth import authz_guard
from app.core.clock import utcnow
from app.core.contact_policy import contact_guard
from app.core.errors import ApiError
from app.core.audit import audit
from app.core.models import User
from app.modules.messaging.consumers import enqueue_notice
from app.modules.notifications.service import may_contact
from .models import Webinar,WebinarEnrollment
from .summary_models import WebinarSummary,WebinarSummaryRevision,WebinarSummaryPreview,WebinarSummaryDelivery

def denied():raise ApiError(404,'summary_not_found','Итоги занятия недоступны.')
def require_manage(p,send=False):
    if not p.user_id or not p.has_permission('studio.manage') or (send and not p.has_permission('notifications.send')):raise ApiError(403,'permission_denied','Недостаточно прав для работы с итогами занятия.')
async def scope(db,p,id,lock=False,send=False):
    require_manage(p,send)
    query=select(Webinar).where(Webinar.id==id,Webinar.foundation_id==p.foundation_id)
    if lock:query=query.with_for_update()
    webinar=await db.scalar(query)
    if not webinar:denied()
    if webinar.state!='ended':raise ApiError(409,'webinar_not_ended','Итоги доступны после завершения занятия.')
    return webinar
async def summary(db,webinar_id,lock=False):
    query=select(WebinarSummary).where(WebinarSummary.webinar_id==webinar_id)
    if lock:query=query.with_for_update()
    return await db.scalar(query)
async def revision(db,row,number):
    return await db.scalar(select(WebinarSummaryRevision).where(WebinarSummaryRevision.summary_id==row.id,WebinarSummaryRevision.number==number)) if number else None
def revision_view(row):return {'number':row.number,'title':row.title,'body':row.body} if row else None
async def view(db,p,webinar,row):
    return dict(webinar_id=webinar.id,version=row.version if row else 0,draft=revision_view(await revision(db,row,row.draft_revision)) if row else None,reviewed_revision=row.reviewed_revision if row else None,published=revision_view(await revision(db,row,row.published_revision)) if row else None,can_manage=p.has_permission('studio.manage'),can_send=p.has_permission('studio.manage') and p.has_permission('notifications.send'))
def version(row,expected):
    current=row.version if row else 0
    if expected!=current:raise ApiError(409,'version_conflict','Итоги изменились. Обновите данные.',current_version=current)
def exact_draft(row,body):
    version(row,body.expected_version)
    if not row or row.draft_revision!=body.revision:raise ApiError(409,'summary_revision_changed','Обновите черновик итогов.')
async def edit(db,p,webinar,body):
    row=await summary(db,webinar.id,True);version(row,body.expected_version)
    title,text=body.title.strip(),body.body.strip()
    if not title or not text or '\n' in title or '\r' in title:raise ApiError(422,'invalid_summary','Заполните заголовок одной строкой и текст итогов.')
    if row is None:
        row=WebinarSummary(foundation_id=p.foundation_id,webinar_id=webinar.id);db.add(row);await db.flush()
    else:row.draft_revision+=1;row.version+=1
    row.reviewed_revision=None
    db.add(WebinarSummaryRevision(summary_id=row.id,number=row.draft_revision,title=title,body=text,created_by_user_id=p.user_id))
    await db.flush();audit(db,p,'studio.summary.edit','webinar',webinar.id,('draft_revision',))
    return await view(db,p,webinar,row)
async def decide(db,p,webinar,body,action):
    row=await summary(db,webinar.id,True);exact_draft(row,body)
    if action=='review':row.reviewed_revision=row.draft_revision
    else:
        if row.reviewed_revision!=row.draft_revision:raise ApiError(409,'summary_review_required','Сначала проверьте эту версию итогов.')
        row.published_revision=row.draft_revision
    row.version+=1;await db.flush();audit(db,p,'studio.summary.'+action,'webinar',webinar.id,('revision',))
    return await view(db,p,webinar,row)
async def audience(db,p,webinar,row):
    rows=(await db.execute(select(WebinarEnrollment,User).join(User,User.id==WebinarEnrollment.user_id).where(WebinarEnrollment.webinar_id==webinar.id,WebinarEnrollment.foundation_id==p.foundation_id,WebinarEnrollment.state=='enrolled',User.foundation_id==p.foundation_id).order_by(User.id).limit(1001).with_for_update())).all()
    if len(rows)>1000:raise ApiError(422,'summary_audience_limit','Список участников превышает допустимый размер.')
    sent=set((await db.scalars(select(WebinarSummaryDelivery.recipient_id).where(WebinarSummaryDelivery.summary_id==row.id,WebinarSummaryDelivery.published_revision==row.published_revision))).all())
    members=[]
    for enrollment,user in rows:
        allowed,reason=await may_contact(db,p.foundation_id,user.id,'in_app','learning')
        if user.id in sent:allowed,reason=False,'already_sent'
        members.append(dict(user_id=str(user.id),display_name=user.display_name,enrollment_version=enrollment.version,eligible=allowed,reason=reason))
    return members
def preview_hash(row,members):return hashlib.sha256(json.dumps({'summary_id':str(row.id),'revision':row.published_revision,'members':members},sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
def published(row,body):
    version(row,body.expected_version)
    if not row or row.published_revision!=body.revision:raise ApiError(409,'summary_publication_changed','Обновите опубликованные итоги.')
async def preview(db,p,webinar,body):
    row=await summary(db,webinar.id,True);published(row,body)
    members=await audience(db,p,webinar,row)
    value=WebinarSummaryPreview(summary_id=row.id,published_revision=row.published_revision,actor_user_id=p.user_id,snapshot=members,preview_hash=preview_hash(row,members),expires_at=utcnow()+timedelta(minutes=15));db.add(value);await db.flush()
    return dict(id=value.id,published_revision=value.published_revision,members=members,eligible_count=sum(x['eligible'] for x in members),preview_hash=value.preview_hash,expires_at=value.expires_at)
async def send(db,p,webinar,body):
    row=await summary(db,webinar.id,True);published(row,body)
    value=await db.scalar(select(WebinarSummaryPreview).where(WebinarSummaryPreview.id==body.preview_id,WebinarSummaryPreview.summary_id==row.id,WebinarSummaryPreview.actor_user_id==p.user_id).with_for_update())
    if not value:raise ApiError(404,'summary_preview_not_found','Предпросмотр получателей не найден.')
    if value.consumed_at or value.expires_at<=utcnow():raise ApiError(409,'summary_preview_expired','Обновите предпросмотр получателей.')
    members=await audience(db,p,webinar,row)
    if value.published_revision!=row.published_revision or body.preview_hash!=value.preview_hash or preview_hash(row,members)!=value.preview_hash:raise ApiError(409,'summary_audience_changed','Участники или их настройки изменились. Обновите предпросмотр.')
    selected=[x for x in members if x['eligible']]
    if not selected:raise ApiError(409,'summary_no_recipients','Нет участников с разрешённой внутренней доставкой.')
    deliveries=[]
    for item in selected:
        delivery=WebinarSummaryDelivery(id=uuid4(),summary_id=row.id,published_revision=row.published_revision,recipient_id=UUID(item['user_id']),sender_user_id=p.user_id)
        outbox=enqueue_notice(db,p.foundation_id,delivery.recipient_id,'','',topic='learning',source={'kind':'webinar_summary','delivery_id':str(delivery.id)})
        delivery.outbox_id=outbox.id;db.add(delivery);deliveries.append(delivery.id)
    value.consumed_at=utcnow();await db.flush();audit(db,p,'studio.summary.send','webinar',webinar.id,('published_revision','audience'))
    return dict(state='queued',enqueued=len(deliveries),delivery_ids=deliveries)
