"""Seed development passwords matching the documentation."""
import asyncio
from sqlalchemy import select
from app.core.db import SessionLocal
from app.core.models import User, ContactChannel, Foundation
from app.core.config import get_settings
from app.core.clock import utcnow
from app.modules.auth.password import hash_password, kdf
from app.modules.auth.password_models import PasswordCredential
from app.modules.profile.models import VolunteerProfile

ACCOUNTS = [
    ("coordinator@example.test", "Marii-EV8UGC53XBcv", "Координатор"),
    ("volunteer1@example.test", "Marii-EuaK9kvAID6L", "Волонтёр Анна"),
    ("volunteer2@example.test", "Marii-7t9EivoFsWZ_", "Волонтёр Михаил"),
    ("volunteer3@example.test", "Marii-xuCYeY2h4CaB", "Волонтёр София"),
]

async def main():
    from app.core.model_loader import load_models
    load_models()
    settings = get_settings()
    async with SessionLocal() as db:
        foundation = await db.get(Foundation, settings.foundation_id)
        if not foundation:
            print("Ошибка: фонд не инициализирован.")
            return

        for email, password, name in ACCOUNTS:
            contact = await db.scalar(select(ContactChannel).where(ContactChannel.normalized_value == email))
            if contact:
                user = await db.get(User, contact.user_id)
            else:
                user = User(foundation_id=foundation.id, display_name=name)
                db.add(user)
                await db.flush()
                db.add(ContactChannel(user_id=user.id, normalized_value=email, verified_at=utcnow()))
                db.add(VolunteerProfile(user_id=user.id, foundation_id=foundation.id, lifecycle="active"))
                await db.flush()

            h = await kdf(hash_password, password)
            cred = await db.scalar(select(PasswordCredential).where(PasswordCredential.user_id == user.id))
            if cred:
                cred.password_hash = h
            else:
                db.add(PasswordCredential(user_id=user.id, password_hash=h, demo_created=True))

        await db.commit()
        print("Пароли для тестовых аккаунтов успешно установлены!")

if __name__ == "__main__":
    asyncio.run(main())
