"""Local setup and encrypted development inbox. Never exposed by HTTP."""
import argparse
import asyncio
import json
from uuid import uuid4
import pyotp
from sqlalchemy import select
from app.core.clock import utcnow
from app.core.config import get_settings
from app.core.crypto import seal, unseal
from app.core.db import SessionLocal
from app.core.model_loader import load_models
from app.core.models import Foundation, User, ContactChannel, StaffMembership, PermissionGrant, MfaFactor, OutboxMessage

PERMISSIONS = ("staff.manage", "assets.manage", "candidates.read", "candidates.review", "candidates.notes", "interviews.manage", "interviews.read", "roles.manage", "opportunities.manage", "events.manage", "assignments.manage", "participants.read", "participants.write", "participants.private_notes", "groups.read", "groups.write", "learning.manage", "reports.read")

async def fixtures():
    if get_settings().environment != "development":
        raise RuntimeError("Fixture seed is development only")
    load_models()
    async with SessionLocal() as db:
        foundation = await db.get(Foundation, get_settings().foundation_id)
        if foundation is None:
            foundation = Foundation(id=get_settings().foundation_id, name="Опора — учебный фонд")
            db.add(foundation)
            await db.flush()
        identities = {}
        for name,email,staff in (("Координатор Тестовый", "coordinator@example.test", True),("Кандидат Первый", "candidate-one@example.test", False),("Кандидат Второй", "candidate-two@example.test", False)):
            contact = await db.scalar(select(ContactChannel).where(ContactChannel.normalized_value == email))
            if contact:
                user = await db.get(User, contact.user_id)
            else:
                user = User(foundation_id=foundation.id, display_name=name)
                db.add(user)
                await db.flush()
                db.add(ContactChannel(user_id=user.id, normalized_value=email, verified_at=utcnow()))
            identities[email] = {"user_id": str(user.id), "email": email}
            if staff:
                membership = await db.scalar(select(StaffMembership).where(StaffMembership.user_id == user.id))
                if membership is None:
                    membership = StaffMembership(user_id=user.id, foundation_id=foundation.id)
                    db.add(membership)
                    await db.flush()
                    db.add_all([PermissionGrant(membership_id=membership.id, permission=p) for p in PERMISSIONS])
                factor = await db.scalar(select(MfaFactor).where(MfaFactor.user_id == user.id))
                if factor is None:
                    secret = pyotp.random_base32()
                    db.add(MfaFactor(user_id=user.id, secret_cipher=seal(secret), confirmed_at=utcnow()))
                    identities[email]["totp_secret"] = secret
                    identities[email]["secret_notice"] = "One-time fixture bootstrap secret; store locally. Never commit."
        try:
            from app.modules.learning.seed import seed_introduction
            await seed_introduction(db, foundation.id)
        except ModuleNotFoundError as exc:
            if exc.name not in ("app.modules.learning", "app.modules.learning.seed"):
                raise
        await db.commit()
        return {"foundation_id": str(foundation.id), "identities": identities, "delivery": "development inbox; no external messages sent"}

async def inbox(email):
    if get_settings().environment != "development" or not get_settings().dev_inbox:
        raise RuntimeError("Development inbox disabled")
    async with SessionLocal() as db:
        rows = (await db.scalars(select(OutboxMessage).order_by(OutboxMessage.created_at.desc()).limit(100))).all()
        result = []
        for row in rows:
            payload = json.loads(unseal(row.payload_cipher))
            if email is None or payload.get("to") == email:
                result.append({"id": str(row.id), "state": row.state, **payload})
        return result

def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    seed = commands.add_parser("fixtures")
    seed.add_argument("name", choices=["g1"])
    seed.add_argument("--json", action="store_true")
    dev = commands.add_parser("dev-inbox")
    dev.add_argument("--email")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(fixtures() if args.command == "fixtures" else inbox(args.email)), ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
