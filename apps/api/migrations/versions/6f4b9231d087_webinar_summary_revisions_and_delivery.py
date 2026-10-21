"""Immutable webinar summary revisions and explicit previewed delivery.

Revision ID: 6f4b9231d087
Revises: 84fc8b53ac5d
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='6f4b9231d087'
down_revision='84fc8b53ac5d'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('studio_webinar_summaries',
        sa.Column('id',sa.Uuid(),nullable=False),
        sa.Column('foundation_id',sa.Uuid(),nullable=False),
        sa.Column('webinar_id',sa.Uuid(),nullable=False),
        sa.Column('draft_revision',sa.Integer(),nullable=False),
        sa.Column('reviewed_revision',sa.Integer(),nullable=True),
        sa.Column('published_revision',sa.Integer(),nullable=True),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['foundation_id'],['foundations.id']),
        sa.ForeignKeyConstraint(['webinar_id'],['studio_webinars.id']),
        sa.UniqueConstraint('webinar_id'),
        sa.CheckConstraint('draft_revision>0 AND version>0',name='ck_webinar_summary_revision'))
    op.create_index('ix_studio_webinar_summaries_foundation_id','studio_webinar_summaries',['foundation_id'])
    op.create_table('studio_webinar_summary_revisions',
        sa.Column('id',sa.Uuid(),nullable=False),
        sa.Column('summary_id',sa.Uuid(),nullable=False),
        sa.Column('number',sa.Integer(),nullable=False),
        sa.Column('title',sa.String(300),nullable=False),
        sa.Column('body',sa.Text(),nullable=False),
        sa.Column('created_by_user_id',sa.Uuid(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),server_default=sa.func.now(),nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['summary_id'],['studio_webinar_summaries.id']),
        sa.ForeignKeyConstraint(['created_by_user_id'],['users.id']),
        sa.UniqueConstraint('summary_id','number'),
        sa.CheckConstraint('number>0',name='ck_webinar_summary_revision_number'))
    op.create_table('studio_webinar_summary_previews',
        sa.Column('id',sa.Uuid(),nullable=False),
        sa.Column('summary_id',sa.Uuid(),nullable=False),
        sa.Column('published_revision',sa.Integer(),nullable=False),
        sa.Column('actor_user_id',sa.Uuid(),nullable=False),
        sa.Column('snapshot',postgresql.JSONB(),nullable=False),
        sa.Column('preview_hash',sa.String(64),nullable=False),
        sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('consumed_at',sa.DateTime(timezone=True),nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['summary_id'],['studio_webinar_summaries.id']),
        sa.ForeignKeyConstraint(['actor_user_id'],['users.id']))
    op.create_table('studio_webinar_summary_deliveries',
        sa.Column('id',sa.Uuid(),nullable=False),
        sa.Column('summary_id',sa.Uuid(),nullable=False),
        sa.Column('published_revision',sa.Integer(),nullable=False),
        sa.Column('recipient_id',sa.Uuid(),nullable=False),
        sa.Column('sender_user_id',sa.Uuid(),nullable=False),
        sa.Column('outbox_id',sa.Uuid(),nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['summary_id'],['studio_webinar_summaries.id']),
        sa.ForeignKeyConstraint(['recipient_id'],['users.id']),
        sa.ForeignKeyConstraint(['sender_user_id'],['users.id']),
        sa.ForeignKeyConstraint(['outbox_id'],['outbox_messages.id']),
        sa.UniqueConstraint('outbox_id'),
        sa.UniqueConstraint('summary_id','published_revision','recipient_id'))

def downgrade():
    op.drop_table('studio_webinar_summary_deliveries')
    op.drop_table('studio_webinar_summary_previews')
    op.drop_table('studio_webinar_summary_revisions')
    op.drop_index('ix_studio_webinar_summaries_foundation_id',table_name='studio_webinar_summaries')
    op.drop_table('studio_webinar_summaries')
