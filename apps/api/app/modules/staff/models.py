"""Invitation intent only; memberships, factors and grants remain canonical core rows."""
from datetime import datetime
from uuid import UUID,uuid4
from sqlalchemy import CheckConstraint,DateTime,ForeignKey,Index,Integer,String,func,text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.core.db import Base

class StaffInvitation(Base):
    __tablename__='staff_invitations'
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    foundation_id:Mapped[UUID]=mapped_column(ForeignKey('foundations.id'),index=True)
    normalized_contact:Mapped[str]=mapped_column(String(320))
    token_hash:Mapped[str]=mapped_column(String(64),unique=True)
    grants:Mapped[list]=mapped_column(JSONB)
    invited_by_user_id:Mapped[UUID]=mapped_column(ForeignKey('users.id'))
    accepted_user_id:Mapped[UUID|None]=mapped_column(ForeignKey('users.id'))
    accepted_membership_id:Mapped[UUID|None]=mapped_column(ForeignKey('staff_memberships.id'))
    outbox_id:Mapped[UUID|None]=mapped_column(ForeignKey('outbox_messages.id'))
    state:Mapped[str]=mapped_column(String(30),default='pending')
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    accepted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    finalized_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    revoked_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    version:Mapped[int]=mapped_column(Integer,default=1)
    __table_args__=(CheckConstraint("state IN ('pending','accepted_pending_mfa','accepted','revoked')",name='ck_staff_invitation_state'),CheckConstraint('version>=1',name='ck_staff_invitation_version'),CheckConstraint("(state IN ('accepted_pending_mfa','accepted')) = (accepted_user_id IS NOT NULL AND accepted_membership_id IS NOT NULL)",name='ck_staff_invitation_accept_identity'),Index('uq_staff_invitation_pending_contact','foundation_id','normalized_contact',unique=True,postgresql_where=text("state IN ('pending','accepted_pending_mfa')")))
