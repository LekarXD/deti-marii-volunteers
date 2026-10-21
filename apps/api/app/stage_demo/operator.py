import json
import os
import stat
from pathlib import Path
from uuid import UUID
from sqlalchemy import select, func, text
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.crypto import digest, unseal
from app.core.models import AuthChallenge, ContactChannel, Foundation, MutationReceipt, OutboxMessage, User

SEED_KEY = 'opora-stage-synthetic-v1'
FOUNDATION_NAME = 'Опора — демонстрационный контур (вымышленные данные)'
CONFIRMATION = 'ONLY_SYNTHETIC_OPORA_STAGE'

def validate_runtime(settings, confirmation):
    if confirmation != CONFIRMATION or os.getenv('OPORA_STAGE_FIXTURE_SEED_ALLOW') != 'true':
        raise RuntimeError('Explicit operator opt-in is required')
    if settings.environment != 'staging' or settings.dev_inbox or not settings.cookie_secure:
        raise RuntimeError('Only secure staging with dev-inbox disabled is allowed')
    if settings.smtp_host or os.getenv('OPORA_TELEGRAM_BOT_TOKEN'):
        raise RuntimeError('Synthetic stage fixtures require external mail and Telegram providers to be absent')

def private_directory(path):
    parent = Path(path).absolute().parent
    if not parent.exists() or parent.is_symlink() or stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise RuntimeError('Use an existing private directory with mode0700')
    return parent

def write_new_private(path, value):
    path = Path(path).absolute()
    private_directory(path)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(value, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path

def read_credentials(path, foundation_id):
    path = Path(path).absolute()
    private_directory(path)
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise RuntimeError('Credential file must be a regular mode0600 private file')
    value = json.loads(path.read_text())
    if value.get('seed_key') != SEED_KEY or value.get('foundation_id') != str(foundation_id):
        raise RuntimeError('Credentials do not belong to this synthetic foundation')
    return value

async def database_guard(db, foundation_id):
    if await db.scalar(text('SELECT current_database()')) != 'opora_stage':
        raise RuntimeError('Refusing a database other than the designated opora_stage')
    other = await db.scalar(select(Foundation.id).where((Foundation.id != foundation_id) | (Foundation.name != FOUNDATION_NAME)).limit(1))
    if other: raise RuntimeError('Refusing a database with another foundation or non-demo name')

async def seed(db, credentials_path, confirmation):
    settings = get_settings()
    validate_runtime(settings, confirmation)
    private_directory(credentials_path)
    await database_guard(db, settings.foundation_id)
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'), {'key':SEED_KEY})
    marker = await db.scalar(select(MutationReceipt).where(MutationReceipt.actor_id == f'stage-seed:{settings.foundation_id}', MutationReceipt.operation == 'stage.demo.seed', MutationReceipt.key == SEED_KEY))
    if marker:
        credentials = read_credentials(credentials_path, settings.foundation_id)
        if credentials.get('manifest') != marker.result:
            raise RuntimeError('Private credentials and committed seed marker do not match')
        return {'status':'already_seeded', 'private_file':str(Path(credentials_path).absolute())}
    if await db.scalar(select(func.count()).select_from(User)):
        raise RuntimeError('First seed requires an empty newly created staging account database')
    if Path(credentials_path).exists(): raise RuntimeError('Refusing to replace an existing private credential file')
    from .dataset import populate
    credentials, manifest = await populate(db, settings.foundation_id)
    db.add(MutationReceipt(actor_id=f'stage-seed:{settings.foundation_id}', operation='stage.demo.seed', key=SEED_KEY, payload_hash=digest(SEED_KEY), result=manifest))
    await db.flush()
    credentials.update(seed_key=SEED_KEY, foundation_id=str(settings.foundation_id), manifest=manifest)
    written = write_new_private(credentials_path, credentials)
    try: await db.commit()
    except BaseException:
        written.unlink(missing_ok=True)
        raise
    return {'status':'seeded', 'private_file':str(written), 'synthetic_only':True}

async def login_token(db, credentials_path, email, challenge_id, output_path, confirmation):
    """Read a normal issued challenge. Never create a Session, verify or consume it."""
    settings = get_settings()
    validate_runtime(settings, confirmation)
    await database_guard(db, settings.foundation_id)
    credentials = read_credentials(credentials_path, settings.foundation_id)
    marker = await db.scalar(select(MutationReceipt).where(MutationReceipt.actor_id == f'stage-seed:{settings.foundation_id}', MutationReceipt.operation == 'stage.demo.seed', MutationReceipt.key == SEED_KEY))
    if not marker or marker.result != credentials.get('manifest'):
        raise RuntimeError('The private file does not match a committed synthetic seed')
    identities = {value['email']:value for value in marker.result['identities'].values()}
    if email not in identities or not email.endswith('@example.test'):
        raise RuntimeError('Only exact seeded fictional email addresses are allowed')
    expected_user = UUID(identities[email]['user_id'])
    actual = await db.scalar(select(User.id).join(ContactChannel, ContactChannel.user_id == User.id).where(User.id == expected_user, User.foundation_id == settings.foundation_id, User.account_state == 'active', ContactChannel.type == 'email', ContactChannel.normalized_value == email))
    if not actual: raise RuntimeError('The seeded fictional identity no longer owns this contact')
    challenge = await db.scalar(select(AuthChallenge).where(AuthChallenge.id == challenge_id, AuthChallenge.foundation_id == settings.foundation_id, AuthChallenge.normalized_contact == email, AuthChallenge.purpose == 'login', AuthChallenge.consumed_at.is_(None), AuthChallenge.expires_at > utcnow(), AuthChallenge.attempts < 5))
    if not challenge: raise RuntimeError('The ordinary challenge is missing, expired, consumed or belongs to another identity')
    rows = (await db.scalars(select(OutboxMessage).where(OutboxMessage.foundation_id == settings.foundation_id, OutboxMessage.channel == 'email').order_by(OutboxMessage.created_at.desc()).limit(100))).all()
    for row in rows:
        payload = json.loads(unseal(row.payload_cipher))
        if payload.get('to') == email and payload.get('purpose') == 'login' and payload.get('challenge_id') == str(challenge_id) and isinstance(payload.get('token'),str) and digest(payload['token']) == challenge.token_hash:
            target = write_new_private(output_path, {'email':email, 'challenge_id':str(challenge_id), 'token':payload['token'], 'expires_at':challenge.expires_at.isoformat()})
            return {'status':'private_code_file_ready', 'private_file':str(target), 'expires_at':challenge.expires_at.isoformat()}
    raise RuntimeError('No matching ordinary encrypted authentication outbox entry')
