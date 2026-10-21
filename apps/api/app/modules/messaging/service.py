from app.core.paths import public_path
import base64
import binascii
import json
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import and_, func, or_, select, text
from app.core.audit import audit
from app.core.auth import authz_guard
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.idempotency import begin_command, finish_command
from app.core.models import MediaAsset, StaffMembership, User
from app.modules.assets.service import require_asset
from .models import Conversation, ConversationMember, Message, MessageAsset, ReadCursor

async def conversation_access(db, principal, conversation_id, lock=False):
    if principal.user_id is None:
        raise ApiError(403, "verified_account_required", "Подтвердите почту, чтобы открыть сообщения")
    query = select(Conversation).join(ConversationMember, ConversationMember.conversation_id == Conversation.id).where(Conversation.id == conversation_id, Conversation.foundation_id == principal.foundation_id, ConversationMember.user_id == principal.user_id, ConversationMember.revoked_at.is_(None))
    if lock:
        query = query.with_for_update(of=Conversation)
    conversation = await db.scalar(query)
    if conversation is None:
        raise ApiError(404, "conversation_not_found", "Диалог не найден")
    if lock:
        membership = await db.scalar(select(ConversationMember.id).where(ConversationMember.conversation_id==conversation_id,ConversationMember.user_id==principal.user_id,ConversationMember.revoked_at.is_(None)))
        if membership is None:
            raise ApiError(404,"conversation_not_found","Диалог не найден")
    return conversation

async def message_views(db, messages):
    if not messages:
        return []
    ids = [m.id for m in messages]
    authors = {u.id:u.display_name for u in (await db.scalars(select(User).where(User.id.in_({m.author_user_id for m in messages if m.author_user_id})))).all()}
    assets = (await db.execute(select(MessageAsset.message_id, MediaAsset).join(MediaAsset,MediaAsset.id==MessageAsset.asset_id).where(MessageAsset.message_id.in_(ids),MediaAsset.state=="ready"))).all()
    by_message = {}
    for message_id,asset in assets:
        by_message.setdefault(message_id,[]).append({"id":str(asset.id),"content_type":asset.content_type,"size":asset.expected_size,"content_url":public_path(f"/api/v1/conversations/assets/{asset.id}/content")})
    return [{"id":str(m.id),"conversation_id":str(m.conversation_id),"author_user_id":str(m.author_user_id) if m.author_user_id else None,"author_name":authors.get(m.author_user_id,"Фонд «Дети Марии»"),"seq":m.seq,"text":m.text,"created_at":m.created_at.isoformat(),"assets":by_message.get(m.id,[])} for m in messages]

async def conversation_view(db, principal, conversation):
    members = (await db.execute(select(User.id,User.display_name).join(ConversationMember,ConversationMember.user_id==User.id).where(ConversationMember.conversation_id==conversation.id,ConversationMember.revoked_at.is_(None)).order_by(User.display_name,User.id))).all()
    cursor = await db.get(ReadCursor,(conversation.id,principal.user_id))
    last_read = cursor.last_read_seq if cursor else 0
    unread = await db.scalar(select(func.count()).select_from(Message).where(Message.conversation_id==conversation.id,Message.seq>last_read,or_(Message.author_user_id.is_(None),Message.author_user_id!=principal.user_id)))
    last = await db.scalar(select(Message).where(Message.conversation_id==conversation.id).order_by(Message.seq.desc()).limit(1))
    last_view = await message_views(db,[last] if last else [])
    title = conversation.title
    if conversation.kind == "direct":
        title = next((name for uid,name in members if uid!=principal.user_id),title)
    return {"id":str(conversation.id),"title":title,"kind":conversation.kind,"version":conversation.version,"last_seq":conversation.last_seq,"last_read_seq":last_read,"unread_count":unread,"last_message":last_view[0] if last_view else None,"members":[{"user_id":str(uid),"display_name":name} for uid,name in members],"allowed_actions":(["send"] if conversation.kind!="system" else [])+(["manage_members"] if principal.has_permission("messaging.manage") and conversation.kind=="group" else []),"external_delivery":"unavailable"}

async def validate_users(db, principal, users):
    found=set((await db.scalars(select(User.id).where(User.id.in_(users),User.foundation_id==principal.foundation_id,User.account_state=="active"))).all())
    if found != set(users):
        raise ApiError(422,"invalid_members","Проверьте участников диалога")

async def create_group(db, principal, body, key):
    await authz_guard(db,principal)
    if not principal.has_permission("messaging.manage"):
        raise ApiError(403,"permission_denied","Недостаточно прав")
    replay=await begin_command(db,principal,"messaging.group.create",key,body.model_dump(mode="json"))
    if replay is not None:
        return replay
    users=set(body.member_ids)|{principal.user_id}
    await validate_users(db,principal,users)
    conversation=Conversation(id=uuid4(),foundation_id=principal.foundation_id,title=body.title.strip(),kind="group",created_by_user_id=principal.user_id)
    db.add(conversation)
    await db.flush()
    db.add_all([ConversationMember(conversation_id=conversation.id,user_id=uid) for uid in users])
    await db.flush()
    audit(db,principal,"messaging.group.create","conversation",conversation.id,("members","title"))
    return await finish_command(db,principal,"messaging.group.create",key,await conversation_view(db,principal,conversation))

async def create_direct(db,principal,recipient_id,key):
    await authz_guard(db,principal)
    if principal.user_id is None or recipient_id==principal.user_id:
        raise ApiError(422,"invalid_recipient","Выберите собеседника")
    await validate_users(db,principal,{principal.user_id,recipient_id})
    if not principal.has_permission("messaging.manage"):
        active_staff=await db.scalar(select(StaffMembership.id).where(StaffMembership.user_id==recipient_id,StaffMembership.foundation_id==principal.foundation_id,StaffMembership.revoked_at.is_(None)))
        if not active_staff:
            raise ApiError(404,"recipient_not_found","Собеседник недоступен")
    replay=await begin_command(db,principal,"messaging.direct.create",key,{"recipient_id":str(recipient_id)})
    if replay is not None:
        return replay
    pair=":".join(sorted([str(principal.user_id),str(recipient_id)]))
    direct_key=f"{principal.foundation_id}:{pair}"
    from app.core.crypto import digest
    await db.execute(text("SELECT pg_advisory_xact_lock(:key)"),{"key":int(digest(direct_key)[:15],16)})
    conversation=await db.scalar(select(Conversation).where(Conversation.direct_key==direct_key))
    if conversation is None:
        conversation=Conversation(id=uuid4(),foundation_id=principal.foundation_id,title="Личный диалог",kind="direct",direct_key=direct_key,created_by_user_id=principal.user_id)
        db.add(conversation)
        await db.flush()
        db.add_all([ConversationMember(conversation_id=conversation.id,user_id=uid) for uid in (principal.user_id,recipient_id)])
        await db.flush()
        audit(db,principal,"messaging.direct.create","conversation",conversation.id,("members",))
    await conversation_access(db,principal,conversation.id)
    return await finish_command(db,principal,"messaging.direct.create",key,await conversation_view(db,principal,conversation))

async def send(db,principal,conversation_id,body,key):
    await authz_guard(db,principal)
    conversation=await conversation_access(db,principal,conversation_id,lock=True)
    if conversation.kind=="system":
        raise ApiError(403,"conversation_read_only","Это канал уведомлений фонда")
    operation=f"messaging.send:{conversation_id}"
    replay=await begin_command(db,principal,operation,key,body.model_dump(mode="json"))
    if replay is not None:
        return replay
    assets=[]
    for aid in body.asset_ids:
        asset=await require_asset(db,principal,aid)
        # Domain-bound participant photos cannot be forwarded through a chat.
        if asset.access_permission or asset.purpose != "generic":
            raise ApiError(403,"asset_not_shareable","Для сообщения загрузите отдельный файл")
        if asset.content_type.startswith("image/") and body.photo_policy != "no_people":
            raise ApiError(422,"photo_privacy_clearance_required","Фото людей в чат не отправляем. Подтвердите, что на изображении нет людей, либо выберите другой файл")
        assets.append(asset)
    conversation.last_seq+=1
    conversation.version+=1
    conversation.updated_at=utcnow()
    message=Message(id=uuid4(),conversation_id=conversation.id,author_user_id=principal.user_id,seq=conversation.last_seq,text=body.text,photo_policy=body.photo_policy)
    db.add(message)
    await db.flush()
    for asset in assets:
        asset.access_permission="messaging.attachment"
        db.add(MessageAsset(message_id=message.id,asset_id=asset.id))
    audit(db,principal,"messaging.send","message",message.id,("text","assets"))
    await db.flush()
    return await finish_command(db,principal,operation,key,(await message_views(db,[message]))[0])

async def set_read(db,principal,conversation_id,last_read_seq):
    await authz_guard(db,principal)
    conversation=await conversation_access(db,principal,conversation_id,lock=True)
    if last_read_seq>conversation.last_seq:
        raise ApiError(422,"invalid_read_cursor","Сообщение ещё не существует")
    cursor=await db.get(ReadCursor,(conversation.id,principal.user_id))
    if cursor is None:
        cursor=ReadCursor(conversation_id=conversation.id,user_id=principal.user_id,last_read_seq=last_read_seq)
        db.add(cursor)
    else:
        cursor.last_read_seq=max(cursor.last_read_seq,last_read_seq)
        cursor.updated_at=utcnow()
    await db.flush()
    view=await conversation_view(db,principal,conversation)
    return {"last_read_seq":cursor.last_read_seq,"unread_count":view['unread_count']}

async def change_member(db,principal,conversation_id,body,active,key):
    await authz_guard(db,principal)
    conversation=await conversation_access(db,principal,conversation_id,lock=True)
    if not principal.has_permission("messaging.manage") or conversation.kind!="group":
        raise ApiError(403,"permission_denied","Недостаточно прав")
    operation=f"messaging.member:{conversation_id}:{active}"
    replay=await begin_command(db,principal,operation,key,body.model_dump(mode="json"))
    if replay is not None:
        return replay
    if conversation.version!=body.expected_version:
        raise ApiError(409,"version_conflict","Состав диалога изменился",current_version=conversation.version)
    await validate_users(db,principal,{body.user_id})
    member=await db.scalar(select(ConversationMember).where(ConversationMember.conversation_id==conversation.id,ConversationMember.user_id==body.user_id))
    if active:
        if member:
            member.revoked_at=None
        else:
            db.add(ConversationMember(conversation_id=conversation.id,user_id=body.user_id))
    elif member:
        member.revoked_at=utcnow()
    conversation.version+=1
    conversation.updated_at=utcnow()
    audit(db,principal,"messaging.member.change","conversation",conversation.id,("members",))
    return await finish_command(db,principal,operation,key,{"version":conversation.version,"user_id":str(body.user_id),"active":active})

async def conversation_list(db,principal,limit,cursor):
    if principal.user_id is None:
        return {"items":[],"next_cursor":None}
    query=select(Conversation).join(ConversationMember,ConversationMember.conversation_id==Conversation.id).where(Conversation.foundation_id==principal.foundation_id,ConversationMember.user_id==principal.user_id,ConversationMember.revoked_at.is_(None))
    if cursor:
        try:
            data=json.loads(base64.urlsafe_b64decode(cursor.encode()))
            stamp,identity=datetime.fromisoformat(data[0]),UUID(data[1])
            if stamp.tzinfo is None:
                raise ValueError()
        except (ValueError,TypeError,IndexError,KeyError,binascii.Error,json.JSONDecodeError):
            raise ApiError(422,"invalid_cursor","Некорректная страница")
        query=query.where(or_(Conversation.created_at<stamp,and_(Conversation.created_at==stamp,Conversation.id<identity)))
    rows=(await db.scalars(query.order_by(Conversation.created_at.desc(),Conversation.id.desc()).limit(limit+1))).all()
    selected=rows[:limit]
    next_cursor=None
    if len(rows)>limit:
        last=selected[-1]
        next_cursor=base64.urlsafe_b64encode(json.dumps([last.created_at.isoformat(),str(last.id)]).encode()).decode()
    return {"items":[await conversation_view(db,principal,c) for c in selected],"next_cursor":next_cursor}
