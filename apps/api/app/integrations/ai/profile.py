"""P13/P20 boundary: produces reviewable data, never writes profile tables."""
from app.core.errors import ApiError
from .service import enqueue_ai_run
PUBLIC_FIELDS=frozenset({'interests','skills','about','availability_summary','preferred_channel'})

async def enqueue_profile_suggestion(db,principal,snapshot):
    if not principal.user_id or str(snapshot.get('user_id'))!=str(principal.user_id):
        raise ApiError(403,'profile_owner_required','Можно подготовить предложение только для своего профиля')
    fields={key:value for key,value in snapshot.get('fields',{}).items() if key in PUBLIC_FIELDS}
    return await enqueue_ai_run(db,principal,'profile.suggest',{'profile_version':snapshot['version'],'fields':fields},source_refs=[f"profile:{principal.user_id}:{snapshot['version']}"])

def suggestion_payload(run,snapshot):
    if run.task!='profile.suggest' or run.state!='succeeded' or run.input_data.get('profile_version')!=snapshot['version']:
        raise ApiError(409,'profile_source_changed','Профиль изменён или предложение ещё не готово')
    before=snapshot.get('fields',{})
    patch={key:run.output[key] for key in ['interests','skills','about'] if run.output[key]!=before.get(key)}
    return {'expected_profile_version':snapshot['version'],'patch':patch,'source_refs':[{'source_id':str(snapshot['user_id']),'version':snapshot['version'],'fragment':'public_profile'}],'producer':{'model':run.model,'prompt_version':run.prompt_version,'run_id':str(run.id)}}
