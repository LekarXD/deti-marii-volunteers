from datetime import datetime
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.auth import lock_background_authorizations,load_background_staff_authorization
from app.worker.registry import register_handler
from .rule_models import SignalRuleSettings
from .rules import settings,evaluate
async def evaluate_rules(db,context):
    initial=await settings(db,context.foundation_id)
    if initial is None:return {'state':'source_missing'}
    await lock_background_authorizations(db,context.foundation_id,[initial.owner_user_id])
    row=await settings(db,context.foundation_id,True)
    if row.version!=context.payload.get('version') or row.next_run_at!=datetime.fromisoformat(context.payload['scheduled_for']):return {'state':'superseded'}
    if row.next_run_at>utcnow():return {'state':'not_due'}
    authority=await load_background_staff_authorization(db,context.foundation_id,row.owner_user_id)
    return await evaluate(db,context.foundation_id,row,authority,context)
register_handler('followups.rules',evaluate_rules,timeout_seconds=90)
