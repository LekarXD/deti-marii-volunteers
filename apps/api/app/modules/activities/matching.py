"""Deterministic, private explanations from selected profile facts and authored fields."""
from uuid import UUID
from sqlalchemy import select
from .models import OpportunityRoleLink,VolunteerRoleVersion
from .schemas import ActivityMatchEvidence,MatchExplanation,normalized_title


async def own_match_context(db,principal):
    if principal.user_id is None:return None
    from app.modules.profile.service import matching_context
    return {**await matching_context(db,principal),'user_id':principal.user_id}


def context_evidence(context,field):
    return [ActivityMatchEvidence(source_id=str(item['source_id']),version=str(item['version']),field=item['field'])
        for item in context.get('evidence',[]) if item.get('field')==field]


async def explain_opportunity(db,opportunity,context):
    requirements=opportunity.preparation_requirements
    constraints=[];reasons=[];evidence=[];missing=[]
    if context is None:
        return MatchExplanation(reasons=[],missing_data=['interests','skills','availability','occurrence_time']+(['preparation'] if requirements else []),constraints=[r['title'] for r in requirements if r['level']=='mandatory'])
    interests=context.get('interests',[]);skills=context.get('skills',[])
    if not interests:missing.append('interests')
    if not skills:missing.append('skills')
    # Free-text regularity/schedule is deliberately not parsed into a timetable.
    if not (context.get('availability') or {}).get('windows'):missing.append('availability')
    missing.append('occurrence_time')
    targets={'interest':[(opportunity.program,'program')],'age_interest':[(opportunity.audience,'audience')],'place_interest':[(opportunity.location,'location')]}
    for selected in interests:
        label=selected['label']
        for authored,field in targets.get(selected['kind'],[]):
            if label.strip() and normalized_title(label)==normalized_title(authored):
                reasons.append(f'Выбранный интерес «{label}» совпадает с '+{'program':'программой','audience':'аудиторией','location':'местом'}[field]+f' «{authored}».')
                evidence.extend(context_evidence(context,'interests'))
                evidence.append(ActivityMatchEvidence(source_id=str(opportunity.id),version=str(opportunity.version),field=field))
    revisions=(await db.scalars(select(VolunteerRoleVersion).join(OpportunityRoleLink,OpportunityRoleLink.role_version_id==VolunteerRoleVersion.id).where(OpportunityRoleLink.opportunity_id==opportunity.id,OpportunityRoleLink.foundation_id==opportunity.foundation_id))).all()
    for skill in skills:
        for revision in revisions:
            title=revision.snapshot['title']
            if normalized_title(skill['label'])==normalized_title(title):
                level='хочу научиться' if skill['level']=='learn' else 'указан как уверенный навык'
                reasons.append(f'Ваш навык «{skill["label"]}» ({level}) совпадает с названием роли «{title}». Уровень подготовки по этому совпадению не определяется.')
                evidence.extend(context_evidence(context,'skills'))
                evidence.append(ActivityMatchEvidence(source_id=str(revision.id),version=str(revision.version),field='role_title'))
    if context.get('paused'):constraints.append('В профиле включена пауза: новые приглашения и подтверждения участия недоступны.')
    # Only exact version-bound learning evidence can fulfill a preparation item.
    if requirements:
        from app.modules.learning.service import requirement_status
        for requirement in requirements:
            status=await requirement_status(db,opportunity.foundation_id,context['user_id'],requirement['key'])
            if status and status['status']=='fulfilled':
                reasons.append(f'Подтверждена подготовка «{requirement["title"]}».')
                proof=status.get('evidence') or {}
                if proof.get('release_id'):
                    from app.modules.learning.models import LearningRelease
                    release=await db.get(LearningRelease,UUID(proof['release_id']))
                    if release and release.foundation_id==opportunity.foundation_id:
                        evidence.append(ActivityMatchEvidence(source_id=str(release.id),version=str(release.number),field='preparation'))
            else:
                missing.append('preparation')
                if requirement['level']=='mandatory':constraints.append(f'Нужно подтвердить подготовку «{requirement["title"]}».')
    unique={(item.source_id,item.version,item.field):item for item in evidence}
    availability=context.get('availability') or {}
    return MatchExplanation(reasons=list(dict.fromkeys(reasons)),constraints=list(dict.fromkeys(constraints)),missing_data=list(dict.fromkeys(missing)),
        evidence=list(unique.values()),context_versions={'profile':context.get('profile_version'),'availability':availability.get('version')})
