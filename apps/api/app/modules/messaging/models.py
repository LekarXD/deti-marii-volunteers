from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base
from app.core.clock import utcnow

class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    foundation_id: Mapped[UUID] = mapped_column(ForeignKey("foundations.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20))
    direct_key: Mapped[str | None] = mapped_column(String(200), unique=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    version: Mapped[int] = mapped_column(BigInteger, default=1)
    last_seq: Mapped[int] = mapped_column(BigInteger, default=0)
    __table_args__ = (CheckConstraint("kind IN ('direct','group','system')", name="conversation_kind"), Index("ix_conversation_page", "foundation_id", "created_at", "id"))

class ConversationMember(Base):
    __tablename__ = "conversation_members"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("conversation_id", "user_id"),)

class Message(Base):
    __tablename__ = "messages"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"), index=True)
    author_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    source_outbox_id: Mapped[UUID | None] = mapped_column(ForeignKey("outbox_messages.id"), unique=True)
    photo_policy: Mapped[str | None] = mapped_column(String(30))
    seq: Mapped[int] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (UniqueConstraint("conversation_id", "seq"), CheckConstraint("length(text) <= 8000", name="message_text_length"))

class MessageAsset(Base):
    __tablename__ = "message_assets"
    message_id: Mapped[UUID] = mapped_column(ForeignKey("messages.id"), primary_key=True)
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("media_assets.id"), primary_key=True)

class ReadCursor(Base):
    __tablename__ = "read_cursors"
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("conversations.id"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    last_read_seq: Mapped[int] = mapped_column(BigInteger, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint("last_read_seq >= 0", name="read_cursor_nonnegative"),)
