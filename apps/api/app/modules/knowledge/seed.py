"""Explicit idempotent import of the already-published introduction, no AI."""
from uuid import UUID,NAMESPACE_URL,uuid5
from sqlalchemy import select
from app.worker.queue import enqueue_job
from app.modules.learning.models import LearningTrack,LearningRelease,LessonBlock,LessonVersion
from .models import KnowledgeSource,SourceVersion

def extract_published_blocks(blocks):
    lines=[]
    def visit(value):
        if isinstance(value,str):lines.append(value)
        elif isinstance(value,list):
            for item in value:visit(item)
        elif isinstance(value,dict):
            for key in ['title','text','intro','items']:
                if key in value:visit(value[key])
    for block in blocks:
        if block.get('type') not in {'quiz','video','file'}:visit(block)
    return '\n\n'.join(lines)[:200000]

async def seed_knowledge(db,foundation_id:UUID):
    """Call after seed_introduction in the explicit development fixture command.

    Never overwrites an edited/archived source. Indexing stays a real queued job.
    """
    track=await db.scalar(select(LearningTrack).where(LearningTrack.foundation_id==foundation_id,LearningTrack.key=='introduction'))
    if track is None or not track.current_release_id:return 0
    release=await db.get(LearningRelease,track.current_release_id)
    count=0
    for raw_id in release.lesson_version_ids:
        version=await db.get(LessonVersion,UUID(raw_id))
        source_id=uuid5(NAMESPACE_URL,f'opora:{foundation_id}:knowledge:introduction:{version.lesson_id}')
        source=await db.scalar(select(KnowledgeSource).where(KnowledgeSource.id==source_id).with_for_update().execution_options(populate_existing=True))
        if source and (source.archived or source.lesson_version_id==version.id):continue
        blocks=(await db.scalars(select(LessonBlock).where(LessonBlock.lesson_version_id==version.id).order_by(LessonBlock.position))).all()
        body=extract_published_blocks([block.content for block in blocks])
        number=1
        if source:
            # Only advance untouched system imports. Manual edits/visibility changes
            # and archived sources remain under their coordinator's control.
            previous=await db.get(SourceVersion,source.current_version_id) if source.current_version_id else None
            old_lesson=await db.get(LessonVersion,source.lesson_version_id) if source.lesson_version_id else None
            old_blocks=(await db.scalars(select(LessonBlock).where(LessonBlock.lesson_version_id==source.lesson_version_id).order_by(LessonBlock.position))).all()
            expected=extract_published_blocks([block.content for block in old_blocks])
            if not previous or not old_lesson or source.owner_user_id or source.kind!='lesson' or source.title!=old_lesson.title or source.draft_body!=expected or source.draft_visibility!='all' or previous.body!=expected or previous.visibility!='all' or previous.title!=old_lesson.title:
                continue
            number=previous.number+1
            source.title=version.title;source.draft_body=body;source.lesson_version_id=version.id
            source.draft_version+=1;source.reviewed_version=None
            source.index_generation+=1;source.index_state='queued';source.index_error=None
        else:
            source=KnowledgeSource(id=source_id,foundation_id=foundation_id,title=version.title,kind='lesson',draft_body=body,draft_visibility='all',lesson_version_id=version.id,index_state='queued',index_generation=1)
            db.add(source);await db.flush()
        publication=SourceVersion(source_id=source.id,foundation_id=foundation_id,number=number,title=version.title,body=body,visibility='all')
        db.add(publication);await db.flush()
        source.current_version_id=publication.id
        enqueue_job(db,foundation_id,'knowledge.index',{'source_id':str(source.id),'source_version_id':str(publication.id),'generation':source.index_generation})
        count+=1
    return count
