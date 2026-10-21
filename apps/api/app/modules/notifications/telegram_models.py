"""Private Telegram identity proof; notification preferences remain separate."""
from datetime import datetime
from uuid import UUID,uuid4
from sqlalchemy import BigInteger,CheckConstraint,DateTime,ForeignKey,ForeignKeyConstraint,Index,Integer,String,Text,text
from sqlalchemy.orm import Mapped,mapped_column
from app.core.clock import utcnow
from app.core.db import Base

class TelegramLinkToken(Base):
    __tablename__='telegram_link_tokens'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    session_id:Mapped[UUID]=mapped_column(ForeignKey('sessions.id'))
    token_hash:Mapped[str]=mapped_column(String(64),unique=True)
    token_cipher:Mapped[str|None]=mapped_column(Text)
    purpose:Mapped[str]=mapped_column(String(30),default='telegram_bind')
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    consumed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    outcome:Mapped[str|None]=mapped_column(String(20))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(ForeignKeyConstraint(['user_id','foundation_id'],['users.id','users.foundation_id']),CheckConstraint("purpose='telegram_bind' AND (outcome IS NULL OR outcome IN ('linked','conflict')) AND (outcome IS NULL OR consumed_at IS NOT NULL) AND expires_at>created_at",name='ck_telegram_link_token'),Index('ix_telegram_link_token_owner','foundation_id','user_id','session_id','created_at'))

class TelegramBinding(Base):
    __tablename__='telegram_bindings'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    telegram_user_id:Mapped[int]=mapped_column(BigInteger)
    chat_id:Mapped[int]=mapped_column(BigInteger)
    version:Mapped[int]=mapped_column(Integer,default=1)
    verified_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    __table_args__=(ForeignKeyConstraint(['user_id','foundation_id'],['users.id','users.foundation_id']),CheckConstraint('telegram_user_id>0 AND chat_id=telegram_user_id AND version>0',name='ck_telegram_binding_private'),Index('uq_telegram_binding_active_user','foundation_id','user_id',unique=True,postgresql_where=text('revoked_at IS NULL')),Index('uq_telegram_binding_active_identity','foundation_id','telegram_user_id',unique=True,postgresql_where=text('revoked_at IS NULL')))
