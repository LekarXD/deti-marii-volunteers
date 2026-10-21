from uuid import UUID
import pytest
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.crypto import digest
from app.core.models import ContactChannel,RegistrationSession,Session,User
from app.modules.profile.models import VolunteerProfile,ProfileRevision
from app.modules.profile.router import router as profile_router
from app.modules.applications.models import Application,ApplicationRevision
from app.modules.applications.service import initialize_registration_user
from app.modules.applications.tests.test_applications import env,anonymous_actor,VALID,verify_email,seed_legacy_registration_application

async def verify_owned_registration(client,factory,email):
    verified = await verify_email(client,factory,email)
    return UUID(verified['user_id'])

@pytest.mark.asyncio
async def test_new_verified_identity_uses_only_its_owned_submitted_application_name(env):
    app,factory=env;app.include_router(profile_router);candidate=await anonymous_actor(app)
    try:
        answers={**VALID,'firstName':'Кандидат','lastName':'Проверочный','email':'form-only@example.test'}
        submitted=await seed_legacy_registration_application(candidate,factory,answers);application_id=UUID(submitted['id']);revision_id=submitted['revision']['id']
        user_id=await verify_owned_registration(candidate,factory,'verified-own@example.test')
        response=await candidate.get('/api/v1/me/profile');assert response.status_code==200,response.text
        assert response.json()['display_name']=='Кандидат Проверочный' and response.json()['version']==0
        async with factory() as db:
            application=await db.get(Application,application_id);user=await db.get(User,user_id)
            assert application.user_id==user_id and application.registration_id is None and str(application.submitted_revision_id)==revision_id
            assert user.display_name=='Кандидат Проверочный'
            assert (await db.get(ApplicationRevision,application.submitted_revision_id)).answers['email']=='form-only@example.test'
    finally:await candidate.aclose()

@pytest.mark.asyncio
@pytest.mark.parametrize('existing_name,manual_profile',[('Имя существующего аккаунта',False),('Волонтёр',False),('Волонтёр',True)])
async def test_claim_to_existing_verified_identity_never_replaces_a_chosen_or_default_name(env,existing_name,manual_profile):
    app,factory=env;candidate=await anonymous_actor(app)
    try:
        await seed_legacy_registration_application(candidate,factory,{**VALID,'firstName':'Новое','lastName':'Имя'})
        async with factory() as db:
            session=await db.scalar(select(Session).where(Session.token_hash==digest(candidate.cookies.get('opora_session'))));user=User(foundation_id=session.foundation_id,display_name=existing_name);db.add(user);await db.flush();db.add(ContactChannel(user_id=user.id,normalized_value='existing@example.test',verified_at=utcnow()))
            if manual_profile:
                db.add(VolunteerProfile(user_id=user.id,foundation_id=user.foundation_id,version=1));db.add(ProfileRevision(foundation_id=user.foundation_id,user_id=user.id,number=1,snapshot={'display_name':existing_name},source='manual',actor_id=str(user.id)))
            await db.commit();existing_id=user.id
        claimed=await verify_owned_registration(candidate,factory,'existing@example.test');assert claimed==existing_id
        async with factory() as db:assert (await db.get(User,existing_id)).display_name==existing_name
    finally:await candidate.aclose()

@pytest.mark.asyncio
async def test_new_identity_without_owned_application_does_not_match_another_application_email(env):
    app,factory=env;other=await anonymous_actor(app);candidate=await anonymous_actor(app)
    try:
        submitted=await seed_legacy_registration_application(other,factory,{**VALID,'firstName':'Чужое','lastName':'Имя','email':'same-contact@example.test'})
        new_user=await verify_owned_registration(candidate,factory,'same-contact@example.test')
        async with factory() as db:
            assert (await db.get(User,new_user)).display_name=='Волонтёр'
            other_application=await db.get(Application,UUID(submitted['id']));assert other_application.user_id is None and other_application.registration_id
    finally:
        await other.aclose();await candidate.aclose()

@pytest.mark.asyncio
async def test_initializer_rejects_unproven_registration_and_preserves_manual_profile_even_if_called(env):
    app,factory=env;candidate=await anonymous_actor(app)
    try:
        submitted=await seed_legacy_registration_application(candidate,factory)
        from app.core.errors import ApiError
        async with factory() as db:
            application=await db.get(Application,UUID(submitted['id']));registration=await db.get(RegistrationSession,application.registration_id);user=User(foundation_id=registration.foundation_id);db.add(user);await db.flush()
            with pytest.raises(ApiError) as error:await initialize_registration_user(db,registration.id,user.id)
            assert error.value.code=='registration_not_verified'
            registration.claimed_user_id=user.id;registration.verified_email='own@example.test';db.add(VolunteerProfile(user_id=user.id,foundation_id=user.foundation_id,version=1));await db.flush()
            await initialize_registration_user(db,registration.id,user.id);assert user.display_name=='Волонтёр'
            await db.rollback()
    finally:await candidate.aclose()
