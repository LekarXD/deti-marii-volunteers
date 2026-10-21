from uuid import uuid4
from sqlalchemy import select
from .models import Conversation, ConversationMember, Message

async def seed_messaging(db,foundation_id,identities):
    """Invented local fixture; no external notification is enqueued."""
    key=f"fixture:g1:messaging:{foundation_id}"
    if await db.scalar(select(Conversation.id).where(Conversation.direct_key==key)):
        return
    owner=identities['coordinator@example.test']['user_id']
    from uuid import UUID
    conversation=Conversation(id=uuid4(),foundation_id=foundation_id,title="Команда фонда",kind="group",direct_key=key,created_by_user_id=UUID(owner),last_seq=1)
    db.add(conversation)
    await db.flush()
    db.add_all([ConversationMember(conversation_id=conversation.id,user_id=UUID(identity['user_id'])) for identity in identities.values()])
    db.add(Message(conversation_id=conversation.id,author_user_id=UUID(owner),seq=1,text="Добро пожаловать в учебный чат фонда. Здесь можно обсудить подготовку и задать вопрос координатору."))
