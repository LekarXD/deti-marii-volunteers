"""platform identity jobs assets foundation"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = '89e3060d3f4f'
down_revision = None
branch_labels = None
depends_on = None
def upgrade():
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.create_table('foundations',
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('mutation_receipts',
    sa.Column('actor_id', sa.String(length=100), nullable=False),
    sa.Column('operation', sa.String(length=120), nullable=False),
    sa.Column('key', sa.String(length=128), nullable=False),
    sa.Column('payload_hash', sa.String(length=64), nullable=False),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('actor_id', 'operation', 'key')
    )
    op.create_table('rate_limit_buckets',
    sa.Column('key', sa.String(length=64), nullable=False),
    sa.Column('window', sa.BigInteger(), nullable=False),
    sa.Column('count', sa.Integer(), nullable=False),
    sa.PrimaryKeyConstraint('key')
    )
    op.create_table('audit_events',
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('actor_id', sa.String(length=100), nullable=False),
    sa.Column('command', sa.String(length=120), nullable=False),
    sa.Column('entity_type', sa.String(length=80), nullable=False),
    sa.Column('entity_id', sa.String(length=100), nullable=False),
    sa.Column('changed_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('request_id', sa.String(length=100), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_events_foundation_id'), 'audit_events', ['foundation_id'], unique=False)
    op.create_table('jobs',
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('kind', sa.String(length=100), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('state', sa.String(length=30), nullable=False),
    sa.Column('available_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('claim_token', sa.UUID(), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('max_attempts', sa.Integer(), nullable=False),
    sa.Column('error_code', sa.String(length=100), nullable=True),
    sa.Column('result', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_jobs_claim', 'jobs', ['state', 'available_at'], unique=False)
    op.create_table('users',
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('display_name', sa.String(length=200), nullable=False),
    sa.Column('account_state', sa.String(length=30), nullable=False),
    sa.Column('version', sa.BigInteger(), nullable=False),
    sa.Column('authz_version', sa.BigInteger(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_foundation_id'), 'users', ['foundation_id'], unique=False)
    op.create_table('contact_channels',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('normalized_value', sa.String(length=320), nullable=False),
    sa.Column('type', sa.String(length=20), nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('normalized_value')
    )
    op.create_index(op.f('ix_contact_channels_user_id'), 'contact_channels', ['user_id'], unique=False)
    op.create_table('mfa_factors',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('secret_cipher', sa.Text(), nullable=False),
    sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_counter', sa.BigInteger(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id')
    )
    op.create_table('mfa_recovery_codes',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code_hash')
    )
    op.create_index(op.f('ix_mfa_recovery_codes_user_id'), 'mfa_recovery_codes', ['user_id'], unique=False)
    op.create_table('outbox_messages',
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('channel', sa.String(length=30), nullable=False),
    sa.Column('payload_cipher', sa.Text(), nullable=False),
    sa.Column('state', sa.String(length=30), nullable=False),
    sa.Column('job_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('registration_sessions',
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('verified_email', sa.String(length=320), nullable=True),
    sa.Column('claimed_user_id', sa.UUID(), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['claimed_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('staff_memberships',
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('foundation_id', 'user_id')
    )
    op.create_table('auth_challenges',
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('registration_id', sa.UUID(), nullable=True),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('normalized_contact', sa.String(length=320), nullable=False),
    sa.Column('purpose', sa.String(length=30), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['registration_id'], ['registration_sessions.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_table('media_assets',
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('owner_user_id', sa.UUID(), nullable=True),
    sa.Column('owner_registration_id', sa.UUID(), nullable=True),
    sa.Column('access_permission', sa.String(length=100), nullable=True),
    sa.Column('storage_key', sa.String(length=200), nullable=False),
    sa.Column('content_type', sa.String(length=100), nullable=False),
    sa.Column('expected_size', sa.BigInteger(), nullable=False),
    sa.Column('checksum', sa.String(length=64), nullable=False),
    sa.Column('received_size', sa.BigInteger(), nullable=False),
    sa.Column('state', sa.String(length=30), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['owner_registration_id'], ['registration_sessions.id'], ),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('storage_key')
    )
    op.create_index(op.f('ix_media_assets_foundation_id'), 'media_assets', ['foundation_id'], unique=False)
    op.create_table('permission_grants',
    sa.Column('membership_id', sa.UUID(), nullable=False),
    sa.Column('permission', sa.String(length=100), nullable=False),
    sa.Column('scope_type', sa.String(length=20), nullable=False),
    sa.Column('scope_id', sa.UUID(), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['membership_id'], ['staff_memberships.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_permission_grants_membership_id'), 'permission_grants', ['membership_id'], unique=False)
    op.create_table('resource_reservations',
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('registration_id', sa.UUID(), nullable=True),
    sa.Column('owner_key', sa.String(length=100), nullable=False),
    sa.Column('source_type', sa.String(length=40), nullable=False),
    sa.Column('source_id', sa.UUID(), nullable=False),
    sa.Column('starts_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('busy_until', sa.DateTime(timezone=True), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('(user_id IS NULL) <> (registration_id IS NULL)', name='reservation_one_owner'),
    sa.CheckConstraint('busy_until > starts_at', name='reservation_positive_range'),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['registration_id'], ['registration_sessions.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_type', 'source_id')
    )
    op.create_index('ix_reservation_owner', 'resource_reservations', ['foundation_id', 'owner_key', 'starts_at'], unique=False)
    op.create_table('sessions',
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('csrf_hash', sa.String(length=64), nullable=False),
    sa.Column('csrf_cipher', sa.Text(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('registration_id', sa.UUID(), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('mfa_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('(user_id IS NULL) <> (registration_id IS NULL)', name='session_one_owner'),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['registration_id'], ['registration_sessions.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    # ### end Alembic commands ###
    op.execute("ALTER TABLE resource_reservations ADD CONSTRAINT reservation_no_overlap EXCLUDE USING gist (foundation_id WITH =, owner_key WITH =, tstzrange(starts_at,busy_until,'[)') WITH &&) WHERE (active)")

def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('sessions')
    op.drop_index('ix_reservation_owner', table_name='resource_reservations')
    op.drop_table('resource_reservations')
    op.drop_index(op.f('ix_permission_grants_membership_id'), table_name='permission_grants')
    op.drop_table('permission_grants')
    op.drop_index(op.f('ix_media_assets_foundation_id'), table_name='media_assets')
    op.drop_table('media_assets')
    op.drop_table('auth_challenges')
    op.drop_table('staff_memberships')
    op.drop_table('registration_sessions')
    op.drop_table('outbox_messages')
    op.drop_index(op.f('ix_mfa_recovery_codes_user_id'), table_name='mfa_recovery_codes')
    op.drop_table('mfa_recovery_codes')
    op.drop_table('mfa_factors')
    op.drop_index(op.f('ix_contact_channels_user_id'), table_name='contact_channels')
    op.drop_table('contact_channels')
    op.drop_index(op.f('ix_users_foundation_id'), table_name='users')
    op.drop_table('users')
    op.drop_index('ix_jobs_claim', table_name='jobs')
    op.drop_table('jobs')
    op.drop_index(op.f('ix_audit_events_foundation_id'), table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_table('rate_limit_buckets')
    op.drop_table('mutation_receipts')
    op.drop_table('foundations')
    # ### end Alembic commands ###
