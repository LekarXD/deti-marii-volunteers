"""Volunteer event feed: role direction/skills, self sign-up origin and the reserve queue.

Revision ID: 5b7e2c9d4f10
Revises: 85f3d6a809be
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '5b7e2c9d4f10'
down_revision = '85f3d6a809be'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('volunteer_roles', sa.Column('direction', sa.String(100), nullable=False, server_default=''))
    op.add_column('volunteer_roles', sa.Column('skills', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column('assignments', sa.Column('origin', sa.String(20), nullable=False, server_default='invitation'))
    op.create_check_constraint('ck_assignment_origin', 'assignments', "origin IN ('invitation','self','reserve')")
    op.create_table('staffing_need_reserves',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('foundation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('foundations.id'), nullable=False),
        sa.Column('occurrence_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('staffing_need_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('offered_assignment_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('assignments.id')),
        sa.Column('queued_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('version', sa.BigInteger(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['staffing_need_id', 'occurrence_id', 'foundation_id'], ['staffing_needs.id', 'staffing_needs.occurrence_id', 'staffing_needs.foundation_id']),
        sa.UniqueConstraint('staffing_need_id', 'user_id'),
        sa.CheckConstraint("state IN ('waiting','offered','closed')", name='ck_reserve_state'))
    op.create_index('ix_reserve_queue', 'staffing_need_reserves', ['staffing_need_id', 'state', 'queued_at', 'id'])
    op.create_index('ix_reserve_user', 'staffing_need_reserves', ['foundation_id', 'user_id', 'state'])


def downgrade():
    op.drop_index('ix_reserve_user', table_name='staffing_need_reserves')
    op.drop_index('ix_reserve_queue', table_name='staffing_need_reserves')
    op.drop_table('staffing_need_reserves')
    op.drop_constraint('ck_assignment_origin', 'assignments', type_='check')
    op.drop_column('assignments', 'origin')
    op.drop_column('volunteer_roles', 'skills')
    op.drop_column('volunteer_roles', 'direction')
