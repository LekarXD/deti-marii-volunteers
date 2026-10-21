"""Explicit append-only imports of approved introduction source revisions."""
import hashlib
import json
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5
from sqlalchemy import select,func
from sqlalchemy.ext.asyncio import AsyncSession
from .models import AssessmentQuestion,AssessmentVersion,LearningRelease,LearningTrack,Lesson,LessonBlock,LessonVersion

FIXTURES=Path(__file__).parent/'fixtures'

def manifest():
    return json.loads((FIXTURES/'introduction-manifest.json').read_text())

def source_content(source_version:int|None=None)->dict:
    source_version=source_version or manifest()['current']
    entry=manifest()['versions'][str(source_version)]
    raw=(FIXTURES/entry['fixture_file']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=entry['fixture_sha256']:
        raise RuntimeError('Immutable introduction fixture hash does not match its manifest')
    return json.loads(raw)

def fixture_id(foundation_id:UUID,key:str,source_version:int=1)->UUID:
    return uuid5(NAMESPACE_URL,f'opora:{foundation_id}:introduction:v{source_version}:{key}')

async def import_source_version(db,foundation_id,source_version):
    track_id=fixture_id(foundation_id,'track')
    content=source_content(source_version)
    entry=manifest()['versions'][str(source_version)]
    assert len(content['modules'])==4 and len(content['test']['questions'])==10
    track=await db.get(LearningTrack,track_id)
    if track is None:
        track=LearningTrack(id=track_id,foundation_id=foundation_id,key='introduction',title=content['title'])
        db.add(track);await db.flush()
    release_id=fixture_id(foundation_id,'release',source_version)
    # Do not overwrite a coordinator-authored current release when fixtures rerun.
    promote=track.current_release_id in (None,fixture_id(foundation_id,'release',1))
    existing=await db.get(LearningRelease,release_id)
    if existing:
        if promote:track.current_release_id=existing.id
        return track_id
    versions=[]
    for module in content['modules']:
        lesson_id=fixture_id(foundation_id,module['id'])
        version_id=fixture_id(foundation_id,module['id']+':v1',source_version)
        stable=await db.get(Lesson,lesson_id)
        if stable is None:
            stable=Lesson(id=lesson_id,track_id=track_id,foundation_id=foundation_id,key=module['id'])
            db.add(stable);await db.flush()
        number=(await db.scalar(select(func.max(LessonVersion.number)).where(LessonVersion.lesson_id==lesson_id)) or 0)+1
        db.add(LessonVersion(id=version_id,lesson_id=lesson_id,number=number,title=module['title'],minutes=module['minutes'],source=module['source'],presentation_mode=module.get('mode','feed')))
        await db.flush()
        for position,block in enumerate(module['blocks']):
            db.add(LessonBlock(id=fixture_id(foundation_id,f"{module['id']}:block:{position}",source_version),lesson_version_id=version_id,position=position,content=block))
        versions.append(str(version_id))
        if promote:
            stable.current_version_id=version_id
            stable.publication_revision+=1
    assessment_id=fixture_id(foundation_id,'assessment',source_version)
    db.add(AssessmentVersion(id=assessment_id,foundation_id=foundation_id,title=content['test']['title'],intro=content['test']['intro'],allow_repeat=source_version<2))
    await db.flush()
    for position,question in enumerate(content['test']['questions']):
        db.add(AssessmentQuestion(id=fixture_id(foundation_id,f'question:{position}',source_version),assessment_version_id=assessment_id,position=position,prompt=question['q'],options=question['o'],correct_option=question['a'],explanation=question['e']))
    number=(await db.scalar(select(func.max(LearningRelease.number)).where(LearningRelease.track_id==track_id)) or 0)+1
    db.add(LearningRelease(id=release_id,track_id=track_id,foundation_id=foundation_id,number=number,title=content['title'],intro=content['intro'],lesson_version_ids=versions,assessment_version_id=assessment_id,source_revision=entry['revision'],source_hash=entry['source_sha256'],change_note='Материалы знакомства обновлены. Ранее завершённое знакомство сохранено в истории.' if source_version>1 else '',reacknowledgement_required=False))
    if promote:
        track.current_release_id=release_id
        track.version+=1
    await db.flush()
    return track_id

async def seed_introduction(db:AsyncSession,foundation_id:UUID,source_version:int|None=None)->UUID:
    """Import current source as a new release; never update old snapshots/history."""
    source_version=source_version or manifest()['current']
    track_id=await import_source_version(db,foundation_id,1)
    if source_version!=1:track_id=await import_source_version(db,foundation_id,source_version)
    return track_id
