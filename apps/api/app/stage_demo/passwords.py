"""Add passwords to four exact synthetic stage identities, without changing MFA."""
import argparse
import asyncio
import json
import secrets
import stat
from pathlib import Path
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.crypto import digest
from app.core.model_loader import load_models
from app.core.models import ContactChannel, MutationReceipt, User
from app.modules.auth.password import hash_password, kdf, staff, verify_password
from app.modules.auth.password_models import PasswordCredential
from .operator import (CONFIRMATION, SEED_KEY, database_guard, private_directory,
                       read_credentials, validate_runtime, write_new_private)

KEY = 'stage-password-demo-v1'
ROLES = ('coordinator', 'volunteer', 'candidate', 'polina')


async def provision(db, source_path, output_path):
    settings = get_settings()
    validate_runtime(settings, CONFIRMATION)
    if not settings.demo_email_codes:
        raise RuntimeError('Explicit demo-email mode required')
    await database_guard(db, settings.foundation_id)
    source = read_credentials(source_path, settings.foundation_id)
    marker = await db.scalar(select(MutationReceipt).where(
        MutationReceipt.actor_id == f'stage-seed:{settings.foundation_id}',
        MutationReceipt.operation == 'stage.demo.seed', MutationReceipt.key == SEED_KEY))
    if not marker or marker.result != source.get('manifest'):
        raise RuntimeError('Original synthetic seed marker required')
    await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'), {'key': KEY})
    output = Path(output_path).absolute()
    private_directory(output)
    done = await db.scalar(select(MutationReceipt).where(
        MutationReceipt.actor_id == KEY, MutationReceipt.operation == KEY, MutationReceipt.key == KEY))
    if done:
        if output.is_symlink() or stat.S_IMODE(output.stat().st_mode) != 0o600:
            raise RuntimeError('Original private password file required')
        saved = json.loads(output.read_text())
        if saved.get('key') != KEY or saved.get('foundation_id') != str(settings.foundation_id) or saved.get('manifest') != done.result:
            raise RuntimeError('Password file does not match the committed marker')
        for account in saved['accounts'].values():
            credential = await db.scalar(select(PasswordCredential).where(PasswordCredential.user_id == UUID(account['user_id'])))
            if not credential or not await kdf(verify_password, account['password'], credential.password_hash):
                raise RuntimeError('Password changed; refusing to overwrite it')
        return {'status': 'already_provisioned', 'accounts': 4, 'private_file': str(output)}
    if output.exists():
        raise RuntimeError('Refusing to replace a private password file')
    accounts, manifest = {}, {}
    for role in ROLES:
        identity = source['manifest']['identities'][role]
        user_id, email = UUID(identity['user_id']), identity['email']
        user = await db.get(User, user_id)
        contact = await db.scalar(select(ContactChannel).where(ContactChannel.user_id == user_id,
            ContactChannel.type == 'email', ContactChannel.normalized_value == email))
        if not user or user.foundation_id != settings.foundation_id or user.account_state != 'active' or not email.endswith('@example.test') or not contact or not contact.verified_at:
            raise RuntimeError('Exact verified synthetic identity required')
        if await db.scalar(select(PasswordCredential).where(PasswordCredential.user_id == user_id)):
            raise RuntimeError('Refusing to replace an existing password')
        password = 'Marii-' + secrets.token_urlsafe(12)
        # Staff passwords are never demo-resettable (no "any code" reset of the coordinator).
        db.add(PasswordCredential(user_id=user_id, password_hash=await kdf(hash_password, password), demo_created=not await staff(db, user_id)))
        accounts[role] = {'user_id': str(user_id), 'name': user.display_name, 'email': email, 'password': password}
        manifest[role] = {'user_id': str(user_id), 'email': email}
    db.add(MutationReceipt(actor_id=KEY, operation=KEY, key=KEY, payload_hash=digest(KEY), result=manifest))
    await db.flush()
    written = write_new_private(output, {'key': KEY, 'foundation_id': str(settings.foundation_id),
        'manifest': manifest, 'accounts': accounts})
    try:
        await db.commit()
    except BaseException:
        written.unlink(missing_ok=True)
        raise
    return {'status': 'provisioned', 'accounts': 4, 'private_file': str(written)}


async def run(args):
    load_models()
    engine = create_async_engine(get_settings().database_url, hide_parameters=True)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await provision(db, args.credentials_path, args.output_path)
    finally:
        await engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--credentials-path', required=True)
    parser.add_argument('--output-path', required=True)
    print(json.dumps(asyncio.run(run(parser.parse_args()))))
