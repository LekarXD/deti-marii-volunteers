"""Own identity profile and reviewable suggestions. No producer may write profile fields."""
from datetime import date
from uuid import UUID
from sqlalchemy import select,delete,text
from sqlalchemy.dialects.postgresql import insert
from app.core.clock import utcnow
from .dates import local_today
from app.core.errors import ApiError
from app.core.models import User,ContactChannel
from app.modules.applications.service import check_version
from .models import VolunteerProfile,ProfileTag,ProfileTagLink,ProfileRevision,ProfileChangeSuggestion
from .schemas import ProfileView,ProfileTagValue,ProfileRevisionView,ProfileContactView,ProfileSuggestionView,ProfileUpdateCommand

def require_user(principal):
    if not principal.user_id:raise ApiError(403,'verified_identity_required','Войдите по подтверждённой почте, чтобы открыть профиль')
    return principal.user_id

async def own_user(db,principal,lock=False):
    user_id=require_user(principal)
    statement=select(User).where(User.id==user_id,User.foundation_id==principal.foundation_id,User.account_state=='active')
    if lock:
        await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'),{'key':f'profile:{principal.foundation_id}:{user_id}'})
        statement=statement.with_for_update()
    user=await db.scalar(statement.execution_options(populate_existing=True))
    if user is None:raise ApiError(404,'user_not_found','Пользователь не найден')
    return user

async def profile_view(db,principal):
    user=await own_user(db,principal);profile=await db.get(VolunteerProfile,user.id,populate_existing=True)
    pairs=(await db.execute(select(ProfileTag,ProfileTagLink.level).join(ProfileTagLink,ProfileTagLink.tag_id==ProfileTag.id).where(ProfileTagLink.user_id==user.id,ProfileTag.foundation_id==principal.foundation_id).order_by(ProfileTag.kind,ProfileTag.label))).all()
    contacts=(await db.scalars(select(ContactChannel).where(ContactChannel.user_id==user.id).order_by(ContactChannel.type,ContactChannel.id))).all()
    revisions=(await db.scalars(select(ProfileRevision).where(ProfileRevision.user_id==user.id,ProfileRevision.foundation_id==principal.foundation_id).order_by(ProfileRevision.number.desc()).limit(100))).all()
    expired=bool(profile and profile.lifecycle=='paused' and profile.paused_until and profile.paused_until<local_today())
    return ProfileView(user_id=user.id,display_name=user.display_name,version=profile.version if profile else 0,about=profile.about if profile else '',lifecycle=profile.lifecycle if profile and not expired else 'active',paused_until=profile.paused_until if profile and not expired else None,photo_asset_id=profile.photo_asset_id if profile else None,ai_about=profile.ai_about if profile else False,ai_skills=profile.ai_skills if profile else False,ai_interests=profile.ai_interests if profile else False,tags=[ProfileTagValue(kind=tag.kind,label=tag.label,level=level) for tag,level in pairs],contacts=[ProfileContactView(type=c.type,value=c.normalized_value,verified_at=c.verified_at) for c in contacts],revisions=[ProfileRevisionView(id=r.id,number=r.number,source=r.source,created_at=r.created_at,snapshot=r.snapshot) for r in revisions])

def snapshot(view):
    return view.model_dump(mode='json',exclude={'contacts','revisions','user_id'})

async def update_profile(db,principal,command,source='manual'):
    user=await own_user(db,principal,True);profile=await db.get(VolunteerProfile,user.id)
    check_version(profile.version if profile else 0,command.expected_version)
    if command.lifecycle=='active' and command.paused_until:raise ApiError(422,'invalid_pause','Дата окончания нужна только для паузы')
    if command.paused_until and command.paused_until<local_today():raise ApiError(422,'invalid_pause','Дата окончания паузы уже прошла')
    if command.photo_asset_id:
        from app.modules.assets.service import require_asset
        asset=await require_asset(db,principal,command.photo_asset_id)
        if asset.owner_user_id!=user.id or asset.purpose!='generic' or asset.content_type not in ('image/jpeg','image/png','image/webp'):raise ApiError(422,'invalid_profile_photo','Выберите своё готовое изображение')
    if profile is None:
        profile=VolunteerProfile(user_id=user.id,foundation_id=principal.foundation_id,version=1);db.add(profile);await db.flush()
    else:profile.version+=1
    user.display_name=command.display_name.strip()
    if not user.display_name:raise ApiError(422,'invalid_name','Укажите имя')
    user.version+=1
    for key in ('about','lifecycle','paused_until','photo_asset_id','ai_about','ai_skills','ai_interests'):setattr(profile,key,getattr(command,key))
    profile.updated_at=utcnow()
    await db.execute(delete(ProfileTagLink).where(ProfileTagLink.user_id==user.id))
    seen=set()
    for value in command.tags:
        label=' '.join(value.label.split());normalized=label.casefold()
        if not normalized:raise ApiError(422,'invalid_tag','Название не может быть пустым')
        if (value.kind,normalized) in seen:raise ApiError(422,'duplicate_tag','Уберите повторяющиеся навыки и интересы')
        seen.add((value.kind,normalized))
        await db.execute(insert(ProfileTag).values(foundation_id=principal.foundation_id,kind=value.kind,label=label,normalized=normalized).on_conflict_do_nothing(index_elements=['foundation_id','kind','normalized']))
        tag=await db.scalar(select(ProfileTag).where(ProfileTag.foundation_id==principal.foundation_id,ProfileTag.kind==value.kind,ProfileTag.normalized==normalized))
        db.add(ProfileTagLink(user_id=user.id,tag_id=tag.id,level=value.level if value.kind=='skill' else 'learn'))
    await db.flush();view=await profile_view(db,principal)
    revision=ProfileRevision(foundation_id=principal.foundation_id,user_id=user.id,number=profile.version,snapshot=snapshot(view),source=source,actor_id=principal.actor_id)
    db.add(revision);await db.flush()
    return await profile_view(db,principal)

async def public_snapshot(db,principal):
    view=await profile_view(db,principal);fields={}
    if view.ai_about:fields['about']=view.about
    if view.ai_skills:fields['skills']=[tag.label for tag in view.tags if tag.kind=='skill']
    if view.ai_interests:fields['interests']=[tag.label for tag in view.tags if tag.kind=='interest']
    return dict(user_id=str(view.user_id),version=view.version,fields=fields)

def suggestion_view(row):
    return ProfileSuggestionView(id=row.id,base_version=row.base_version,before=row.before,patch=row.patch,source_refs=row.source_refs,producer=row.producer,state=row.state,applied_revision_id=row.applied_revision_id,reverted_revision_id=row.reverted_revision_id,created_at=row.created_at)

async def suggestion_for_run(db,principal,run_id):
    await own_user(db,principal)
    row=await db.scalar(select(ProfileChangeSuggestion).where(ProfileChangeSuggestion.foundation_id==principal.foundation_id,ProfileChangeSuggestion.user_id==principal.user_id,ProfileChangeSuggestion.producer['run_id'].astext==str(run_id)))
    return suggestion_view(row) if row else None

async def ai_snapshot(db,principal,lock=False):
    if lock:await own_user(db,principal,True)
    return await public_snapshot(db,principal)

async def create_suggestion(db,principal,*,expected_profile_version,patch,source_refs,producer):
    await own_user(db,principal,True)
    run_id=producer.get('run_id') if isinstance(producer,dict) else None
    if isinstance(run_id,str) and run_id:
        prior=await db.scalar(select(ProfileChangeSuggestion).where(ProfileChangeSuggestion.foundation_id==principal.foundation_id,ProfileChangeSuggestion.user_id==principal.user_id,ProfileChangeSuggestion.producer['run_id'].astext==run_id))
        if prior:
            if prior.base_version!=expected_profile_version or prior.patch!=patch or prior.source_refs!=source_refs or prior.producer!=producer:raise ApiError(409,'suggestion_run_payload_conflict','Этот запуск уже создал другое предложение')
            return suggestion_view(prior)
    view=await profile_view(db,principal);check_version(view.version,expected_profile_version)
    allowed={'about':view.ai_about,'skills':view.ai_skills,'interests':view.ai_interests}
    if not patch or set(patch)-set(allowed) or any(not allowed[key] for key in patch):raise ApiError(422,'suggestion_fields_forbidden','Предложение затрагивает поля без разрешения')
    if 'about' in patch and (not isinstance(patch['about'],str) or len(patch['about'])>8000):raise ApiError(422,'invalid_suggestion','Некорректный текст предложения')
    for key in ('skills','interests'):
        if key in patch and (not isinstance(patch[key],list) or len(patch[key])>40 or any(not isinstance(v,str) or not v.strip() or len(v)>120 for v in patch[key])):raise ApiError(422,'invalid_suggestion','Некорректные навыки или интересы')
    if not source_refs or len(source_refs)>100 or any(not isinstance(ref,dict) or not {'source_id','version','fragment'}<=ref.keys() or len(str(ref['fragment']))>2000 for ref in source_refs):raise ApiError(422,'suggestion_sources_required','У предложения должны быть проверяемые источники')
    if any(ref['fragment']=='public_profile' and (str(ref['source_id'])!=str(principal.user_id) or ref['version']!=view.version) for ref in source_refs):raise ApiError(403,'suggestion_source_scope_denied','Источник предложения не относится к текущей версии вашего профиля')
    if not isinstance(producer,dict) or not {'model','prompt_version','run_id'}<=producer.keys():raise ApiError(422,'suggestion_producer_required','Не указан источник предложения')
    row=ProfileChangeSuggestion(foundation_id=principal.foundation_id,user_id=view.user_id,base_version=view.version,before=snapshot(view),patch=patch,source_refs=source_refs,producer=producer,state='proposed')
    db.add(row);await db.flush();return suggestion_view(row)

async def decide_suggestion(db,principal,suggestion_id,command):
    await own_user(db,principal,True)
    row=await db.scalar(select(ProfileChangeSuggestion).where(ProfileChangeSuggestion.id==suggestion_id,ProfileChangeSuggestion.foundation_id==principal.foundation_id,ProfileChangeSuggestion.user_id==principal.user_id).with_for_update())
    if row is None:raise ApiError(404,'suggestion_not_found','Предложение не найдено')
    current=await profile_view(db,principal);check_version(current.version,command.expected_version)
    if command.decision=='reject':
        if row.state!='proposed':raise ApiError(409,'suggestion_decided','Решение уже принято')
        row.state='rejected';await db.flush();return suggestion_view(row)
    if command.decision=='accept':
        if row.state!='proposed':raise ApiError(409,'suggestion_decided','Решение уже принято')
        check_version(current.version,row.base_version)
        flags={'about':current.ai_about,'skills':current.ai_skills,'interests':current.ai_interests}
        if any(not flags[k] for k in row.patch):raise ApiError(409,'suggestion_permission_revoked','Разрешение на эти поля отозвано')
        values=snapshot(current)
        tags=values['tags']
        for key,kind in (('skills','skill'),('interests','interest')):
            if key in row.patch:
                old={tag['label'].casefold():tag for tag in tags if tag['kind']==kind}
                tags=[tag for tag in tags if tag['kind']!=kind]+[dict(kind=kind,label=label,level=old.get(label.casefold(),{}).get('level','learn')) for label in row.patch[key]]
        values['tags']=tags
        if 'about' in row.patch:values['about']=row.patch['about']
        row.state='accepted'
    else:
        if row.state!='accepted':raise ApiError(409,'suggestion_not_accepted','Отменить можно принятое предложение')
        applied=await db.get(ProfileRevision,row.applied_revision_id)
        check_version(current.version,applied.number)
        values=dict(row.before);row.state='reverted'
    values.pop('version',None)
    result=await update_profile(db,principal,ProfileUpdateCommand(expected_version=current.version,**values),source='suggestion_'+command.decision)
    revision=await db.scalar(select(ProfileRevision).where(ProfileRevision.user_id==principal.user_id,ProfileRevision.number==result.version))
    if command.decision=='accept':row.applied_revision_id=revision.id
    else:row.reverted_revision_id=revision.id
    await db.flush();return suggestion_view(row)

async def active_for_invitations(db,foundation_id,user_id):
    profile=await db.scalar(select(VolunteerProfile).where(VolunteerProfile.user_id==user_id,VolunteerProfile.foundation_id==foundation_id))
    return profile is None or profile.lifecycle!='paused' or bool(profile.paused_until and profile.paused_until<local_today())

from .ledger import append_service_time  # internal P09 transaction seam

async def matching_context(db,principal):
    """Current self-selected facts, not an inference or a staff identity override."""
    from app.modules.crm.service import own_availability
    view=await profile_view(db,principal);own=await own_availability(db,principal);rule=own.availability
    skills=[dict(label=tag.label,normalized=tag.label.casefold(),level=tag.level) for tag in view.tags if tag.kind=='skill']
    interests=[dict(kind=tag.kind,label=tag.label,normalized=tag.label.casefold()) for tag in view.tags if tag.kind!='skill']
    evidence=[]
    if view.version and view.revisions:
        evidence=[dict(source_id=str(view.revisions[0].id),source_type='profile_revision',version=view.version,field=field) for field in ('skills','interests','lifecycle')]
    availability=None
    if rule:
        availability=dict(version=rule.number,owner_version=own.version,summary=rule.summary,timezone=rule.timezone,windows=[window.model_dump(mode='json') for window in rule.windows],verified=rule.verified)
        evidence.append(dict(source_id=str(rule.id),source_type='availability_rule',version=rule.number,field='availability'))
    return dict(profile_version=view.version,skills=skills,interests=interests,availability=availability,paused=view.lifecycle=='paused',no_contact=own.no_contact,evidence=evidence)
