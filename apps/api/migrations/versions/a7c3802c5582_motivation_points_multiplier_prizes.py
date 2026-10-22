"""Points multiplier on needs and confirmed assignments, points bonuses/adjustments and prizes.

Revision ID: a7c3802c5582
Revises: 5b7e2c9d4f10
"""
from alembic import op
import sqlalchemy as sa

revision = 'a7c3802c5582'
down_revision = '5b7e2c9d4f10'
branch_labels = None
depends_on = None
MULTIPLIED = (('assignments', 'ck_assignment_points_multiplier'), ('event_series_need_templates', 'ck_need_template_points_multiplier'), ('staffing_needs', 'ck_staffing_need_points_multiplier'))


def upgrade():
    op.create_table('points_entries',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('bonus_key', sa.String(length=40), nullable=True),
    sa.Column('points', sa.Integer(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('actor_id', sa.String(length=100), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('bonus','adjustment') AND (kind = 'bonus') = (bonus_key IS NOT NULL) AND points <> 0", name='ck_points_entry'),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('foundation_id', 'user_id', 'bonus_key', name='uq_points_bonus_once')
    )
    op.create_index(op.f('ix_points_entries_foundation_id'), 'points_entries', ['foundation_id'], unique=False)
    op.create_index(op.f('ix_points_entries_user_id'), 'points_entries', ['user_id'], unique=False)
    op.create_table('prizes',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('photo_asset_id', sa.UUID(), nullable=True),
    sa.Column('price_points', sa.Integer(), nullable=False),
    sa.Column('stock', sa.Integer(), nullable=False),
    sa.Column('visible', sa.Boolean(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('price_points > 0 AND stock >= 0 AND version > 0', name='ck_prize'),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['photo_asset_id'], ['media_assets.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prizes_foundation_id'), 'prizes', ['foundation_id'], unique=False)
    op.create_table('prize_requests',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('prize_id', sa.Uuid(), nullable=False),
    sa.Column('points', sa.Integer(), nullable=False),
    sa.Column('state', sa.String(length=20), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('decided_by', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("points > 0 AND state IN ('requested','issued','rejected','cancelled')", name='ck_prize_request'),
    sa.ForeignKeyConstraint(['decided_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['prize_id'], ['prizes.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prize_requests_foundation_id'), 'prize_requests', ['foundation_id'], unique=False)
    op.create_index(op.f('ix_prize_requests_prize_id'), 'prize_requests', ['prize_id'], unique=False)
    op.create_index(op.f('ix_prize_requests_user_id'), 'prize_requests', ['user_id'], unique=False)
    for table, check in MULTIPLIED:
        op.add_column(table, sa.Column('points_multiplier', sa.Numeric(precision=3, scale=2, asdecimal=False), server_default='1', nullable=False))
        op.create_check_constraint(check, table, 'points_multiplier IN (1, 1.5)')

def downgrade():
    for table, check in MULTIPLIED:
        op.drop_constraint(check, table, type_='check')
        op.drop_column(table, 'points_multiplier')
    op.drop_index(op.f('ix_prize_requests_user_id'), table_name='prize_requests')
    op.drop_index(op.f('ix_prize_requests_prize_id'), table_name='prize_requests')
    op.drop_index(op.f('ix_prize_requests_foundation_id'), table_name='prize_requests')
    op.drop_table('prize_requests')
    op.drop_index(op.f('ix_prizes_foundation_id'), table_name='prizes')
    op.drop_table('prizes')
    op.drop_index(op.f('ix_points_entries_user_id'), table_name='points_entries')
    op.drop_index(op.f('ix_points_entries_foundation_id'), table_name='points_entries')
    op.drop_table('points_entries')
