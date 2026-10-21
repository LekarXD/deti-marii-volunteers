"""Recording authority + learning transaction integration, synthetic DB media fixture.

This proves exact-review/CAS/retention and publication ledger semantics. Actual
capture/encoding belongs to the recordings driver's independent media proof.
"""
from datetime import datetime,timedelta,timezone
from uuid import UUID,uuid4
import pytest
from sqlalchemy import select,func
from app.core.crypto import digest
from app.core.models import User,StaffMembership,PermissionGrant,MediaAsset,Session
from app.modules.learning.models import Lesson,LessonDraft,LessonVersion,LearningTrack
from app.modules.studio import models as studio_models
from app.modules.recordings.models import RecordingProject,StudioCaptureSession,RecordingTake,RecordingRenderVersion,RecordingReview,RecordingPublication
from test_introduction import setup,post

@pytest.mark.asyncio
async def test_exact_recording_review_publication_ledger_and_previous_primary_retention(setup):
    client,factory,fid=setup
    old=(await client.get('/api/v1/me/preparation')).json()['assignments'][0]
    lid=UUID(old['lessons'][0]['lesson_id']);tid=UUID(old['track_id']);rid=uuid4()
    async with factory() as db:
        user=User(foundation_id=fid,display_name='Synthetic recording publication fixture');db.add(user);await db.flush()
        member=StaffMembership(foundation_id=fid,user_id=user.id);db.add(member);await db.flush()
        for name in ('learning.read','learning.write','learning.publish','recordings.manage','recordings.publish'):db.add(PermissionGrant(membership_id=member.id,permission=name))
        session=Session(foundation_id=fid,user_id=user.id,token_hash=digest('recording'+str(fid)),csrf_hash=digest('csrf'),csrf_cipher='fixture',expires_at=datetime.now(timezone.utc)+timedelta(days=1),mfa_at=datetime.now(timezone.utc));db.add(session);await db.flush()
        project=RecordingProject(foundation_id=fid,owner_user_id=user.id,target_lesson_id=lid,title='Synthetic DB fixture',privacy_state='approved');db.add(project);await db.flush()
        studio=studio_models.StudioSession(foundation_id=fid,resource_kind='lesson_recording_project',resource_id=project.id,host_user_id=user.id,room_name=uuid4().hex,generation=1,scene={});db.add(studio);await db.flush()
        capture=StudioCaptureSession(project_id=project.id,studio_session_id=studio.id,host_auth_session_id=session.id,generation=1);db.add(capture);await db.flush()
        take=RecordingTake(project_id=project.id,capture_session_id=capture.id,number=1,generation=1,state='captured',projection={},projection_hash='a'*64);db.add(take);await db.flush()
        asset=MediaAsset(foundation_id=fid,owner_user_id=user.id,purpose='recording.output',resource_type='recording_render',resource_id=rid,storage_key=uuid4().hex,content_type='video/mp4',expected_size=100,received_size=100,checksum='b'*64,state='ready');db.add(asset);await db.flush()
        render=RecordingRenderVersion(id=rid,project_id=project.id,take_id=take.id,generation=1,state='preview_ready',manifest={'synthetic_db_fixture':True},render_hash='c'*64,asset_id=asset.id,content_hash=asset.checksum,quality='verified',duration_ms=1000);db.add(render)
        draft=LessonDraft(lesson_id=lid,foundation_id=fid,title='Recording lesson fixture',minutes=1,source='Synthetic review fixture',blocks=[{'type':'video','asset_id':str(asset.id),'title':'Private review fixture'}],version=2,status='reviewed');db.add(draft)
        stable=await db.get(Lesson,lid);track=await db.get(LearningTrack,tid)
        old_primary=stable.current_version_id;revision=stable.publication_revision;track_version=track.version
        count=await db.scalar(select(func.count()).select_from(LessonVersion).where(LessonVersion.lesson_id==lid))
        await db.commit();uid=user.id
    client.cookies.set('opora_session','recording'+str(fid))
    body={'expected_version':track_version,'lesson_ids':[str(lid)],'lesson_draft_versions':{str(lid):2},'lesson_publication_revisions':{str(lid):revision}}
    # A private render cannot replace the primary without its exact human review.
    denied=await post(client,f'/coord/learning/tracks/{tid}/publish',body)
    assert denied.status_code==409 and denied.json()['code']=='recording_approval_required'
    async with factory() as db:
        assert (await db.get(Lesson,lid)).current_version_id==old_primary
        assert (await db.get(LearningTrack,tid)).current_release_id==UUID(old['release_id'])
        assert await db.scalar(select(func.count()).select_from(LessonVersion).where(LessonVersion.lesson_id==lid))==count
        db.add(RecordingReview(render_id=rid,render_hash='c'*64,content_hash='b'*64,decision='approved',reviewer_user_id=uid,reason='Synthetic DB review fixture'));await db.commit()
    published=await post(client,f'/coord/learning/tracks/{tid}/publish',body,key='publish-recording')
    assert published.status_code==200,published.text
    replay=await post(client,f'/coord/learning/tracks/{tid}/publish',body,key='publish-recording')
    assert replay.status_code==200 and replay.json()==published.json()
    async with factory() as db:
        stable=await db.get(Lesson,lid)
        assert stable.current_version_id!=old_primary and await db.get(LessonVersion,old_primary)
        records=(await db.scalars(select(RecordingPublication).where(RecordingPublication.render_id==rid))).all()
        assert len(records)==1 and records[0].lesson_version_id==stable.current_version_id
        assert records[0].render_hash=='c'*64 and records[0].state=='published'
