"""Bind role snapshots to their role and close deferred application revision FK."""
from alembic import op
revision = '30b4f832ef68'
down_revision = 'b3566c48dbbb'
branch_labels = None
depends_on = None

def upgrade():
    op.create_foreign_key('application_current_revision_fk','applications','application_revisions',['submitted_revision_id'],['id'])
    op.create_unique_constraint('uq_role_version_identity','volunteer_role_versions',['id','role_id'])
    op.drop_constraint('opportunity_role_links_role_version_id_fkey','opportunity_role_links',type_='foreignkey')
    op.create_foreign_key('fk_opportunity_role_version_identity','opportunity_role_links','volunteer_role_versions',['role_version_id','role_id'],['id','role_id'])

def downgrade():
    op.drop_constraint('fk_opportunity_role_version_identity','opportunity_role_links',type_='foreignkey')
    op.create_foreign_key('opportunity_role_links_role_version_id_fkey','opportunity_role_links','volunteer_role_versions',['role_version_id'],['id'])
    op.drop_constraint('uq_role_version_identity','volunteer_role_versions',type_='unique')
    op.drop_constraint('application_current_revision_fk','applications',type_='foreignkey')
