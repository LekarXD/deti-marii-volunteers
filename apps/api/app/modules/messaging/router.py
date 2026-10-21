from uuid import UUID
from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.auth import Principal, get_principal
from app.core.db import get_db
from app.core.errors import ApiError
from app.core.models import MediaAsset
from app.modules.assets.service import asset_content
from . import service
from .models import ConversationMember, Message, MessageAsset
from .schemas import ConversationCreate, ConversationPage, ConversationSyncView, ConversationView, DirectCreate, MemberCommand, MembershipView, MessageCreate, MessagePage, MessageView, ReadCommand, ReadCursorView, DeliveryReadinessView
router=APIRouter(prefix="/api/v1/conversations",tags=["messaging"])

@router.get("",operation_id="conversation_list",response_model=ConversationPage)
async def list_conversations(limit:int=Query(30,ge=1,le=50),cursor:str|None=Query(None,max_length=500),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.conversation_list(db,principal,limit,cursor)

@router.post("",operation_id="conversation_create",response_model=ConversationView)
async def create_conversation(body:ConversationCreate,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    result=await service.create_group(db,principal,body,request.headers.get("Idempotency-Key"))
    await db.commit()
    return result

@router.post("/direct",operation_id="conversation_direct",response_model=ConversationView)
async def direct(body:DirectCreate,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    result=await service.create_direct(db,principal,body.recipient_id,request.headers.get("Idempotency-Key"))
    await db.commit()
    return result

@router.get("/assets/{asset_id}/content",operation_id="conversation_attachment_content")
async def attachment(asset_id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    linked=(await db.execute(select(MediaAsset,Message.conversation_id).join(MessageAsset,MessageAsset.asset_id==MediaAsset.id).join(Message,Message.id==MessageAsset.message_id).join(ConversationMember,ConversationMember.conversation_id==Message.conversation_id).where(MediaAsset.id==asset_id,MediaAsset.foundation_id==principal.foundation_id,ConversationMember.user_id==principal.user_id,ConversationMember.revoked_at.is_(None)).limit(1))).first()
    if not linked:
        raise ApiError(404,"asset_not_found","Файл не найден")
    await service.conversation_access(db,principal,linked[1])
    return await asset_content(db,linked[0])

@router.get("/{conversation_id}",operation_id="conversation_get",response_model=ConversationView)
async def detail(conversation_id:UUID,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    return await service.conversation_view(db,principal,await service.conversation_access(db,principal,conversation_id))

@router.get("/{conversation_id}/messages",operation_id="conversation_messages",response_model=MessagePage)
async def messages(conversation_id:UUID,before_seq:int|None=Query(None,ge=1),after_seq:int|None=Query(None,ge=0),limit:int=Query(50,ge=1,le=100),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    conversation=await service.conversation_access(db,principal,conversation_id)
    if before_seq is not None and after_seq is not None:
        raise ApiError(422,"invalid_pagination","Выберите одно направление истории")
    query=select(Message).where(Message.conversation_id==conversation.id)
    if before_seq is not None:
        query=query.where(Message.seq<before_seq)
    if after_seq is not None:
        query=query.where(Message.seq>after_seq)
    query=query.order_by(Message.seq.asc() if after_seq is not None else Message.seq.desc()).limit(limit+1)
    rows=(await db.scalars(query)).all()
    has_more=len(rows)>limit
    rows=rows[:limit]
    rows=rows if after_seq is not None else list(reversed(rows))
    return {"items":await service.message_views(db,rows),"next_before_seq":rows[0].seq if has_more and rows and after_seq is None else None,"has_more":has_more,"revision":conversation.version}

@router.post("/{conversation_id}/messages",operation_id="conversation_send",response_model=MessageView)
async def send(conversation_id:UUID,body:MessageCreate,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    result=await service.send(db,principal,conversation_id,body,request.headers.get("Idempotency-Key"))
    await db.commit()
    return result

@router.put("/{conversation_id}/read-cursor",operation_id="conversation_read",response_model=ReadCursorView)
async def read(conversation_id:UUID,body:ReadCommand,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    result=await service.set_read(db,principal,conversation_id,body.last_read_seq)
    await db.commit()
    return result

@router.get("/{conversation_id}/sync",operation_id="conversation_sync",response_model=ConversationSyncView)
async def sync(conversation_id:UUID,after_seq:int=Query(0,ge=0),principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    conversation=await service.conversation_access(db,principal,conversation_id)
    rows=(await db.scalars(select(Message).where(Message.conversation_id==conversation.id,Message.seq>after_seq).order_by(Message.seq).limit(101))).all()
    return {"conversation":await service.conversation_view(db,principal,conversation),"messages":await service.message_views(db,rows[:100]),"has_more":len(rows)>100,"next_after_seq":rows[min(99,len(rows)-1)].seq if rows else after_seq}

@router.post("/{conversation_id}/members",operation_id="conversation_member_add",response_model=MembershipView)
async def member_add(conversation_id:UUID,body:MemberCommand,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    result=await service.change_member(db,principal,conversation_id,body,True,request.headers.get("Idempotency-Key"))
    await db.commit()
    return result

@router.post("/{conversation_id}/members/revoke",operation_id="conversation_member_revoke",response_model=MembershipView)
async def member_revoke(conversation_id:UUID,body:MemberCommand,request:Request,principal:Principal=Depends(get_principal),db:AsyncSession=Depends(get_db)):
    result=await service.change_member(db,principal,conversation_id,body,False,request.headers.get("Idempotency-Key"))
    await db.commit()
    return result

@router.get("/delivery/email/readiness",operation_id="email_delivery_readiness",response_model=DeliveryReadinessView)
async def delivery_readiness(principal:Principal=Depends(get_principal)):
    if not principal.has_permission("integrations.manage"):
        raise ApiError(403,"permission_denied","Недостаточно прав")
    from app.integrations.delivery.email import readiness
    return readiness()
