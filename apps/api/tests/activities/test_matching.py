"""Real producer integration: selected labels, immutable role snapshots, no score."""
from datetime import timedelta
from uuid import UUID
import pytest
from sqlalchemy import func,select
from app.core.auth import resolve_principal
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.models import Session
from app.modules.crm.models import CrmVolunteer,AvailabilityRule,AvailabilityWindow
from app.modules.profile.models import ProfileRevision
from app.modules.profile.schemas import ProfileUpdateCommand
from app.modules.profile.service import update_profile
from app.modules.learning.models import LearningTrack,LearningRelease,LearningAssignment
from .test_p07 import context,headers,post_role


async def profile(context,tags,**extra):
    async with context.db() as db:
        row=await db.scalar(select(Session).where(Session.token_hash==digest('self')))
        principal=await resolve_principal(db,row)
        result=await update_profile(db,principal,ProfileUpdateCommand(expected_version=extra.pop('version',0),display_name='Selected profile fixture',tags=tags,about='Private profile prose must not be used for matching',**extra))
        await db.commit()
        return result


async def published(context,role,requirements=None):
    created=await context.client.post('/api/v1/coord/opportunities',headers=headers(),json={'title':'В мастерской','role_ids':[role['id']],'program':'Творчество','audience':'Взрослые','location':'Мастерская','schedule':'По субботам',**({'preparation_requirements':requirements} if requirements is not None else {})})
    assert created.status_code==200,created.text
    result=await context.client.post(f"/api/v1/coord/opportunities/{created.json()['id']}/publish",headers=headers(),json={'expected_version':1})
    assert result.status_code==200,result.text
    return result.json()


@pytest.mark.asyncio
async def test_selected_profile_facts_have_exact_versioned_explanations_and_no_read_side_effect(context):
    role=await post_role(context,'Акварель')
    item=await published(context,role,[])
    selected=await profile(context,[{'kind':'interest','label':'  ТВОРЧЕСТВО '},{'kind':'skill','label':'акварель','level':'learn'},{'kind':'age_interest','label':'Взрослые'},{'kind':'place_interest','label':'Мастерская'}])
    async with context.db() as db:
        before=await db.scalar(select(func.count()).select_from(CrmVolunteer))
        revision=await db.scalar(select(ProfileRevision).where(ProfileRevision.user_id==selected.user_id))
    # AI profile opt-ins remain false: deterministic self explanations use only explicit labels.
    assert not selected.ai_skills and not selected.ai_interests
    response=await context.client.get(f"/api/v1/opportunities/{item['id']}",headers={'Cookie':'opora_session=self'})
    assert response.status_code==200,response.text
    match=response.json()['matching']
    assert len(match['reasons'])==4 and match['algorithm_version']=='rules-v2'
    assert any('хочу научиться' in reason for reason in match['reasons'])
    assert not any(key in match for key in ['score','percent','rank'])
    assert match['context_versions']['profile']==1
    assert {'skills','interests','role_title','program','audience','location'}=={entry['field'] for entry in match['evidence']}
    assert any(entry['source_id']==str(revision.id) and entry['version']=='1' for entry in match['evidence'])
    assert 'availability' in match['missing_data'] and 'occurrence_time' in match['missing_data']
    assert 'Private profile prose' not in response.text
    async with context.db() as db:assert await db.scalar(select(func.count()).select_from(CrmVolunteer))==before
    # Renaming the mutable role does not retroactively rewrite the authored opportunity role.
    renamed=await context.client.patch(f"/api/v1/coord/roles/{role['id']}",headers=headers(),json={'expected_version':1,'title':'Керамика'})
    assert renamed.status_code==200
    again=(await context.client.get(f"/api/v1/opportunities/{item['id']}",headers={'Cookie':'opora_session=self'})).json()['matching']
    assert any('акварель' in reason for reason in again['reasons'])
    # Another actor and staff snapshots do not receive the volunteer's profile explanation.
    staff=(await context.client.get(f"/api/v1/coord/opportunities/{item['id']}",headers={'Cookie':'opora_session=staff'})).json()['matching']
    assert staff['evidence']==[] and staff['context_versions']=={} and staff['reasons']==[]
    listing=(await context.client.get('/api/v1/opportunities',headers={'Cookie':'opora_session=self'})).json()['items']
    assert listing[0]['matching']==again
    await profile(context,[],version=1)
    changed=(await context.client.get(f"/api/v1/opportunities/{item['id']}",headers={'Cookie':'opora_session=self'})).json()['matching']
    assert changed['reasons']==[] and changed['context_versions']['profile']==2


@pytest.mark.asyncio
async def test_preparation_pause_and_availability_are_actual_facts_not_schedule_inference(context):
    role=await post_role(context)
    selected=await profile(context,[],lifecycle='paused')
    async with context.db() as db:
        volunteer=CrmVolunteer(foundation_id=context.foundation.id,user_id=selected.user_id,display_name='Selected profile fixture',context='Private coordinator note');db.add(volunteer);await db.flush()
        rule=AvailabilityRule(volunteer_id=volunteer.id,number=1,summary='Суббота',timezone='Europe/Moscow',preferred_channel='email',author_id='fixture');db.add(rule);await db.flush()
        db.add(AvailabilityWindow(rule_id=rule.id,weekday=5,start_minute=10*60,end_minute=14*60))
        track=LearningTrack(foundation_id=context.foundation.id,key='actual-preparation',title='Подготовка');db.add(track);await db.flush()
        release=LearningRelease(foundation_id=context.foundation.id,track_id=track.id,number=1,title='Версия подготовки',intro='',lesson_version_ids=[]);db.add(release);await db.flush()
        db.add(LearningAssignment(foundation_id=context.foundation.id,release_id=release.id,user_id=selected.user_id,completed_at=utcnow()))
        await db.commit()
        release_id=release.id
    item=await published(context,role,[{'key':'learning_release:'+str(release_id),'title':'Пройти подготовку','level':'mandatory'},{'key':'manual-discussion','title':'Обсудить задачу','level':'mandatory'}])
    response=await context.client.get(f"/api/v1/opportunities/{item['id']}",headers={'Cookie':'opora_session=self'})
    assert response.status_code==200,response.text
    match=response.json()['matching']
    assert match['context_versions']['availability']==1
    assert 'availability' not in match['missing_data'] and 'occurrence_time' in match['missing_data']
    assert 'preparation' in match['missing_data']
    assert any('пауза' in constraint for constraint in match['constraints'])
    assert any('Обсудить задачу' in constraint for constraint in match['constraints'])
    assert not any('Пройти подготовку' in constraint for constraint in match['constraints'])
    assert any('Подтверждена подготовка' in reason for reason in match['reasons'])
    assert not any('время подходит' in reason for reason in match['reasons'])
    assert 'Private coordinator note' not in response.text
    # Evidence is user-scoped: the coordinator has not completed this release.
    other=(await context.client.get(f"/api/v1/opportunities/{item['id']}",headers={'Cookie':'opora_session=staff'})).json()['matching']
    assert not any('Подтверждена подготовка' in reason for reason in other['reasons'])


@pytest.mark.asyncio
async def test_absent_revision_and_expired_pause_never_create_evidence_or_restriction(context):
    from app.modules.profile.models import VolunteerProfile
    role=await post_role(context)
    item=await published(context,role,[])
    async with context.db() as db:
        row=await db.scalar(select(Session).where(Session.token_hash==digest('self')))
        db.add(VolunteerProfile(user_id=row.user_id,foundation_id=context.foundation.id,version=1,lifecycle='paused',paused_until=utcnow().date()-timedelta(days=1)))
        await db.commit()
    response=await context.client.get(f"/api/v1/opportunities/{item['id']}",headers={'Cookie':'opora_session=self'})
    assert response.status_code==200,response.text
    match=response.json()['matching']
    assert match['reasons']==[] and match['evidence']==[] and match['constraints']==[]
    assert match['context_versions']['profile']==1
