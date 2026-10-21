import asyncio,json
from datetime import timedelta
from uuid import UUID,uuid4
from types import SimpleNamespace
import httpx,pyotp,pytest
from fastapi import FastAPI
from sqlalchemy import select,func
from app.core.auth import resolve_principal
from app.core.clock import utcnow
from app.core.crypto import seal,unseal,digest
from app.core.db import get_db
from app.core.errors import install_error_handlers,ApiError
from app.core.models import User,Foundation,Session,StaffMembership,PermissionGrant,MfaFactor,OutboxMessage
from app.modules.studio.tests.test_studio import world
from app.modules.studio.models import Webinar,WebinarEnrollment
from app.modules.studio.summary_models import WebinarSummaryRevision,WebinarSummaryDelivery
from app.modules.studio.summary_router import edit_summary,published_summary
from app.modules.studio.router import router
from app.modules.studio.summary_schemas import SummaryEditInput
from app.modules.studio import summary_notifications
from app.modules.notifications.models import NotificationPreference
from app.modules.notifications.delivery import process_internal
from app.modules.messaging.models import Message
from app.worker.queue import claim,complete

@pytest.fixture
async def scenario(world,monkeypatch):
    w=world
    async with w.factory() as db:
        membership=await db.scalar(select(StaffMembership).where(StaffMembership.user_id==w.host.user_id))
        db.add(PermissionGrant(membership_id=membership.id,permission='notifications.send'))
        db.add(MfaFactor(user_id=w.host.user_id,secret_cipher=seal(pyotp.random_base32()),confirmed_at=utcnow()))
        host_session=await db.get(Session,w.host.session_id);host_session.token_hash=digest('summary-host');host_session.csrf_hash=digest('summary-csrf')
        viewer_session=await db.get(Session,w.viewer.session_id);viewer_session.token_hash=digest('summary-viewer')
        webinar=Webinar(foundation_id=w.foundation.id,host_user_id=w.host.user_id,title='Завершённая встреча',starts_at=utcnow()-timedelta(days=1),state='ended');db.add(webinar);await db.flush()
        db.add(WebinarEnrollment(foundation_id=w.foundation.id,webinar_id=webinar.id,user_id=w.viewer.user_id))
        blocked=User(foundation_id=w.foundation.id,display_name='Без уведомлений');db.add(blocked);await db.flush()
        db.add(WebinarEnrollment(foundation_id=w.foundation.id,webinar_id=webinar.id,user_id=blocked.id));db.add(NotificationPreference(foundation_id=w.foundation.id,user_id=blocked.id,no_contact=True))
        foreign=Foundation(name='Другой фонд');db.add(foreign);await db.flush();foreign_webinar=Webinar(foundation_id=foreign.id,host_user_id=w.host.user_id,title='Чужая встреча',starts_at=utcnow()-timedelta(days=1),state='ended');db.add(foreign_webinar)
        await db.commit();w.host=await resolve_principal(db,host_session)
    app=FastAPI();install_error_handlers(app);app.include_router(router)
    async def database():
        async with w.factory() as db:yield db
    app.dependency_overrides[get_db]=database
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(),'trusted_origins',['http://testserver'])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',cookies={'opora_session':'summary-host'},headers={'Origin':'http://testserver','X-CSRF-Token':'summary-csrf'}) as client:
        yield SimpleNamespace(w=w,client=client,id=webinar.id,foreign_id=foreign_webinar.id,blocked=blocked)
async def post(f,action,body,key=None):return await f.client.post(f'/api/v1/webinars/{f.id}/summary/{action}',json=body,headers={'Idempotency-Key':key or uuid4().hex})
async def draft(f,text='Что обсудили и что сделать дальше.'):
    value=(await f.client.get(f'/api/v1/webinars/{f.id}/summary')).json()
    response=await f.client.patch(f'/api/v1/webinars/{f.id}/summary',json=dict(expected_version=value['version'],title='Итоги встречи',body=text),headers={'Idempotency-Key':uuid4().hex});assert response.status_code==200,response.text;return response.json()
async def publish(f):
    value=await draft(f)
    for action in ('review','publish'):
        response=await post(f,action,dict(expected_version=value['version'],revision=value['draft']['number']));assert response.status_code==200,response.text;value=response.json()
    return value
async def preview(f,value):
    response=await post(f,'audience-preview',dict(expected_version=value['version'],revision=value['published']['number']));assert response.status_code==200,response.text;return response.json()
def send_body(value,preview):return dict(expected_version=value['version'],revision=value['published']['number'],preview_id=preview['id'],preview_hash=preview['preview_hash'])
async def dispatch(w):
    async with w.factory() as db:
        job=await claim(db,kinds=['outbox.deliver']);assert job;await db.commit()
        outbox=await db.get(OutboxMessage,UUID(job.payload['outbox_id']));payload=json.loads(unseal(outbox.payload_cipher))
        state=await process_internal(db,job,outbox,payload);await complete(db,job.id,job.claim_token,{'state':state});await db.commit();return state

@pytest.mark.asyncio
async def test_real_summary_review_publication_preview_delivery_and_replay(scenario):
    f=scenario;w=f.w
    assert (await f.client.get(f'/api/v1/webinars/{f.foreign_id}/summary')).status_code==404
    f.client.cookies.set('opora_session','summary-viewer')
    assert (await f.client.get(f'/api/v1/webinars/{f.id}/summary')).status_code==403
    assert (await f.client.get(f'/api/v1/webinars/{f.id}/summary/published')).status_code==404
    f.client.cookies.set('opora_session','summary-host');value=await draft(f)
    denied=await post(f,'publish',dict(expected_version=value['version'],revision=1));assert denied.status_code==409 and denied.json()['code']=='summary_review_required'
    async with w.factory() as db:assert await db.scalar(select(func.count()).select_from(OutboxMessage))==0
    response=await post(f,'review',dict(expected_version=value['version'],revision=1));value=response.json()
    body=dict(expected_version=value['version'],revision=1);response=await post(f,'publish',body,'publish-once');value=response.json();assert await post(f,'publish',body,'publish-once') is not None
    f.client.cookies.set('opora_session','summary-viewer');webinars=(await f.client.get('/api/v1/webinars')).json();assert len(webinars)==1 and webinars[0]['summary_available'] and not webinars[0]['can_manage_summary'];published=(await f.client.get(f'/api/v1/webinars/{f.id}/summary/published')).json();assert published['body']=='Что обсудили и что сделать дальше.' and 'draft' not in published
    f.client.cookies.set('opora_session','summary-host');audience=await preview(f,value);assert audience['eligible_count']==1 and len(audience['members'])==2
    assert next(x for x in audience['members'] if x['user_id']==str(f.blocked.id))['reason']=='no_contact'
    response=await post(f,'send',send_body(value,audience),'send-once');assert response.status_code==200,response.text
    assert (await post(f,'send',send_body(value,audience),'send-once')).json()==response.json()
    async with w.factory() as db:
        assert await db.scalar(select(func.count()).select_from(WebinarSummaryDelivery))==1
        assert await db.scalar(select(func.count()).select_from(Message))==0
    assert await dispatch(w)=='delivered'
    async with w.factory() as db:
        messages=(await db.scalars(select(Message))).all();assert len(messages)==1 and messages[0].text=='Итоги встречи\nЧто обсудили и что сделать дальше.'
        assert not await db.scalar(select(WebinarSummaryRevision).where(WebinarSummaryRevision.number==2))

@pytest.mark.asyncio
async def test_audience_changes_require_new_preview_and_current_enrollment_at_dispatch(scenario):
    f=scenario;value=await publish(f);audience=await preview(f,value)
    async with f.w.factory() as db:
        enrollment=await db.scalar(select(WebinarEnrollment).where(WebinarEnrollment.webinar_id==f.id,WebinarEnrollment.user_id==f.w.viewer.user_id));enrollment.version+=1;await db.commit()
    response=await post(f,'send',send_body(value,audience));assert response.status_code==409 and response.json()['code']=='summary_audience_changed'
    audience=await preview(f,value);assert (await post(f,'send',send_body(value,audience))).status_code==200
    async with f.w.factory() as db:
        enrollment=await db.scalar(select(WebinarEnrollment).where(WebinarEnrollment.webinar_id==f.id,WebinarEnrollment.user_id==f.w.viewer.user_id));enrollment.state='revoked';enrollment.version+=1;await db.commit()
    f.client.cookies.set('opora_session','summary-viewer');assert (await f.client.get('/api/v1/webinars')).json()==[]
    assert await dispatch(f.w)=='suppressed_summary_enrollment'
    async with f.w.factory() as db:
        assert await db.scalar(select(func.count()).select_from(Message))==0
        with pytest.raises(ApiError):await published_summary(f.id,db,f.w.viewer)

@pytest.mark.asyncio
async def test_sender_grant_revocation_suppresses_queued_summary_and_receipt(scenario):
    f=scenario;value=await publish(f);audience=await preview(f,value);body=send_body(value,audience)
    assert (await post(f,'send',body,'revoked-sender')).status_code==200
    async with f.w.factory() as db:
        grant=await db.scalar(select(PermissionGrant).join(StaffMembership).where(StaffMembership.user_id==f.w.host.user_id,PermissionGrant.permission=='notifications.send'));grant.revoked_at=utcnow();await db.commit()
    assert (await post(f,'send',body,'revoked-sender')).status_code==403
    assert await dispatch(f.w)=='suppressed_summary_sender'

@pytest.mark.asyncio
async def test_new_draft_invalidates_review_preserves_publication_and_supersedes_old_delivery(scenario):
    f=scenario;value=await publish(f);audience=await preview(f,value);assert (await post(f,'send',send_body(value,audience))).status_code==200
    newer=await draft(f,'Новые проверенные итоги.');assert newer['reviewed_revision'] is None and newer['published']['number']==1
    response=await post(f,'publish',dict(expected_version=newer['version'],revision=2));assert response.status_code==409
    stale=await post(f,'review',dict(expected_version=value['version'],revision=1));assert stale.status_code==409
    for action in ('review','publish'):
        response=await post(f,action,dict(expected_version=newer['version'],revision=2));assert response.status_code==200,response.text;newer=response.json()
    assert await dispatch(f.w)=='suppressed_summary_stale'
    async with f.w.factory() as db:assert await db.scalar(select(func.count()).select_from(WebinarSummaryRevision))==2

@pytest.mark.asyncio
async def test_edit_compare_and_swap_and_unfinished_webinar_denial(scenario):
    f=scenario
    async def edit(text):
        async with f.w.factory() as db:return await edit_summary(f.id,SummaryEditInput(expected_version=0,title='Итоги',body=text),db,f.w.host,uuid4().hex)
    results=await asyncio.gather(edit('Первый текст'),edit('Второй текст'),return_exceptions=True)
    assert sum(isinstance(x,dict) for x in results)==1
    assert next(x for x in results if isinstance(x,ApiError)).code=='version_conflict'
    async with f.w.factory() as db:
        webinar=await db.get(Webinar,f.id);webinar.state='published';await db.commit()
    response=await f.client.get(f'/api/v1/webinars/{f.id}/summary');assert response.status_code==409


@pytest.mark.asyncio
@pytest.mark.parametrize('policy',['no_contact','quiet'])
async def test_current_recipient_policy_applies_at_actual_dispatch(scenario,policy):
    f=scenario;value=await publish(f);audience=await preview(f,value);assert (await post(f,'send',send_body(value,audience))).status_code==200
    async with f.w.factory() as db:
        values=dict(foundation_id=f.w.foundation.id,user_id=f.w.viewer.user_id)
        if policy=='no_contact':values['no_contact']=True
        else:
            minute=utcnow().hour*60+utcnow().minute;values.update(quiet_enabled=True,timezone='UTC',quiet_from=(minute-1)%1440,quiet_to=(minute+60)%1440)
        db.add(NotificationPreference(**values));await db.commit()
    assert await dispatch(f.w)==('suppressed_no_contact' if policy=='no_contact' else 'deferred_quiet')
    async with f.w.factory() as db:assert await db.scalar(select(func.count()).select_from(Message))==0


@pytest.mark.asyncio
async def test_revoked_sending_session_suppresses_queued_summary(scenario):
    f=scenario;value=await publish(f);audience=await preview(f,value);assert (await post(f,'send',send_body(value,audience))).status_code==200
    async with f.w.factory() as db:
        session=await db.get(Session,f.w.host.session_id);session.revoked_at=utcnow();await db.commit()
    assert await dispatch(f.w)=='suppressed_summary_sender'
