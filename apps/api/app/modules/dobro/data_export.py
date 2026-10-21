"""Bounded own-data projection for the existing profile ZIP export.

No private coordinator notes, actor identities, source snapshots or other people's
rows are exposed. Retention and deletion remain the separate reviewed workflow.
"""
from sqlalchemy import select
from .models import DobroEnrollment, DobroEnrollmentEvent, DobroTransfer
from .service import own_view, user

async def own_export_section(db, principal):
    own = await user(db, principal)
    current = await own_view(db, principal)
    rows = (await db.scalars(select(DobroEnrollment).where(DobroEnrollment.foundation_id == principal.foundation_id, DobroEnrollment.user_id == own.id).order_by(DobroEnrollment.updated_at, DobroEnrollment.id))).all()
    enrollment_ids = [row.id for row in rows]
    events = (await db.scalars(select(DobroEnrollmentEvent).where(DobroEnrollmentEvent.enrollment_id.in_(enrollment_ids)).order_by(DobroEnrollmentEvent.created_at, DobroEnrollmentEvent.version))).all() if enrollment_ids else []
    transfers = (await db.scalars(select(DobroTransfer).where(DobroTransfer.foundation_id == principal.foundation_id, DobroTransfer.user_id == own.id).order_by(DobroTransfer.entered_at, DobroTransfer.id))).all()
    return {
        'format_version': 1,
        'current': current.model_dump(mode='json'),
        'enrollments': [{'id':str(row.id), 'activity_id':str(row.activity_id), 'state':row.state, 'version':row.version, 'updated_at':row.updated_at.isoformat()} for row in rows],
        'enrollment_history': [{'enrollment_id':str(row.enrollment_id), 'version':row.version, 'state':row.state, 'created_at':row.created_at.isoformat()} for row in events],
        'transfers': [{'id':str(row.id), 'activity_id':str(row.activity_id), 'period':row.period.strftime('%Y-%m'), 'minutes_due_snapshot':row.minutes_due_snapshot, 'hours_delta':row.hours_delta, 'entered_at':row.entered_at.isoformat()} for row in transfers],
    }
