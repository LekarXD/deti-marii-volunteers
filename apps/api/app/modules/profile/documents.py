import asyncio
from sqlalchemy import select,func
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.models import Foundation,User
from app.modules.applications.service import check_version
from app.modules.assets.registry import create_generated_asset
from .models import ProfileDocument,ServiceTimeEntry
from .schemas import ProfileDocumentView
from . import assets
from .ledger import subject_lock

def document_view(row):
    return ProfileDocumentView(id=row.id,user_id=row.user_id,kind=row.kind,period_from=row.period_from,period_to=row.period_to,recipient=row.recipient,body=row.body,total_minutes=row.total_minutes,state=row.state,version=row.version,asset_id=row.asset_id,public_response=row.public_response,created_at=row.created_at)

async def build_snapshot(db,row):
    user=await db.get(User,row.user_id);foundation=await db.get(Foundation,row.foundation_id)
    entries=(await db.scalars(select(ServiceTimeEntry).where(ServiceTimeEntry.foundation_id==row.foundation_id,ServiceTimeEntry.user_id==row.user_id,ServiceTimeEntry.service_date>=row.period_from,ServiceTimeEntry.service_date<=row.period_to).order_by(ServiceTimeEntry.service_date,ServiceTimeEntry.created_at))).all()
    total=sum(entry.delta_minutes for entry in entries)
    if total<=0:raise ApiError(422,'document_no_confirmed_time','За этот период пока нет подтверждённых минут')
    return dict(document_id=str(row.id),kind=row.kind,foundation_name=foundation.name,display_name=user.display_name,recipient=row.recipient,period_from=row.period_from.strftime('%d.%m.%Y'),period_to=row.period_to.strftime('%d.%m.%Y'),total_minutes=total,entry_ids=[str(entry.id) for entry in entries],issued_at=utcnow().strftime('%d.%m.%Y'),body=row.body)

async def generate(db,principal,row):
    from .pdf import render_document
    row.snapshot=await build_snapshot(db,row);row.total_minutes=row.snapshot['total_minutes']
    content=await asyncio.to_thread(render_document,row.snapshot)
    asset=await create_generated_asset(db,principal,content_type='application/pdf',data=content,purpose='profile_document',resource_type='profile_document',resource_id=row.id)
    row.asset_id=asset.id;row.state='ready';await db.flush()
    return document_view(row)

async def request_document(db,principal,command):
    from .service import own_user
    user=await own_user(db,principal)
    if command.period_to>utcnow().date():raise ApiError(422,'future_document_period','Период должен закончиться не позже сегодняшнего дня')
    await subject_lock(db,principal.foundation_id,user.id)
    row=ProfileDocument(foundation_id=principal.foundation_id,user_id=user.id,kind=command.kind,period_from=command.period_from,period_to=command.period_to,recipient=command.recipient.strip(),body='',state='requested',version=1)
    if not row.recipient:raise ApiError(422,'document_recipient_required','Укажите, кому нужен документ')
    db.add(row);await db.flush()
    if row.kind=='certificate':return await generate(db,principal,row)
    return document_view(row)

async def review_document(db,principal,document_id,command):
    row=await db.scalar(select(ProfileDocument).where(ProfileDocument.id==document_id,ProfileDocument.foundation_id==principal.foundation_id))
    if row is None:raise ApiError(404,'document_not_found','Документ не найден')
    await subject_lock(db,principal.foundation_id,row.user_id)
    row=await db.scalar(select(ProfileDocument).where(ProfileDocument.id==document_id).with_for_update().execution_options(populate_existing=True));check_version(row.version,command.expected_version)
    if row.state not in ('requested','approved'):raise ApiError(409,'document_already_decided','Документ уже обработан')
    row.version+=1;row.public_response=command.public_response.strip();row.reviewed_by=principal.user_id
    if command.decision=='rejected':row.state='rejected';await db.flush();return document_view(row)
    if not command.body.strip():raise ApiError(422,'document_body_required','Напишите текст письма')
    row.body=command.body.strip();row.state='approved';await db.flush()
    return await generate(db,principal,row)
