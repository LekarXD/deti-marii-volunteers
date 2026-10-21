from app.core.auth import authz_guard
from app.core.audit import audit
from app.core.errors import ApiError
from app.core.idempotency import begin_command, finish_command


async def execute_command(db, principal, operation, key, body, action, request, permission=None):
    payload = body.model_dump(mode='json')
    try:
        await authz_guard(db, principal)
        if permission and not principal.has_permission(permission):
            raise ApiError(403, 'permission_denied', 'Недостаточно прав.')
        replay = await begin_command(db, principal, operation, key, payload)
        if replay is not None:
            await db.commit()
            return replay
        result = await action()
        response = result.model_dump(mode='json') if hasattr(result, 'model_dump') else result
        audit(db, principal, operation, 'simulator', response.get('id', ''),
              fields=[name for name in payload if name != 'expected_version'], request_id=getattr(request.state, 'request_id', None))
        await finish_command(db, principal, operation, key, response)
        await db.commit()
        return response
    except Exception:
        await db.rollback()
        raise
