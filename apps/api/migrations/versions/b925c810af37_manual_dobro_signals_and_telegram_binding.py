"""Manual Dobro ledger, configurable signals and private Telegram binding.

Revision ID: b925c810af37
Revises: 6f4b9231d087
Exact model sources: Dobro814a45e, Signals3b0a289, Telegram864e6df.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision='b925c810af37'
down_revision='6f4b9231d087'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('dobro_settings',
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('organization_url', sa.String(length=1500), nullable=False),
    sa.Column('registration_url', sa.String(length=1500), nullable=False),
    sa.Column('verified', sa.Boolean(), nullable=False),
    sa.Column('monthly_day', sa.Integer(), nullable=False),
    sa.Column('hard_deadline_days', sa.Integer(), nullable=False),
    sa.Column('risk_days', sa.Integer(), nullable=False),
    sa.Column('whole_hours', sa.Boolean(), nullable=False),
    sa.Column('rules_confirmed', sa.Boolean(), nullable=False),
    sa.Column('reminder_template', sa.Text(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('updated_by', sa.String(length=200), nullable=False),
    sa.CheckConstraint('monthly_day BETWEEN 1 AND 28 AND hard_deadline_days BETWEEN 1 AND 365 AND risk_days BETWEEN 1 AND 60 AND version > 0', name='ck_dobro_settings'),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.PrimaryKeyConstraint('foundation_id')
    )
    op.create_table('dobro_activity_links',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('opportunity_id', sa.Uuid(), nullable=False),
    sa.Column('url', sa.String(length=1500), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('valid_from', sa.Date(), nullable=False),
    sa.Column('valid_until', sa.Date(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.String(length=200), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("kind IN ('long_term','one_off') AND valid_until >= valid_from AND version > 0", name='ck_dobro_activity'),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['opportunity_id', 'foundation_id'], ['opportunities.id', 'opportunities.foundation_id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('id', 'foundation_id')
    )
    op.create_index(op.f('ix_dobro_activity_links_foundation_id'), 'dobro_activity_links', ['foundation_id'], unique=False)
    op.create_table('dobro_profiles',
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('profile_url', sa.String(length=1500), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('updated_by', sa.String(length=200), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('user_id')
    )
    op.create_table('signal_rule_settings',
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('thresholds', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('owner_user_id', sa.UUID(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_result', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.CheckConstraint('version>0', name='ck_signal_rule_version'),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('foundation_id')
    )
    op.create_table('telegram_bindings',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('telegram_user_id', sa.BigInteger(), nullable=False),
    sa.Column('chat_id', sa.BigInteger(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('verified_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('telegram_user_id>0 AND chat_id=telegram_user_id AND version>0', name='ck_telegram_binding_private'),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['user_id', 'foundation_id'], ['users.id', 'users.foundation_id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_telegram_bindings_foundation_id'), 'telegram_bindings', ['foundation_id'], unique=False)
    op.create_index('uq_telegram_binding_active_identity', 'telegram_bindings', ['foundation_id', 'telegram_user_id'], unique=True, postgresql_where=sa.text('revoked_at IS NULL'))
    op.create_index('uq_telegram_binding_active_user', 'telegram_bindings', ['foundation_id', 'user_id'], unique=True, postgresql_where=sa.text('revoked_at IS NULL'))
    op.create_table('dobro_enrollments',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('activity_id', sa.Uuid(), nullable=False),
    sa.Column('state', sa.String(length=20), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("state IN ('none','applied','approved','not_needed') AND version > 0", name='ck_dobro_enrollment'),
    sa.ForeignKeyConstraint(['activity_id', 'foundation_id'], ['dobro_activity_links.id', 'dobro_activity_links.foundation_id'], ),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('activity_id', 'user_id')
    )
    op.create_table('dobro_transfers',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('activity_id', sa.Uuid(), nullable=False),
    sa.Column('period', sa.Date(), nullable=False),
    sa.Column('minutes_due_snapshot', sa.Integer(), nullable=False),
    sa.Column('hours_delta', sa.Integer(), nullable=False),
    sa.Column('snapshot_hash', sa.String(length=64), nullable=False),
    sa.Column('snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('actor_id', sa.String(length=200), nullable=False),
    sa.Column('note', sa.Text(), nullable=False),
    sa.Column('entered_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint('hours_delta <> 0 AND EXTRACT(DAY FROM period) = 1', name='ck_dobro_transfer_delta'),
    sa.ForeignKeyConstraint(['activity_id', 'foundation_id'], ['dobro_activity_links.id', 'dobro_activity_links.foundation_id'], ),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dobro_transfers_foundation_id'), 'dobro_transfers', ['foundation_id'], unique=False)
    op.create_index(op.f('ix_dobro_transfers_user_id'), 'dobro_transfers', ['user_id'], unique=False)
    op.create_table('rule_signals',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('rule', sa.String(length=20), nullable=False),
    sa.Column('entity_id', sa.Uuid(), nullable=False),
    sa.Column('group_id', sa.Uuid(), nullable=True),
    sa.Column('subject_user_id', sa.UUID(), nullable=True),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('details', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('source_hash', sa.String(length=64), nullable=False),
    sa.Column('settings_version', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('state', sa.String(length=20), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("rule IN ('miss','quiet','learn','app','shift')", name='ck_rule_signal_kind'),
    sa.CheckConstraint("state IN ('open','resolved','dismissed') AND version>0", name='ck_rule_signal_state'),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['group_id'], ['participant_groups.id'], ),
    sa.ForeignKeyConstraint(['subject_user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('foundation_id', 'rule', 'entity_id')
    )
    op.create_index(op.f('ix_rule_signals_foundation_id'), 'rule_signals', ['foundation_id'], unique=False)
    op.create_table('dobro_enrollment_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('enrollment_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('state', sa.String(length=20), nullable=False),
    sa.Column('actor_id', sa.String(length=200), nullable=False),
    sa.Column('reason', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['enrollment_id'], ['dobro_enrollments.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('enrollment_id', 'version')
    )
    op.create_table('dobro_series_opportunities',
    sa.Column('series_id', sa.Uuid(), nullable=False),
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('opportunity_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('actor_id', sa.String(length=200), nullable=False),
    sa.CheckConstraint('version > 0', name='ck_dobro_series_version'),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['opportunity_id', 'foundation_id'], ['opportunities.id', 'opportunities.foundation_id'], ),
    sa.ForeignKeyConstraint(['series_id', 'foundation_id'], ['event_series.id', 'event_series.foundation_id'], ),
    sa.PrimaryKeyConstraint('series_id')
    )
    op.create_table('telegram_link_tokens',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('foundation_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('session_id', sa.UUID(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('token_cipher', sa.Text(), nullable=True),
    sa.Column('purpose', sa.String(length=30), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('outcome', sa.String(length=20), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("purpose='telegram_bind' AND (outcome IS NULL OR outcome IN ('linked','conflict')) AND (outcome IS NULL OR consumed_at IS NOT NULL) AND expires_at>created_at", name='ck_telegram_link_token'),
    sa.ForeignKeyConstraint(['foundation_id'], ['foundations.id'], ),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], ),
    sa.ForeignKeyConstraint(['user_id', 'foundation_id'], ['users.id', 'users.foundation_id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('token_hash')
    )
    op.create_index('ix_telegram_link_token_owner', 'telegram_link_tokens', ['foundation_id', 'user_id', 'session_id', 'created_at'], unique=False)
    op.create_index(op.f('ix_telegram_link_tokens_foundation_id'), 'telegram_link_tokens', ['foundation_id'], unique=False)

    # btree_gist is an existing prerequisite from 89e3060d3f4f.
    op.execute("ALTER TABLE dobro_activity_links ADD CONSTRAINT ex_dobro_activity_no_overlap EXCLUDE USING gist (foundation_id WITH =, opportunity_id WITH =, daterange(valid_from,valid_until,'[]') WITH &&)")
    for table,column,target,name in (
        ('dobro_profiles','user_id','users','fk_dobro_profile_user_scope'),
        ('dobro_enrollments','user_id','users','fk_dobro_enrollment_user_scope'),
        ('dobro_transfers','user_id','users','fk_dobro_transfer_user_scope'),
        ('signal_rule_settings','owner_user_id','users','fk_signal_rule_owner_scope'),
        ('rule_signals','subject_user_id','users','fk_rule_signal_user_scope'),
        ('rule_signals','group_id','participant_groups','fk_rule_signal_group_scope')):
        op.create_foreign_key(name,table,target,[column,'foundation_id'],['id','foundation_id'])
    op.execute("""CREATE FUNCTION opora_dobro_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'dobro_immutable_journal' USING ERRCODE='23514'; END $$""")
    for table in ('dobro_activity_links','dobro_transfers','dobro_enrollment_events'):
        op.execute(f'CREATE TRIGGER tr_{table}_immutable BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION opora_dobro_append_only()')
    op.execute("""CREATE FUNCTION opora_dobro_mapping_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP='UPDATE' AND (NEW.series_id<>OLD.series_id OR NEW.foundation_id<>OLD.foundation_id) THEN
                RAISE EXCEPTION 'dobro_mapping_identity_immutable' USING ERRCODE='23514';
            END IF;
            PERFORM pg_advisory_xact_lock(hashtextextended('dobro-series:'||OLD.foundation_id::text||':'||OLD.series_id::text,0));
            IF EXISTS(SELECT 1 FROM attendance_events ledger
                JOIN assignments assigned ON assigned.id=ledger.assignment_id
                JOIN event_occurrences occurrence ON occurrence.id=assigned.occurrence_id
                WHERE occurrence.series_id=OLD.series_id AND occurrence.foundation_id=OLD.foundation_id) THEN
                RAISE EXCEPTION 'dobro_mapping_has_ledger_facts' USING ERRCODE='23514';
            END IF;
            IF TG_OP='DELETE' THEN RETURN OLD; END IF;
            RETURN NEW;
        END $$""")
    op.execute('CREATE TRIGGER tr_dobro_series_mapping_guard BEFORE UPDATE OR DELETE ON dobro_series_opportunities FOR EACH ROW EXECUTE FUNCTION opora_dobro_mapping_guard()')
    op.execute("""CREATE FUNCTION opora_dobro_ledger_mapping_lock() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE linked_series uuid; linked_foundation uuid;
        BEGIN
            SELECT occurrence.series_id,occurrence.foundation_id INTO linked_series,linked_foundation
            FROM assignments assigned JOIN event_occurrences occurrence ON occurrence.id=assigned.occurrence_id
            WHERE assigned.id=NEW.assignment_id;
            IF linked_series IS NOT NULL THEN
                PERFORM pg_advisory_xact_lock(hashtextextended('dobro-series:'||linked_foundation::text||':'||linked_series::text,0));
            END IF;
            RETURN NEW;
        END $$""")
    op.execute('CREATE TRIGGER tr_attendance_dobro_mapping_lock BEFORE INSERT ON attendance_events FOR EACH ROW EXECUTE FUNCTION opora_dobro_ledger_mapping_lock()')
    op.execute("""CREATE FUNCTION opora_telegram_token_session_scope() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF NOT EXISTS(SELECT 1 FROM sessions login WHERE login.id=NEW.session_id AND login.user_id=NEW.user_id AND login.foundation_id=NEW.foundation_id) THEN
                RAISE EXCEPTION 'telegram_token_session_scope_mismatch' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute('CREATE TRIGGER tr_telegram_token_session_scope BEFORE INSERT OR UPDATE ON telegram_link_tokens FOR EACH ROW EXECUTE FUNCTION opora_telegram_token_session_scope()')

def downgrade():
    op.execute("DROP TRIGGER tr_attendance_dobro_mapping_lock ON attendance_events")
    op.drop_table('telegram_link_tokens')
    op.drop_table('dobro_series_opportunities')
    op.drop_table('dobro_enrollment_events')
    op.drop_table('rule_signals')
    op.drop_table('dobro_transfers')
    op.drop_table('dobro_enrollments')
    op.drop_table('telegram_bindings')
    op.drop_table('signal_rule_settings')
    op.drop_table('dobro_profiles')
    op.drop_table('dobro_activity_links')
    op.drop_table('dobro_settings')
    op.execute('DROP FUNCTION opora_telegram_token_session_scope()')
    op.execute('DROP FUNCTION opora_dobro_ledger_mapping_lock()')
    op.execute('DROP FUNCTION opora_dobro_mapping_guard()')
    op.execute('DROP FUNCTION opora_dobro_append_only()')
