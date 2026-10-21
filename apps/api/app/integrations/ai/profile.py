"""P20 produces an owned, reviewable proposal through the profile authority."""
from uuid import UUID
from sqlalchemy import select
from app.core.auth import resolve_principal
from app.core.clock import utcnow
from app.core.errors import ApiError
from app.core.models import Session, User
from .models import AIRun
from .service import enqueue_ai_run
PUBLIC_FIELDS=frozenset({'interests','skills','about'})

async def enqueue_profile_suggestion(db,principal,snapshot=None,*,expected_profile_version=None):
    if snapshot is None:
        from app.modules.profile.service import ai_snapshot
        snapshot=await ai_snapshot(db,principal,lock=True)
    if not principal.user_id or str(snapshot.get('user_id'))!=str(principal.user_id):
        raise ApiError(403,'profile_owner_required','Можно подготовить предложение только для своего профиля')
    if expected_profile_version is not None and snapshot['version']!=expected_profile_version:
        raise ApiError(409,'profile_source_changed','Профиль изменён. Обновите страницу')
    fields={key:value for key,value in snapshot.get('fields',{}).items() if key in PUBLIC_FIELDS}
    if not fields:raise ApiError(422,'profile_ai_optin_required','Сначала разрешите обработку выбранных полей профиля')
    return await enqueue_ai_run(db,principal,'profile.suggest',{'profile_version':snapshot['version'],'fields':fields},source_refs=[f"profile:{principal.user_id}:{snapshot['version']}"])

def suggestion_payload(run,snapshot):
    if run.task!='profile.suggest' or run.state!='succeeded' or run.input_data.get('profile_version')!=snapshot['version'] or run.input_data.get('fields')!={key:value for key,value in snapshot.get('fields',{}).items() if key in PUBLIC_FIELDS}:
        raise ApiError(409,'profile_source_changed','Профиль или разрешение на обработку изменены')
    before=snapshot.get('fields',{})
    patch={key:run.output[key] for key in before if key in PUBLIC_FIELDS and key in run.output and run.output[key]!=before[key]}
    return {'expected_profile_version':snapshot['version'],'patch':patch,'source_refs':[{'source_id':str(snapshot['user_id']),'version':snapshot['version'],'fragment':'public_profile'}],'producer':{'model':run.model,'prompt_version':run.prompt_version,'run_id':str(run.id)}}

async def current_principal(db,run):
    session=await db.get(Session,run.request_session_id,populate_existing=True)
    if session is None or session.revoked_at or session.expires_at<=utcnow() or session.foundation_id!=run.foundation_id:
        raise ApiError(409,'session_expired','Сессия запроса завершена')
    if session.user_id:await db.get(User,session.user_id,populate_existing=True)
    principal=await resolve_principal(db,session)
    if not principal.user_id or principal.actor_id!=run.actor_id:
        raise ApiError(403,'profile_owner_required','Владелец запроса изменён')
    return principal

async def validate_profile_source(db,principal,run,*,lock=False):
    from app.modules.profile.service import ai_snapshot
    if not principal.user_id or principal.actor_id!=run.actor_id or principal.foundation_id!=run.foundation_id:
        raise ApiError(403,'profile_owner_required','Можно подготовить предложение только для своего профиля')
    snapshot=await ai_snapshot(db,principal,lock=lock)
    if snapshot['version']!=run.input_data.get('profile_version') or snapshot['fields']!=run.input_data.get('fields') or not snapshot['fields']:
        raise ApiError(409,'profile_source_changed','Профиль или разрешение на обработку изменены')
    if run.source_refs!=[f"profile:{principal.user_id}:{snapshot['version']}"]:
        raise ApiError(409,'profile_source_changed','Источники предложения изменены')
    return snapshot

async def materialize_profile_suggestion(db,run,context):
    if run.task!='profile.suggest' or run.state!='succeeded':return
    from app.modules.profile.service import create_suggestion,suggestion_for_run
    try:
        principal=await current_principal(db,run)
        # Lookup precedes source CAS: accepted/rejected/reverted proposals are
        # immutable outcomes and a replay must never recreate them.
        existing=await suggestion_for_run(db,principal,run.id)
        if existing:return existing
        snapshot=await validate_profile_source(db,principal,run,lock=True)
        payload=suggestion_payload(run,snapshot)
        if not payload['patch']:
            run.state='no_changes';return
        await context.fence(db)
        return await create_suggestion(db,principal,**payload)
    except ApiError as error:
        run.state,run.error_code='sources_changed',error.code
        run.output=None

async def profile_run_view(db,principal,run_id):
    from app.modules.profile.service import suggestion_for_run
    value=await db.scalar(select(AIRun).where(AIRun.id==run_id,AIRun.foundation_id==principal.foundation_id,AIRun.actor_id==principal.actor_id,AIRun.task=='profile.suggest'))
    if value is None:raise ApiError(404,'ai_run_not_found','Обработка не найдена')
    existing=await suggestion_for_run(db,principal,value.id)
    state,error=value.state,value.error_code
    if not existing:
        try:await validate_profile_source(db,principal,value)
        except ApiError as rejected:state,error='sources_changed',rejected.code
    return {'id':value.id,'state':state,'error_code':error,'profile_version':value.input_data['profile_version'],'suggestion_id':existing.id if existing else None}
