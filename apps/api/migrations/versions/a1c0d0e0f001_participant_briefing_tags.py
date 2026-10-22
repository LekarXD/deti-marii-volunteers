"""Participant memo chips: communication, support and interests tags on the briefing.

Revision ID: a1c0d0e0f001
Revises: 5b7e2c9d4f10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = 'a1c0d0e0f001'
down_revision = '5b7e2c9d4f10'
branch_labels = None
depends_on = None

COLUMNS = ('communication_tags', 'support_tags', 'interests_tags')


def upgrade():
    for name in COLUMNS:
        op.add_column('participant_briefings', sa.Column(name, postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))


def downgrade():
    for name in reversed(COLUMNS):
        op.drop_column('participant_briefings', name)
