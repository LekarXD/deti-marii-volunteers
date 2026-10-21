from datetime import datetime
from uuid import UUID,uuid4
from sqlalchemy import BigInteger,Boolean,DateTime,ForeignKey,Integer,String,Text,UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB,UUID as PGUUID
from sqlalchemy.orm import Mapped,mapped_column
from app.core.db import Base
from app.core.clock import utcnow

class NotificationPreference(Base):
    __tablename__='notification_preferences'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    no_contact:Mapped[bool]=mapped_column(Boolean,default=False)
    email_enabled:Mapped[bool]=mapped_column(Boolean,default=False)
    in_app_enabled:Mapped[bool]=mapped_column(Boolean,default=True)
    topics:Mapped[dict]=mapped_column(JSONB,default=lambda:dict(assignments=True,learning=True,messages=True,news=False),server_default='{"assignments":true,"learning":true,"messages":true,"news":false}')
    quiet_enabled:Mapped[bool]=mapped_column(Boolean,default=False,server_default='false')
    quiet_from:Mapped[int]=mapped_column(Integer,default=1320,server_default='1320')
    quiet_to:Mapped[int]=mapped_column(Integer,default=540,server_default='540')
    timezone:Mapped[str]=mapped_column(String(80),default='Europe/Moscow',server_default='Europe/Moscow')
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('foundation_id','user_id'),)

class NotificationTemplate(Base):
    __tablename__='notification_templates'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    key:Mapped[str]=mapped_column(String(100))
    channel:Mapped[str]=mapped_column(String(20))
    topic:Mapped[str]=mapped_column(String(30),default='messages',server_default='messages')
    subject:Mapped[str]=mapped_column(String(300))
    body:Mapped[str]=mapped_column(Text)
    state:Mapped[str]=mapped_column(String(20),default='draft')
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('foundation_id','key'),)

class NotificationTemplateVersion(Base):
    __tablename__='notification_template_versions'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    template_id:Mapped[UUID]=mapped_column(ForeignKey('notification_templates.id'))
    revision:Mapped[int]=mapped_column(BigInteger)
    topic:Mapped[str]=mapped_column(String(30),default='messages',server_default='messages')
    subject:Mapped[str]=mapped_column(String(300))
    body:Mapped[str]=mapped_column(Text)
    fields:Mapped[list]=mapped_column(JSONB)
    published_by:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    __table_args__=(UniqueConstraint('template_id','revision'),)

class NotificationAudiencePreview(Base):
    __tablename__='notification_audience_previews'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    actor_user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    template_version_id:Mapped[UUID]=mapped_column(ForeignKey('notification_template_versions.id'))
    snapshot:Mapped[list]=mapped_column(JSONB)
    preview_hash:Mapped[str]=mapped_column(String(64))
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    consumed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class NotificationDelivery(Base):
    __tablename__='notification_deliveries'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'))
    outbox_id:Mapped[UUID]=mapped_column(ForeignKey('outbox_messages.id'),unique=True)
    recipient_user_id:Mapped[UUID|None]=mapped_column(ForeignKey('users.id'))
    template_version_id:Mapped[UUID|None]=mapped_column(ForeignKey('notification_template_versions.id'))
    channel:Mapped[str]=mapped_column(String(30))
    state:Mapped[str]=mapped_column(String(40),default='queued')
    provider_message_id:Mapped[str|None]=mapped_column(String(200),unique=True)
    last_webhook_at:Mapped[int]=mapped_column(BigInteger,default=0)
    version:Mapped[int]=mapped_column(BigInteger,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class DeliveryAttempt(Base):
    __tablename__='delivery_attempts'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    delivery_id:Mapped[UUID]=mapped_column(ForeignKey('notification_deliveries.id'),index=True)
    attempt_number:Mapped[int]=mapped_column(Integer)
    state:Mapped[str]=mapped_column(String(40))
    error_code:Mapped[str|None]=mapped_column(String(100))
    started_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    __table_args__=(UniqueConstraint('delivery_id','attempt_number'),)

class NotificationWebhookReceipt(Base):
    __tablename__='notification_webhook_receipts'
    id:Mapped[UUID]=mapped_column(PGUUID(as_uuid=True),primary_key=True,default=uuid4)
    event_id:Mapped[str]=mapped_column(String(200),unique=True)
    body_hash:Mapped[str]=mapped_column(String(64))
    provider_message_id:Mapped[str]=mapped_column(String(200))
    state:Mapped[str]=mapped_column(String(30))
    received_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
