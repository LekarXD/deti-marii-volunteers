"""Safe unused Dobro link edits and explicit reminder owner.

Revision ID: c72a9064de18
Revises: b925c810af37
Exact reminder models7b07ecb; no audience, consent or delivery changes.
"""
from alembic import op
import sqlalchemy as sa
revision='c72a9064de18'
down_revision='b925c810af37'
branch_labels=None
depends_on=None

def lock_guards(foundation_lock):
    mapping_prefix="PERFORM pg_advisory_xact_lock(hashtextextended('dobro:'||OLD.foundation_id::text,0));" if foundation_lock else ''
    ledger_prefix="PERFORM pg_advisory_xact_lock(hashtextextended('dobro:'||linked_foundation::text,0));" if foundation_lock else ''
    op.execute(f"""CREATE OR REPLACE FUNCTION opora_dobro_mapping_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP='UPDATE' AND (NEW.series_id<>OLD.series_id OR NEW.foundation_id<>OLD.foundation_id) THEN
                RAISE EXCEPTION 'dobro_mapping_identity_immutable' USING ERRCODE='23514';
            END IF;
            {mapping_prefix}
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
    op.execute(f"""CREATE OR REPLACE FUNCTION opora_dobro_ledger_mapping_lock() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE linked_series uuid; linked_foundation uuid;
        BEGIN
            SELECT occurrence.series_id,occurrence.foundation_id INTO linked_series,linked_foundation
            FROM assignments assigned JOIN event_occurrences occurrence ON occurrence.id=assigned.occurrence_id
            WHERE assigned.id=NEW.assignment_id;
            IF linked_series IS NOT NULL THEN
                {ledger_prefix}
                PERFORM pg_advisory_xact_lock(hashtextextended('dobro-series:'||linked_foundation::text||':'||linked_series::text,0));
            END IF;
            RETURN NEW;
        END $$""")

def upgrade():
    op.add_column('dobro_settings',sa.Column('reminders_enabled',sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column('dobro_settings',sa.Column('reminder_owner_user_id',sa.UUID(),nullable=True))
    op.create_foreign_key('fk_dobro_reminder_owner_user','dobro_settings','users',['reminder_owner_user_id'],['id'])
    op.create_foreign_key('fk_dobro_reminder_owner_scope','dobro_settings','users',['reminder_owner_user_id','foundation_id'],['id','foundation_id'])
    op.create_check_constraint('ck_dobro_reminder_owner','dobro_settings','NOT reminders_enabled OR reminder_owner_user_id IS NOT NULL')
    lock_guards(True)
    op.execute("""CREATE FUNCTION opora_dobro_link_edit_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            IF TG_OP='DELETE' THEN RAISE EXCEPTION 'dobro_link_delete_forbidden' USING ERRCODE='23514'; END IF;
            IF NEW.id<>OLD.id OR NEW.foundation_id<>OLD.foundation_id OR NEW.opportunity_id<>OLD.opportunity_id OR NEW.created_at<>OLD.created_at OR NEW.version<>OLD.version+1 THEN
                RAISE EXCEPTION 'dobro_link_identity_or_version' USING ERRCODE='23514';
            END IF;
            PERFORM pg_advisory_xact_lock(hashtextextended('dobro:'||OLD.foundation_id::text,0));
            IF EXISTS(SELECT 1 FROM dobro_enrollments WHERE activity_id=OLD.id)
                OR EXISTS(SELECT 1 FROM dobro_transfers WHERE activity_id=OLD.id)
                OR EXISTS(SELECT 1 FROM attendance_events ledger
                    JOIN assignments assigned ON assigned.id=ledger.assignment_id
                    JOIN event_occurrences occurrence ON occurrence.id=assigned.occurrence_id
                    JOIN dobro_series_opportunities mapping ON mapping.series_id=occurrence.series_id AND mapping.foundation_id=occurrence.foundation_id
                    WHERE mapping.foundation_id=OLD.foundation_id AND mapping.opportunity_id=OLD.opportunity_id
                      AND (((occurrence.starts_at AT TIME ZONE occurrence.timezone)::date BETWEEN OLD.valid_from AND OLD.valid_until)
                        OR ((occurrence.starts_at AT TIME ZONE occurrence.timezone)::date BETWEEN NEW.valid_from AND NEW.valid_until))) THEN
                RAISE EXCEPTION 'dobro_link_already_used' USING ERRCODE='23514';
            END IF;
            RETURN NEW;
        END $$""")
    op.execute('DROP TRIGGER tr_dobro_activity_links_immutable ON dobro_activity_links')
    op.execute('CREATE TRIGGER tr_dobro_activity_links_guard BEFORE UPDATE OR DELETE ON dobro_activity_links FOR EACH ROW EXECUTE FUNCTION opora_dobro_link_edit_guard()')

def downgrade():
    op.execute('DROP TRIGGER tr_dobro_activity_links_guard ON dobro_activity_links')
    op.execute('DROP FUNCTION opora_dobro_link_edit_guard()')
    op.execute('CREATE TRIGGER tr_dobro_activity_links_immutable BEFORE UPDATE OR DELETE ON dobro_activity_links FOR EACH ROW EXECUTE FUNCTION opora_dobro_append_only()')
    lock_guards(False)
    op.drop_constraint('ck_dobro_reminder_owner','dobro_settings',type_='check')
    op.drop_constraint('fk_dobro_reminder_owner_scope','dobro_settings',type_='foreignkey')
    op.drop_constraint('fk_dobro_reminder_owner_user','dobro_settings',type_='foreignkey')
    op.drop_column('dobro_settings','reminder_owner_user_id')
    op.drop_column('dobro_settings','reminders_enabled')
