"""Transaction-bound approval claims. Learning owns all immutable lesson publication."""
from dataclasses import dataclass,field
from uuid import UUID
from sqlalchemy import select
from app.core.auth import authz_guard
from app.core.errors import ApiError
from app.core.models import MediaAsset
from .models import RecordingProject,RecordingRenderVersion,RecordingTake,RecordingReview
from . import service
@dataclass(frozen=True)
class RecordingPublicationClaim:
    asset_id:UUID
    project_id:UUID
    target_lesson_id:UUID
    expected_draft_version:int
    render_id:UUID
    render_hash:str
    content_hash:str
    generation:int
    review_id:UUID
    _transaction:object=field(repr=False,compare=False)

def invalid():raise ApiError(409,'recording_approval_required','Согласуйте именно эту запись для выбранного урока')
async def prepare_recording_publications(db,principal,*,requests):
    await authz_guard(db,principal)
    if not principal.has_permission('recordings.publish'):raise ApiError(403,'permission_denied','Недостаточно прав для публикации записи')
    if not 1<=len(requests)<=64:raise ApiError(422,'recording_publication_limit','Проверьте число записей')
    resolved=[]
    for request in requests:
        asset_id=UUID(str(request['asset_id']))
        render=await db.scalar(select(RecordingRenderVersion).where(RecordingRenderVersion.asset_id==asset_id))
        if render is None:invalid()
        resolved.append((request,render.id,render.project_id))
    owners={}
    # Stable order across every publication path; no lesson locks have been taken yet.
    for id in sorted({item[2] for item in resolved},key=str):owners[id]=await service.project(db,principal,id,True)
    renders={}
    for id in sorted({item[1] for item in resolved},key=str):
        renders[id]=await db.scalar(select(RecordingRenderVersion).where(RecordingRenderVersion.id==id).with_for_update().execution_options(populate_existing=True))
    assets={}
    for id in sorted({UUID(str(item[0]['asset_id'])) for item in resolved},key=str):
        assets[id]=await db.scalar(select(MediaAsset).where(MediaAsset.id==id).with_for_update().execution_options(populate_existing=True))
    claims=[]
    for request,rid,pid in resolved:
        owner=owners[pid];render=renders[rid];asset=assets[UUID(str(request['asset_id']))]
        target=UUID(str(request['target_lesson_id']))
        take=await db.get(RecordingTake,render.take_id,populate_existing=True)
        review=await db.scalar(select(RecordingReview).where(RecordingReview.render_id==rid).order_by(RecordingReview.created_at.desc(),RecordingReview.id.desc()).limit(1))
        if not asset or asset.foundation_id!=principal.foundation_id or asset.state!='ready' or asset.purpose!='recording.output' or asset.resource_id!=render.id or asset.checksum!=render.content_hash or owner.target_lesson_id!=target or owner.state=='archived' or owner.privacy_state!='approved' or render.state not in ('preview_ready','degraded') or take.state!='captured' or take.generation!=render.generation or not review or review.decision!='approved' or review.render_hash!=render.render_hash or review.content_hash!=render.content_hash:invalid()
        claims.append(RecordingPublicationClaim(asset.id,pid,target,request['expected_draft_version'],rid,render.render_hash,render.content_hash,render.generation,review.id,db.sync_session.get_transaction()))
    return claims
async def prepare_recording_publication(db,principal,*,asset_id,target_lesson_id,expected_draft_version):
    return (await prepare_recording_publications(db,principal,requests=[dict(asset_id=asset_id,target_lesson_id=target_lesson_id,expected_draft_version=expected_draft_version)]))[0]
async def validate_recording_claim(db,claim,*,asset_id,target_lesson_id,expected_draft_version):
    # Locks are still held in this exact transaction. Do not acquire recording locks after learning locks.
    if not isinstance(claim,RecordingPublicationClaim) or claim._transaction is None or db.sync_session.get_transaction() is not claim._transaction or not claim._transaction.is_active or (claim.asset_id,claim.target_lesson_id,claim.expected_draft_version)!=(asset_id,target_lesson_id,expected_draft_version):invalid()

async def record_recording_publications(db,*,claims,lesson_version_id,actor_user_id):
    """Learning calls after creating its immutable version, while preflight locks remain held."""
    from app.modules.learning.models import LessonVersion
    from .models import RecordingPublication
    version=await db.get(LessonVersion,lesson_version_id)
    if version is None:invalid()
    for claim in claims:
        await validate_recording_claim(db,claim,asset_id=claim.asset_id,target_lesson_id=version.lesson_id,expected_draft_version=claim.expected_draft_version)
        project=await db.get(RecordingProject,claim.project_id)
        if project.owner_user_id!=actor_user_id:invalid()
        prior=await db.scalar(select(RecordingPublication.id).where(RecordingPublication.render_id==claim.render_id,RecordingPublication.lesson_version_id==lesson_version_id,RecordingPublication.state=='published'))
        if prior is None:db.add(RecordingPublication(project_id=claim.project_id,render_id=claim.render_id,render_hash=claim.render_hash,lesson_version_id=lesson_version_id,state='published',actor_user_id=actor_user_id))
    await db.flush()
