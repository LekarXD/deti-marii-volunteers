"""Explicit source import. Run from the foundation seed; never demo fallback."""
import json
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import AssessmentQuestion, AssessmentVersion, LearningRelease, LearningTrack, Lesson, LessonBlock, LessonVersion


def source_content() -> dict:
    return json.loads((Path(__file__).parent / "fixtures" / "introduction.json").read_text())


def fixture_id(foundation_id: UUID, key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"opora:{foundation_id}:introduction:v1:{key}")


async def seed_introduction(db: AsyncSession, foundation_id: UUID) -> UUID:
    """Idempotently import exact prototype 4 modules / 10 questions, without commit."""
    track_id = fixture_id(foundation_id, "track")
    if await db.get(LearningTrack, track_id):
        return track_id
    content = source_content()
    assert len(content["modules"]) == 4 and len(content["test"]["questions"]) == 10
    release_id, assessment_id = fixture_id(foundation_id, "release"), fixture_id(foundation_id, "assessment")
    db.add(LearningTrack(id=track_id, foundation_id=foundation_id, key="introduction", title=content["title"], current_release_id=release_id))
    await db.flush()
    versions = []
    for module in content["modules"]:
        lesson_id = fixture_id(foundation_id, module["id"])
        version_id = fixture_id(foundation_id, module["id"] + ":v1")
        versions.append(str(version_id))
        db.add(Lesson(id=lesson_id, track_id=track_id, foundation_id=foundation_id, key=module["id"], current_version_id=version_id, publication_revision=1))
        await db.flush()
        db.add(LessonVersion(id=version_id, lesson_id=lesson_id, number=1, title=module["title"], minutes=module["minutes"], source=module["source"]))
        await db.flush()
        for position, block in enumerate(module["blocks"]):
            db.add(LessonBlock(id=fixture_id(foundation_id, f"{module['id']}:block:{position}"), lesson_version_id=version_id, position=position, content=block))
    db.add(AssessmentVersion(id=assessment_id, foundation_id=foundation_id, title=content["test"]["title"], intro=content["test"]["intro"]))
    await db.flush()
    for position, question in enumerate(content["test"]["questions"]):
        db.add(AssessmentQuestion(id=fixture_id(foundation_id, f"question:{position}"), assessment_version_id=assessment_id, position=position, prompt=question["q"], options=question["o"], correct_option=question["a"], explanation=question["e"]))
    db.add(LearningRelease(id=release_id, track_id=track_id, foundation_id=foundation_id, number=1, title=content["title"], intro=content["intro"], lesson_version_ids=versions, assessment_version_id=assessment_id))
    await db.flush()
    return track_id
