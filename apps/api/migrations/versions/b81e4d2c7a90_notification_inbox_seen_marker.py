"""Seen marker for the volunteer's derived notification inbox (the bell in the header).

Revision ID: b81e4d2c7a90
Revises: a7c3802c5582
"""
from alembic import op
import sqlalchemy as sa

revision = 'b81e4d2c7a90'
down_revision = 'a7c3802c5582'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('notification_preferences', sa.Column('inbox_seen_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column('notification_preferences', 'inbox_seen_at')
