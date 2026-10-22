"""Courses: stages and lesson order, settings, external video and course stats (real PostgreSQL)."""
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.crypto import digest
from app.core.models import PermissionGrant, Session, StaffMembership, User
from app.modules.learning.video import video_embed
from test_introduction import post, setup  # noqa: F401  (fixture)


async def staff(factory, foundation_id, token):
    async with factory() as db:
        user = User(foundation_id=foundation_id, display_name='Course author fixture')
        db.add(user)
        await db.flush()
        membership = StaffMembership(foundation_id=foundation_id, user_id=user.id)
        db.add(membership)
        await db.flush()
        for permission in ['learning.read', 'learning.write', 'learning.publish']:
            db.add(PermissionGrant(membership_id=membership.id, permission=permission))
        db.add(Session(foundation_id=foundation_id, user_id=user.id, token_hash=digest(token+str(foundation_id)), csrf_hash=digest('csrf'), csrf_cipher='fixture', expires_at=datetime.now(timezone.utc)+timedelta(days=1), mfa_at=datetime.now(timezone.utc)))
        await db.commit()
    return user


async def put(client, path, body):
    return await client.put('/api/v1'+path, json=body, headers={'Idempotency-Key': str(uuid4())})


async def patch(client, path, body):
    return await client.patch('/api/v1'+path, json=body, headers={'Idempotency-Key': str(uuid4())})


async def lesson_with_text(client, track_id, key, title, stage=None):
    created = await post(client, '/coord/learning/lessons', {'track_id': track_id, 'key': key, 'title': title, **({'stage_title': stage} if stage else {})})
    assert created.status_code == 200, created.text
    lesson = created.json()
    saved = await put(client, f"/coord/learning/lessons/{lesson['id']}/draft", {'expected_version': lesson['draft']['version'], 'title': title, 'minutes': 2, 'source': '', 'blocks': [{'type': 'text', 'text': title+' text'}]})
    assert saved.status_code == 200, saved.text
    reviewed = await post(client, f"/coord/learning/lessons/{lesson['id']}/review", {'expected_version': saved.json()['draft']['version']})
    assert reviewed.status_code == 200, reviewed.text
    return reviewed.json()


def publish_body(track):
    lessons = [item for item in track['lessons'] if not item['archived']]
    # Deliberately reversed: the release must follow the course order, not the request.
    return {'expected_version': track['version'], 'lesson_ids': [item['id'] for item in reversed(lessons)], 'lesson_draft_versions': {item['id']: item['draft']['version'] if item['draft'] else 0 for item in lessons}, 'lesson_publication_revisions': {item['id']: item['publication_revision'] for item in lessons}}


def test_video_links_are_rebuilt_as_known_embeds():
    assert video_embed('https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=5') == ('youtube', 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ')
    assert video_embed('youtu.be/dQw4w9WgXcQ') == ('youtube', 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ')
    assert video_embed('https://rutube.ru/video/0123456789abcdef0123456789abcdef/') == ('rutube', 'https://rutube.ru/play/embed/0123456789abcdef0123456789abcdef/')
    assert video_embed('https://vkvideo.ru/video-1234_5678') == ('vk', 'https://vkvideo.ru/video_ext.php?oid=-1234&id=5678')
    assert video_embed('https://vk.com/video_ext.php?oid=-1&id=2&hash=abc123') == ('vk', 'https://vkvideo.ru/video_ext.php?oid=-1&id=2&hash=abc123')
    for bad in ['https://youtube.com.evil.example/watch?v=dQw4w9WgXcQ', 'javascript:alert(1)', 'https://user@youtube.com/watch?v=dQw4w9WgXcQ', 'https://www.youtube.com:444/watch?v=dQw4w9WgXcQ', 'https://rutube.ru/video/short/', 'https://example.com/video.mp4', None, '']:
        assert video_embed(bad) is None, bad


@pytest.mark.asyncio
async def test_stages_order_publication_and_change_state(setup):
    client, factory, foundation_id = setup
    await staff(factory, foundation_id, 'author')
    client.cookies.set('opora_session', 'author'+str(foundation_id))
    track = (await post(client, '/coord/learning/tracks', {'key': 'course-order', 'title': 'Курс'})).json()
    assert track['publish_state'] == 'draft' and track['audience'] == 'manual' and track['required'] is False
    first = await lesson_with_text(client, track['id'], 'zeta', 'Первый', 'О фонде')
    second = await lesson_with_text(client, track['id'], 'alpha', 'Второй', 'О фонде')
    third = await lesson_with_text(client, track['id'], 'mid', 'Третий', 'Правила')
    track = (await client.get(f"/api/v1/coord/learning/tracks/{track['id']}")).json()
    # Creation order, not the random key, until the author changes it.
    assert [item['id'] for item in track['lessons']] == [first['id'], second['id'], third['id']]
    assert [item['stage_title'] for item in track['lessons']] == ['О фонде', 'О фонде', 'Правила']
    path = f"/coord/learning/tracks/{track['id']}/structure"
    for stages in (
        [{'title': 'О фонде', 'lesson_ids': [first['id'], second['id']]}],
        [{'title': 'О фонде', 'lesson_ids': [first['id'], second['id'], first['id']]}, {'title': 'Правила', 'lesson_ids': [third['id']]}],
        [{'title': 'О фонде', 'lesson_ids': [first['id']]}, {'title': ' О фонде ', 'lesson_ids': [second['id'], third['id']]}],
    ):
        refused = await put(client, path, {'expected_version': track['version'], 'stages': stages})
        assert refused.status_code == 422, refused.text
    assert (await put(client, path, {'expected_version': track['version']-1, 'stages': [{'title': None, 'lesson_ids': [first['id'], second['id'], third['id']]}]})).status_code == 409
    structured = await put(client, path, {'expected_version': track['version'], 'stages': [{'title': 'Правила', 'lesson_ids': [third['id'], first['id']]}, {'title': '', 'lesson_ids': [second['id']]}]})
    assert structured.status_code == 200, structured.text
    track = structured.json()
    assert [(item['id'], item['stage_title'], item['position']) for item in track['lessons']] == [(third['id'], 'Правила', 0), (first['id'], 'Правила', 1), (second['id'], None, 2)]
    published = await post(client, f"/coord/learning/tracks/{track['id']}/publish", publish_body(track))
    assert published.status_code == 200, published.text
    track = published.json()
    assert track['publish_state'] == 'published'
    release = track['releases'][0]
    order = [item['current_version_id'] for item in track['lessons']]
    assert release['lesson_version_ids'] == order
    # Opening a published lesson for editing is not a change yet.
    opened = await post(client, f"/coord/learning/lessons/{third['id']}/edit")
    assert opened.json()['draft']['status'] == 'published'
    track = (await client.get(f"/api/v1/coord/learning/tracks/{track['id']}")).json()
    assert track['publish_state'] == 'published'
    renamed = await put(client, path, {'expected_version': track['version'], 'stages': [{'title': 'Правила фонда', 'lesson_ids': [third['id'], first['id']]}, {'title': None, 'lesson_ids': [second['id']]}]})
    assert renamed.json()['publish_state'] == 'changed'
    track = renamed.json()
    republished = await post(client, f"/coord/learning/tracks/{track['id']}/publish", publish_body(track))
    assert republished.status_code == 200, republished.text
    track = republished.json()
    async with factory() as db:
        from app.modules.learning.models import LearningRelease
        current = await db.get(LearningRelease, __import__('uuid').UUID(track['current_release_id']))
        assert [stage['title'] for stage in current.stages] == ['Правила фонда', None]
        assert [len(stage['lesson_version_ids']) for stage in current.stages] == [2, 1]
    assert track['publish_state'] == 'published'
    retitled = await patch(client, f"/coord/learning/tracks/{track['id']}", {'expected_version': track['version'], 'title': 'Новое название'})
    assert retitled.status_code == 200 and retitled.json()['publish_state'] == 'changed'
    # A newly added lesson goes last and makes the course "changed" until published.
    added = await post(client, '/coord/learning/lessons', {'track_id': track['id'], 'key': 'added', 'title': 'Новый урок'})
    track = (await client.get(f"/api/v1/coord/learning/tracks/{track['id']}")).json()
    assert track['lessons'][-1]['id'] == added.json()['id'] and track['lessons'][-1]['position'] == 3


@pytest.mark.asyncio
async def test_external_video_image_and_simulator_blocks(setup):
    client, factory, foundation_id = setup
    await staff(factory, foundation_id, 'video')
    client.cookies.set('opora_session', 'video'+str(foundation_id))
    track = (await post(client, '/coord/learning/tracks', {'key': 'course-video', 'title': 'Видео'})).json()
    lesson = (await post(client, '/coord/learning/lessons', {'track_id': track['id'], 'key': 'video', 'title': 'Видео'})).json()
    draft_path = f"/coord/learning/lessons/{lesson['id']}/draft"
    body = {'expected_version': lesson['draft']['version'], 'title': 'Видео', 'minutes': 3, 'source': '', 'blocks': [
        {'type': 'video', 'url': 'https://youtu.be/dQw4w9WgXcQ', 'embed_url': 'https://evil.example/embed', 'title': 'Разбор'},
        {'type': 'video', 'url': 'https://evil.example/video'},
        {'type': 'image'},
        {'type': 'sim', 'scenario_id': str(uuid4())},
    ]}
    saved = await put(client, draft_path, body)
    assert saved.status_code == 200, saved.text
    blocks = saved.json()['draft']['blocks']
    assert blocks[0]['embed_url'] == 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ' and blocks[0]['provider'] == 'youtube'
    assert 'embed_url' not in blocks[1]
    errors = (await post(client, f"/coord/learning/lessons/{lesson['id']}/validate")).json()['errors']
    assert errors == ['Блок 2: нужна ссылка на VK Видео, Rutube или YouTube', 'Блок 3: загрузите картинку', 'Блок 4: выберите опубликованный сценарий тренажёра']
    body.update(expected_version=saved.json()['draft']['version'], blocks=[{'type': 'video', 'url': 'https://rutube.ru/video/0123456789abcdef0123456789abcdef/', 'title': 'Кодекс'}, {'type': 'video', 'embed_url': 'https://evil.example/embed'}])
    saved = await put(client, draft_path, body)
    lesson = (await post(client, f"/coord/learning/lessons/{lesson['id']}/review", {'expected_version': saved.json()['draft']['version']})).json()
    assert lesson['draft']['status'] == 'reviewed'
    preview = (await client.get(f"/api/v1/coord/learning/lessons/{lesson['id']}/preview")).json()
    assert preview['blocks'][0]['embed_url'] == 'https://rutube.ru/play/embed/0123456789abcdef0123456789abcdef/'
    assert 'embed_url' not in preview['blocks'][1]
    track = (await client.get(f"/api/v1/coord/learning/tracks/{track['id']}")).json()
    published = await post(client, f"/coord/learning/tracks/{track['id']}/publish", publish_body(track))
    assert published.status_code == 200, published.text
    # Even a tampered stored block only ever yields an embed rebuilt from its link.
    async with factory() as db:
        from sqlalchemy import select
        from app.modules.learning.models import LessonBlock
        version_id = published.json()['lessons'][0]['current_version_id']
        stored = (await db.scalars(select(LessonBlock).where(LessonBlock.lesson_version_id == __import__('uuid').UUID(version_id)).order_by(LessonBlock.position))).all()
        stored[0].content = {**stored[0].content, 'embed_url': 'https://evil.example/embed'}
        await db.commit()
    preview = (await client.get(f"/api/v1/coord/learning/lessons/{lesson['id']}/preview")).json()
    assert preview['blocks'][0]['embed_url'] == 'https://rutube.ru/play/embed/0123456789abcdef0123456789abcdef/'


@pytest.mark.asyncio
async def test_new_volunteer_audience_assigns_course_and_counts_progress(setup):
    client, factory, foundation_id = setup
    await staff(factory, foundation_id, 'settings')
    client.cookies.set('opora_session', 'settings'+str(foundation_id))
    track = (await post(client, '/coord/learning/tracks', {'key': 'course-auto', 'title': 'Для всех'})).json()
    lesson = await lesson_with_text(client, track['id'], 'auto', 'Урок')
    track = (await client.get(f"/api/v1/coord/learning/tracks/{track['id']}")).json()
    track = (await post(client, f"/coord/learning/tracks/{track['id']}/publish", publish_body(track))).json()
    assert track['stats'] == {'completed': 0, 'learning': 0, 'stuck': 0}
    updated = await patch(client, f"/coord/learning/tracks/{track['id']}", {'expected_version': track['version'], 'audience': 'new', 'required': True, 'description': ' Коротко о курсе '})
    assert updated.status_code == 200, updated.text
    track = updated.json()
    assert (track['audience'], track['required'], track['description'], track['publish_state']) == ('new', True, 'Коротко о курсе', 'published')
    assert (await patch(client, f"/coord/learning/tracks/{track['id']}", {'expected_version': track['version'], 'audience': 'everyone'})).status_code == 422
    # Accounts get the course automatically; the introduction stays first.
    own = (await client.get('/api/v1/me/preparation')).json()['assignments']
    assert [item['track_key'] for item in own] == ['introduction', 'course-auto']
    course = own[1]
    track = (await client.get(f"/api/v1/coord/learning/tracks/{track['id']}")).json()
    assert track['stats'] == {'completed': 0, 'learning': 1, 'stuck': 0}
    await post(client, f"/learning/progress/{course['lessons'][0]['id']}/complete", {'assignment_id': course['id']})
    await post(client, '/policy-acknowledgements', {'assignment_id': course['id']})
    track = (await client.get(f"/api/v1/coord/learning/tracks/{track['id']}")).json()
    assert track['stats'] == {'completed': 1, 'learning': 0, 'stuck': 0}
    # Candidates' registration sessions still only get the introduction.
    client.cookies.set('opora_session', 'one'+str(foundation_id))
    candidate = (await client.get('/api/v1/me/preparation')).json()['assignments']
    assert [item['track_key'] for item in candidate] == ['introduction']
    assert lesson['draft']['status'] == 'reviewed'
    # Every lesson done but the final test not submitted: stuck on the test.
    for item in candidate[0]['lessons']:
        assert (await post(client, f"/learning/progress/{item['id']}/complete", {'assignment_id': candidate[0]['id']})).status_code == 200
    client.cookies.set('opora_session', 'settings'+str(foundation_id))
    introduction = (await client.get(f"/api/v1/coord/learning/tracks/{candidate[0]['track_id']}")).json()
    assert introduction['stats'] == {'completed': 0, 'learning': 2, 'stuck': 1}
    assert (introduction['audience'], introduction['required']) == ('new', True)
