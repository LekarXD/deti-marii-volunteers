from uuid import UUID
import pytest
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.auth import Principal
from app.core.models import User
from app.modules.profile.tests.test_profile import attendance_fixture
from app.modules.followups.models import Reflection,ReflectionReview,ReflectionReviewNote
from app.modules.crm.models import CrmVolunteer
from app.modules.crm.service import volunteer_view
from app.modules.crm.tests.test_crm import env,coordinator

@pytest.mark.asyncio
async def test_crm_projects_only_scoped_public_reflection_and_decision(env):
    app,factory=env;client=await coordinator(app,factory)
    try:
        from app.core.config import get_settings
        foundation=get_settings().foundation_id
        async with factory() as db:
            user=User(foundation_id=foundation,display_name='Волонтёр после выхода');db.add(user);await db.flush()
            staff=await db.scalar(select(User).where(User.id!=user.id));await db.commit()
        assignment,_,_=await attendance_fixture(factory,user.id)
        async with factory() as db:
            person=CrmVolunteer(foundation_id=foundation,user_id=user.id,display_name=user.display_name,contacts={},context='');db.add(person)
            reflection=Reflection(foundation_id=foundation,assignment_id=assignment,user_id=user.id,text='Хочу продолжить',unexpected='Новые задания',help='yes',help_text='Не раскрывать в CRM',continuation='discuss',submitted_at=utcnow());db.add(reflection);await db.flush()
            review=ReflectionReview(foundation_id=foundation,reflection_id=reflection.id,revision=1,decision='discussion',public_message='Обсудим подготовку',assigned_user_id=staff.id,author_id=staff.id);db.add(review);await db.flush();db.add(ReflectionReviewNote(review_id=review.id,text='Приватная заметка психолога',author_id=staff.id));await db.commit()
        p=Principal(staff.id,None,foundation,UUID(int=1),True,str(staff.id),grants=(('followups.read','foundation',None),))
        async with factory() as db:
            value=await volunteer_view(db,person,True,principal=p)
            assert value.latest_reflection.text=='Хочу продолжить' and value.latest_reflection.review.public_message=='Обсудим подготовку'
            assert not value.latest_reflection.can_review
            assert 'Приватная' not in value.model_dump_json() and 'Не раскрывать' not in value.model_dump_json()
            reflection=await db.get(Reflection,reflection.id);reflection.restricted=True;await db.flush()
            assert (await volunteer_view(db,person,True,principal=p)).latest_reflection is None
            p.grants+=(('signals.restricted','foundation',None),)
            assert (await volunteer_view(db,person,True,principal=p)).latest_reflection.id==reflection.id
            p.grants=()
            assert (await volunteer_view(db,person,True,principal=p)).latest_reflection is None
    finally:await client.aclose()
