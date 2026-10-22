"""Courses: lesson order with stages, course settings and published stage snapshots.

Revision ID: a1c0d0e0f002
Revises: a1c0d0e0f001
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = 'a1c0d0e0f002'
down_revision = 'a1c0d0e0f001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('lessons', sa.Column('position', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('lessons', sa.Column('stage_title', sa.String(200), nullable=True))
    op.add_column('learning_tracks', sa.Column('description', sa.String(3000), nullable=False, server_default=''))
    op.add_column('learning_tracks', sa.Column('audience', sa.String(20), nullable=False, server_default='manual'))
    op.add_column('learning_tracks', sa.Column('required', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_check_constraint('ck_learning_track_audience', 'learning_tracks', "audience IN ('new','manual')")
    op.add_column('learning_releases', sa.Column('stages', postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    bind = op.get_bind()
    # The introduction was always assigned to everyone and is the onboarding requirement.
    bind.execute(sa.text("UPDATE learning_tracks SET audience='new', required=true WHERE key='introduction'"))
    # Keep the order volunteers already see: the current release first, then the rest by key
    # (the order the builder showed before positions existed).
    tracks = bind.execute(sa.text('SELECT id, current_release_id FROM learning_tracks')).all()
    for track_id, release_id in tracks:
        published = []
        if release_id is not None:
            version_ids = bind.execute(sa.text('SELECT lesson_version_ids FROM learning_releases WHERE id=:id'), {'id': release_id}).scalar() or []
            for version_id in version_ids:
                lesson_id = bind.execute(sa.text('SELECT lesson_id FROM lesson_versions WHERE id=CAST(:id AS uuid)'), {'id': str(version_id)}).scalar()
                if lesson_id is not None and lesson_id not in published:
                    published.append(lesson_id)
        rest = [row[0] for row in bind.execute(sa.text('SELECT id FROM lessons WHERE track_id=:track ORDER BY key'), {'track': track_id}).all() if row[0] not in published]
        for position, lesson_id in enumerate(published + rest):
            bind.execute(sa.text('UPDATE lessons SET position=:position WHERE id=:id'), {'position': position, 'id': lesson_id})


def downgrade():
    op.drop_column('learning_releases', 'stages')
    op.drop_constraint('ck_learning_track_audience', 'learning_tracks', type_='check')
    op.drop_column('learning_tracks', 'required')
    op.drop_column('learning_tracks', 'audience')
    op.drop_column('learning_tracks', 'description')
    op.drop_column('lessons', 'stage_title')
    op.drop_column('lessons', 'position')
