from app.core.models import AuditEvent

def audit(db, principal, command, entity_type, entity_id, fields=(), request_id=None):
    db.add(AuditEvent(foundation_id=principal.foundation_id, actor_id=principal.actor_id, command=command, entity_type=entity_type, entity_id=str(entity_id), changed_fields=list(fields), request_id=request_id))
