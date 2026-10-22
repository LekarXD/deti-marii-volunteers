"""Session channel for volunteer-scoped Telegram bot sessions.

Revision ID: b7e2c41d9a05
Revises: 5b7e2c9d4f10
"""
from alembic import op
import sqlalchemy as sa
revision = 'b7e2c41d9a05'
down_revision = '5b7e2c9d4f10'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('sessions', sa.Column('channel', sa.String(20), nullable=False, server_default='web'))
    op.create_check_constraint('session_channel', 'sessions', "channel IN ('web','telegram_bot') AND (channel = 'web' OR user_id IS NOT NULL)")


def downgrade():
    op.execute("UPDATE sessions SET revoked_at = now() WHERE channel <> 'web' AND revoked_at IS NULL")
    op.drop_constraint('session_channel', 'sessions', type_='check')
    op.drop_column('sessions', 'channel')
