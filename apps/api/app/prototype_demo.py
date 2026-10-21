"""Four private manual-test accounts for the isolated welcome-screen prototype."""
import argparse
import asyncio
import json
import secrets
import stat
from pathlib import Path

import pyotp
from sqlalchemy import func, select, text

from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.crypto import digest, seal
from app.core.db import SessionLocal
from app.core.model_loader import load_models
from app.core.models import (ContactChannel, Foundation, MfaFactor, MfaRecovery,
                             MutationReceipt, PermissionGrant, StaffMembership, User)

KEY = 'welcome-prototype-accounts-v1'
NAME = 'Дети Марии — демонстрация входа'
PEOPLE = (
    ('coordinator', 'Координатор Демонстрационный', 'coordinator@example.test'),
    ('volunteer1', 'Анна Демонстрационная', 'volunteer1@example.test'),
    ('volunteer2', 'Михаил Демонстрационный', 'volunteer2@example.test'),
    ('volunteer3', 'София Демонстрационная', 'volunteer3@example.test'),
)


def guard():
    settings = get_settings()
    if settings.environment != 'development' or not settings.demo_email_codes:
        raise RuntimeError('Use the explicit local prototype email-code mode')
    return settings


def read_private(path):
    path = Path(path)
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise RuntimeError('Use the original private mode0600 credential file')
    data = json.loads(path.read_text())
    if data.get('seed_key') != KEY:
        raise RuntimeError('Not a welcome-screen prototype credential file')
    return data


async def seed(path):
    settings = guard()
    load_models()
    from app.cli import PERMISSIONS
    from app.modules.auth.password import hash_password, kdf
    from app.modules.auth.password_models import PasswordCredential
    from app.modules.profile.models import VolunteerProfile
    from app.stage_demo.operator import write_new_private
    output = Path(path).absolute()
    async with SessionLocal() as db:
        if await db.scalar(text('SELECT current_database()')) != 'opora_welcome_demo':
            raise RuntimeError('Only the isolated opora_welcome_demo database is allowed')
        await db.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:key,0))'), {'key': KEY})
        marker = await db.scalar(select(MutationReceipt).where(
            MutationReceipt.actor_id == KEY, MutationReceipt.operation == KEY, MutationReceipt.key == KEY))
        if marker:
            data = read_private(output)
            if data.get('foundation_id') != str(settings.foundation_id) or data.get('manifest') != marker.result:
                raise RuntimeError('Credential file and prototype seed marker differ')
            return {'status': 'already_seeded', 'credentials_path': str(output), 'accounts': 4}
        if output.exists() or await db.scalar(select(func.count()).select_from(User)):
            raise RuntimeError('First seed needs an empty prototype account database and a new private output file')
        foundations = (await db.scalars(select(Foundation))).all()
        if any(row.id != settings.foundation_id or row.name != NAME for row in foundations):
            raise RuntimeError('Refusing a different foundation')
        if not foundations:
            db.add(Foundation(id=settings.foundation_id, name=NAME))
            await db.flush()
        manifest, accounts = {}, {}
        for role, name, email in PEOPLE:
            password = 'Marii-' + secrets.token_urlsafe(9)
            user = User(foundation_id=settings.foundation_id, display_name=name)
            db.add(user)
            await db.flush()
            db.add(ContactChannel(user_id=user.id, normalized_value=email, verified_at=utcnow()))
            db.add(PasswordCredential(user_id=user.id, password_hash=await kdf(hash_password, password), demo_created=True))
            db.add(VolunteerProfile(user_id=user.id, foundation_id=settings.foundation_id))
            accounts[role] = {'name': name, 'email': email, 'password': password}
            manifest[role] = {'user_id': str(user.id), 'email': email}
            if role == 'coordinator':
                member = StaffMembership(foundation_id=settings.foundation_id, user_id=user.id)
                db.add(member)
                await db.flush()
                db.add_all(PermissionGrant(membership_id=member.id, permission=value) for value in PERMISSIONS)
                secret = pyotp.random_base32()
                db.add(MfaFactor(user_id=user.id, secret_cipher=seal(secret), confirmed_at=utcnow()))
                recovery = [secrets.token_hex(8) for _ in range(8)]
                db.add_all(MfaRecovery(user_id=user.id, code_hash=digest(code)) for code in recovery)
                accounts[role].update(totp_secret=secret, recovery_codes=recovery)
        data = {'seed_key': KEY, 'foundation_id': str(settings.foundation_id),
                'manifest': manifest, 'accounts': accounts, 'synthetic_only': True}
        db.add(MutationReceipt(actor_id=KEY, operation=KEY, key=KEY,
                               payload_hash=digest(KEY), result=manifest))
        await db.flush()
        written = write_new_private(output, data)
        try:
            await db.commit()
        except BaseException:
            written.unlink(missing_ok=True)
            raise
    return {'status': 'seeded', 'credentials_path': str(output), 'accounts': 4}


def current_code(path):
    settings = guard()
    data = read_private(path)
    if data.get('foundation_id') != str(settings.foundation_id):
        raise RuntimeError('Different prototype foundation')
    return {'code': pyotp.TOTP(data['accounts']['coordinator']['totp_secret']).now(),
            'valid_for_seconds': 30 - int(utcnow().timestamp()) % 30}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('seed', 'code'))
    parser.add_argument('--credentials-path', required=True)
    args = parser.parse_args()
    result = asyncio.run(seed(args.credentials_path)) if args.command == 'seed' else current_code(args.credentials_path)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
