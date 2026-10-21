"""Salted password credentials and bounded session-bound email proofs.

Revision ID: 85f3d6a809be
Revises: c72a9064de18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '85f3d6a809be'
down_revision = 'c72a9064de18'
branch_labels = None
depends_on = None


def identity_columns():
    return [sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    op.create_table('password_credentials', *identity_columns(),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False, unique=True),
        sa.Column('password_hash', sa.Text(), nullable=False), sa.Column('demo_created', sa.Boolean(), nullable=False), sa.Column('version', sa.Integer(), nullable=False))
    op.create_table('password_challenges', *identity_columns(),
        sa.Column('foundation_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('foundations.id'), nullable=False),
        sa.Column('bound_session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('sessions.id'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id')),
        sa.Column('credential_version', sa.Integer()), sa.Column('normalized_contact', sa.String(320), nullable=False),
        sa.Column('purpose', sa.String(30), nullable=False), sa.Column('demo_code_allowed', sa.Boolean(), nullable=False), sa.Column('code_hash', sa.String(64), nullable=False),
        sa.Column('pending_password_hash', sa.Text()), sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consumed_at', sa.DateTime(timezone=True)), sa.Column('attempts', sa.Integer(), nullable=False),
        sa.CheckConstraint("purpose IN ('register','password_reset')", name='password_challenge_purpose'),
        sa.CheckConstraint('attempts BETWEEN 0 AND 5', name='password_challenge_attempts'),
        sa.CheckConstraint("purpose <> 'register' OR pending_password_hash IS NOT NULL", name='password_registration_hash'))
    op.create_index('ix_password_challenges_bound_session_id', 'password_challenges', ['bound_session_id'])


def downgrade():
    op.drop_table('password_challenges')
    op.drop_table('password_credentials')
