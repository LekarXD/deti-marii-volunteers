"""Prize catalog and requests. Requests reserve points and stock until issued, rejected or cancelled."""
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.models import MediaAsset,User
from app.modules.applications.service import check_version
from .models import Prize,PrizeRequest,PointsEntry
from .schemas import PrizeView,PrizeRequestView,PointsAdjustmentView
from .ledger import subject_lock,points_view

def prize_view(row):
    return PrizeView(id=row.id,title=row.title,description=row.description,price_points=row.price_points,stock=row.stock,visible=row.visible,version=row.version,photo_asset_id=row.photo_asset_id)

async def request_view(db,row,staff=False):
    prize=await db.get(Prize,row.prize_id)
    view=PrizeRequestView(id=row.id,user_id=row.user_id,prize_id=row.prize_id,prize_title=prize.title,points=row.points,state=row.state,version=row.version,reason=row.reason,created_at=row.created_at,updated_at=row.updated_at)
    return view.model_copy(update={'display_name':(await db.get(User,row.user_id)).display_name}) if staff else view

async def catalog(db,principal,staff=False):
    query=select(Prize).where(Prize.foundation_id==principal.foundation_id)
    if not staff:query=query.where(Prize.visible.is_(True))
    return [prize_view(row) for row in (await db.scalars(query.order_by(Prize.price_points,Prize.created_at).limit(200))).all()]

async def visible_prize(db,principal,prize_id):
    row=await db.scalar(select(Prize).where(Prize.id==prize_id,Prize.foundation_id==principal.foundation_id,Prize.visible.is_(True)))
    if row is None:raise ApiError(404,'prize_not_found','Приз не найден')
    return row

async def check_photo(db,principal,row,asset_id):
    if asset_id is None or asset_id==row.photo_asset_id:return
    asset=await db.scalar(select(MediaAsset).where(MediaAsset.id==asset_id,MediaAsset.foundation_id==principal.foundation_id))
    if asset is None or asset.purpose!='prize_photo' or asset.resource_type!='prize' or asset.resource_id!=row.id or asset.state!='ready':raise ApiError(422,'prize_photo_invalid','Сначала загрузите фото этого приза')

async def create_prize(db,principal,command):
    row=Prize(foundation_id=principal.foundation_id,title=command.title.strip(),description=command.description.strip(),price_points=command.price_points,stock=command.stock,visible=command.visible,version=1)
    if not row.title:raise ApiError(422,'empty_title','Укажите название приза')
    if command.photo_asset_id:raise ApiError(422,'prize_photo_invalid','Фото добавляется после создания приза')
    db.add(row);await db.flush();return prize_view(row)

async def update_prize(db,principal,prize_id,command):
    row=await db.scalar(select(Prize).where(Prize.id==prize_id,Prize.foundation_id==principal.foundation_id).with_for_update())
    if row is None:raise ApiError(404,'prize_not_found','Приз не найден')
    check_version(row.version,command.expected_version)
    await check_photo(db,principal,row,command.photo_asset_id)
    row.title=command.title.strip();row.description=command.description.strip();row.price_points=command.price_points;row.stock=command.stock;row.visible=command.visible;row.photo_asset_id=command.photo_asset_id
    if not row.title:raise ApiError(422,'empty_title','Укажите название приза')
    row.version+=1;row.updated_at=utcnow();await db.flush();return prize_view(row)

async def photo_intent(db,principal,prize_id,command):
    from app.modules.assets.registry import create_upload_intent
    row=await db.scalar(select(Prize).where(Prize.id==prize_id,Prize.foundation_id==principal.foundation_id))
    if row is None:raise ApiError(404,'prize_not_found','Приз не найден')
    return await create_upload_intent(db,principal,content_type=command.content_type,expected_size=command.expected_size,checksum=command.checksum,purpose='prize_photo',resource_type='prize',resource_id=row.id)

async def locked_prize(db,prize_id):
    return await db.scalar(select(Prize).where(Prize.id==prize_id).with_for_update().execution_options(populate_existing=True))

async def request_prize(db,principal,command):
    from .service import own_user
    user=await own_user(db,principal)
    await visible_prize(db,principal,command.prize_id)
    # One per-subject order with the hours ledger, then the prize row: balance and stock are checked together.
    await subject_lock(db,principal.foundation_id,user.id)
    prize=await locked_prize(db,command.prize_id)
    if not prize.visible:raise ApiError(404,'prize_not_found','Приз не найден')
    if prize.stock<1:raise ApiError(409,'prize_out_of_stock','Этот приз закончился')
    balance=(await points_view(db,principal.foundation_id,user.id)).balance
    if balance<prize.price_points:raise ApiError(409,'points_insufficient','Пока не хватает баллов',current_version=balance)
    prize.stock-=1;prize.version+=1;prize.updated_at=utcnow()
    row=PrizeRequest(foundation_id=principal.foundation_id,user_id=user.id,prize_id=prize.id,points=prize.price_points,state='requested',version=1,reason='')
    db.add(row);await db.flush();return await request_view(db,row)

async def own_requests(db,principal):
    rows=(await db.scalars(select(PrizeRequest).where(PrizeRequest.foundation_id==principal.foundation_id,PrizeRequest.user_id==principal.user_id).order_by(PrizeRequest.created_at.desc()).limit(100))).all()
    return [await request_view(db,row) for row in rows]

async def queue(db,principal):
    rows=(await db.scalars(select(PrizeRequest).where(PrizeRequest.foundation_id==principal.foundation_id).order_by(PrizeRequest.created_at.desc()).limit(200))).all()
    return [await request_view(db,row,True) for row in rows]

async def close_request(db,principal,request_id,expected_version,state,reason='',own=False):
    query=select(PrizeRequest).where(PrizeRequest.id==request_id,PrizeRequest.foundation_id==principal.foundation_id)
    if own:query=query.where(PrizeRequest.user_id==principal.user_id)
    row=await db.scalar(query)
    if row is None:raise ApiError(404,'prize_request_not_found','Заявка не найдена')
    if not own and row.user_id==principal.user_id:raise ApiError(403,'self_prize_review_forbidden','Приз себе выдаёт другой сотрудник')
    await subject_lock(db,principal.foundation_id,row.user_id)
    prize=await locked_prize(db,row.prize_id)
    row=await db.scalar(select(PrizeRequest).where(PrizeRequest.id==request_id).with_for_update().execution_options(populate_existing=True))
    check_version(row.version,expected_version)
    if row.state!='requested':raise ApiError(409,'prize_request_closed','Заявка уже закрыта')
    row.state=state;row.reason=reason.strip();row.version+=1;row.updated_at=utcnow()
    if not own:row.decided_by=principal.user_id
    # Issued prizes are never taken back; rejected and cancelled ones return to stock.
    if state!='issued':prize.stock+=1;prize.version+=1;prize.updated_at=utcnow()
    await db.flush();return await request_view(db,row,not own)

async def adjust_points(db,principal,command):
    if command.user_id==principal.user_id:raise ApiError(403,'self_points_adjustment_forbidden','Свои баллы меняет другой сотрудник')
    user=await db.scalar(select(User).where(User.id==command.user_id,User.foundation_id==principal.foundation_id,User.account_state=='active'))
    if user is None:raise ApiError(404,'user_not_found','Волонтёр не найден')
    await subject_lock(db,principal.foundation_id,user.id)
    row=PointsEntry(foundation_id=principal.foundation_id,user_id=user.id,kind='adjustment',bonus_key=None,points=command.points,reason=command.reason.strip(),actor_id=principal.actor_id)
    db.add(row);await db.flush()
    return PointsAdjustmentView(id=row.id,user_id=row.user_id,points=row.points,reason=row.reason,created_at=row.created_at)
