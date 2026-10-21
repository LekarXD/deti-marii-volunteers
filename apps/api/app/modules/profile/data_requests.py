"""Own-data export and a reviewable deletion request, preserving retained facts."""
import io,json,zipfile
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.models import User
from app.modules.assets.registry import create_generated_asset
from app.modules.applications.service import check_version,own_application,application_view
from app.modules.applications.consents import consent_events
from .models import ProfileDataRequest
from .schemas import ProfileDataView
from . import assets

def data_view(row):
    return ProfileDataView(id=row.id,user_id=row.user_id,kind=row.kind,state=row.state,version=row.version,reason=row.reason,public_response=row.public_response,retention_note=row.retention_note,scheduled_for=row.scheduled_for,asset_id=row.asset_id,created_at=row.created_at,updated_at=row.updated_at)

async def own_export(db,principal):
    from .service import profile_view
    from .ledger import hours_view
    from app.modules.crm.service import own_availability
    profile=await profile_view(db,principal);hours=await hours_view(db,principal);availability=await own_availability(db,principal)
    application=await own_application(db,principal,required=False)
    events=await consent_events(db,principal.foundation_id,user_id=principal.user_id)
    data=dict(format_version=1,generated_at=utcnow().isoformat(),profile=profile.model_dump(mode='json'),hours=hours.model_dump(mode='json'),availability=availability.model_dump(mode='json'),application=(await application_view(db,application)).model_dump(mode='json') if application else None,consents=[dict(id=str(event.id),purpose=event.purpose,granted=event.granted,document=event.document,document_version=event.document_version,source=event.source,created_at=event.created_at.isoformat()) for event in events])
    # Only domain self projections. Private staff notes never enter the archive.
    encoded=json.dumps(data,ensure_ascii=False,indent=2).encode()
    if len(encoded)>10*1024*1024:raise ApiError(413,'export_review_required','Объём архива требует подготовки сотрудником')
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:archive.writestr('my-data.json',encoded)
    return output.getvalue()

async def create_request(db,principal,command):
    from .service import own_user
    user=await own_user(db,principal,True)
    if command.kind=='deletion':
        pending=await db.scalar(select(ProfileDataRequest.id).where(ProfileDataRequest.foundation_id==principal.foundation_id,ProfileDataRequest.user_id==user.id,ProfileDataRequest.kind=='deletion',ProfileDataRequest.state.in_(('requested','in_review','approved'))).limit(1))
        if pending:raise ApiError(409,'deletion_request_pending','Запрос на удаление уже находится у сотрудника')
    row=ProfileDataRequest(foundation_id=principal.foundation_id,user_id=user.id,kind=command.kind,reason=command.reason.strip(),state='requested',version=1)
    db.add(row);await db.flush()
    if row.kind=='export':
        content=await own_export(db,principal)
        asset=await create_generated_asset(db,principal,content_type='application/zip',data=content,purpose='profile_data_request',resource_type='profile_data_request',resource_id=row.id)
        row.asset_id=asset.id;row.state='ready';row.public_response='Архив готов к скачиванию в профиле.';await db.flush()
    return data_view(row)

async def cancel_request(db,principal,request_id,command):
    row=await db.scalar(select(ProfileDataRequest).where(ProfileDataRequest.id==request_id,ProfileDataRequest.foundation_id==principal.foundation_id,ProfileDataRequest.user_id==principal.user_id).with_for_update())
    if row is None:raise ApiError(404,'data_request_not_found','Запрос не найден')
    check_version(row.version,command.expected_version)
    if row.kind!='deletion' or row.state not in ('requested','in_review','approved'):raise ApiError(409,'data_request_not_cancellable','Этот запрос уже нельзя отменить')
    row.state='cancelled';row.version+=1;row.updated_at=utcnow();await db.flush();return data_view(row)

async def review_request(db,principal,request_id,command):
    row=await db.scalar(select(ProfileDataRequest).where(ProfileDataRequest.id==request_id,ProfileDataRequest.foundation_id==principal.foundation_id).with_for_update())
    if row is None:raise ApiError(404,'data_request_not_found','Запрос не найден')
    check_version(row.version,command.expected_version)
    if row.kind!='deletion' or row.state not in ('requested','in_review','approved'):raise ApiError(409,'data_request_decided','Запрос уже обработан')
    if command.decision=='approved' and (not command.scheduled_for or command.scheduled_for<utcnow().date() or not command.retention_note.strip()):raise ApiError(422,'deletion_plan_required','Укажите дату обработки и какие данные потребуется сохранить')
    if command.decision=='completed':
        # Completion is evidence about account erasure, not a label that executes it.
        user=await db.get(User,row.user_id)
        if row.state!='approved' or user.account_state!='deleted':raise ApiError(409,'deletion_not_executed','Аккаунт ещё не обработан по плану удаления')
    row.state=command.decision;row.version+=1;row.reviewed_by=principal.user_id;row.public_response=command.public_response.strip();row.retention_note=command.retention_note.strip();row.scheduled_for=command.scheduled_for;row.updated_at=utcnow()
    await db.flush();return data_view(row)
