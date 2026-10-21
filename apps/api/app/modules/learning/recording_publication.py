"""P18E bridge: approval stays exclusively in recordings, publication in learning.

Preflight happens BEFORE the track/lesson/draft locks. Claims are opaque and
transaction-bound; the recording owner validates them again before pointer swap.
"""
from importlib import import_module
from uuid import UUID
from sqlalchemy import select
from app.core.errors import ApiError
from app.core.models import MediaAsset
from .models import Lesson,LessonBlock,LessonDraft


def publication_key(asset_id,lesson_id,draft_version):
    return str(asset_id),str(lesson_id),draft_version


def recording_module():
    try:
        return import_module('app.modules.recordings.publication')
    except ModuleNotFoundError as error:
        if error.name not in {'app.modules.recordings','app.modules.recordings.publication'}:raise
        raise ApiError(503,'recording_publication_unavailable','Публикация записи пока недоступна')


async def prepare_recording_assets(db,principal,lesson_ids,expected_draft_versions):
    """Read draft references, then let A1 acquire recording locks in stable order."""
    requests=[]
    for lesson_id in lesson_ids:
        stable=await db.scalar(select(Lesson).where(Lesson.id==lesson_id,Lesson.foundation_id==principal.foundation_id))
        if stable is None:raise ApiError(404,'lesson_not_found','Урок не найден')
        draft=await db.scalar(select(LessonDraft).where(LessonDraft.lesson_id==stable.id))
        expected=expected_draft_versions.get(stable.id,-1)
        if (draft.version if draft else 0)!=expected:
            raise ApiError(409,'version_conflict','Редакция урока изменена',current_version=draft.version if draft else 0)
        if draft and draft.status!='published':blocks=draft.blocks
        else:blocks=[block.content for block in (await db.scalars(select(LessonBlock).where(LessonBlock.lesson_version_id==stable.current_version_id))).all()]
        for block in blocks:
            if not block.get('asset_id') or block.get('type') not in {'video','file'}:continue
            try:asset_id=UUID(str(block['asset_id']))
            except ValueError:raise ApiError(422,'invalid_asset','Проверьте файл урока')
            asset=await db.scalar(select(MediaAsset).where(MediaAsset.id==asset_id,MediaAsset.foundation_id==principal.foundation_id))
            if asset is not None and asset.purpose.startswith('recording.'):
                request=dict(asset_id=asset.id,target_lesson_id=stable.id,expected_draft_version=expected)
                if request not in requests:requests.append(request)
    if not requests:return {}
    module=recording_module()
    bulk=getattr(module,'prepare_recording_publications',None)
    if len(requests)>1:
        if bulk is None:raise ApiError(503,'recording_bulk_publication_unavailable','Публикация нескольких записей пока недоступна')
        claims=await bulk(db,principal,requests=requests)
        if len(claims)!=len(requests):raise ApiError(503,'recording_publication_unavailable','Не удалось проверить записи')
    else:
        claims=[await module.prepare_recording_publication(db,principal,**requests[0])]
    return {publication_key(request['asset_id'],request['target_lesson_id'],request['expected_draft_version']):claim for request,claim in zip(requests,claims,strict=True)}


async def validate_recording_assets(db,principal,lesson_id,draft_version,blocks,claims):
    for block in blocks:
        if block.get('type') not in {'video','file'} or not block.get('asset_id'):continue
        asset=await db.scalar(select(MediaAsset).where(MediaAsset.id==UUID(str(block['asset_id'])),MediaAsset.foundation_id==principal.foundation_id))
        if asset is None or not asset.purpose.startswith('recording.'):continue
        claim=claims.get(publication_key(asset.id,lesson_id,draft_version))
        if claim is None:raise ApiError(409,'recording_approval_required','Сначала согласуйте именно эту запись для урока')
        await recording_module().validate_recording_claim(db,claim,asset_id=asset.id,target_lesson_id=lesson_id,expected_draft_version=draft_version)


async def record_recording_assets(db,principal,lesson_id,draft_version,lesson_version_id,claims):
    owned=[claim for (asset,target,version),claim in claims.items() if target==str(lesson_id) and version==draft_version]
    if not owned:return
    record=getattr(recording_module(),'record_recording_publications',None)
    if record is None:raise ApiError(503,'recording_publication_unavailable','Публикация записи пока недоступна')
    await record(db,claims=owned,lesson_version_id=lesson_version_id,actor_user_id=principal.user_id)


async def prepare_recording_attachment(db,principal,lesson_id,draft_version,render_id,render_hash):
    # Exact approval/owner/privacy/generation remain the recording authority's
    # decision, with its locks taken before any learning pointer/draft lock.
    module=recording_module()
    models=import_module('app.modules.recordings.models')
    render=(await db.execute(select(models.RecordingRenderVersion.asset_id,models.RecordingRenderVersion.render_hash).where(models.RecordingRenderVersion.id==render_id))).one_or_none()
    if render is None or not render.asset_id or render.render_hash!=render_hash:
        raise ApiError(409,'recording_approval_required','Запись изменилась. Откройте актуальную согласованную версию')
    claim=await module.prepare_recording_publication(db,principal,asset_id=render.asset_id,target_lesson_id=lesson_id,expected_draft_version=draft_version)
    if claim.render_id!=render_id or claim.render_hash!=render_hash:
        raise ApiError(409,'recording_approval_required','Запись изменилась. Откройте актуальную согласованную версию')
    return claim
