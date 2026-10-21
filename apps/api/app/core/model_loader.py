import importlib
from app.core import models

DOMAIN_MODULES = ("applications", "interviews", "activities", "participants", "learning", "messaging", "crm", "studio", "notifications", "knowledge", "followups", "simulator", "profile", "recordings", "staff", "reporting", "dobro")
def load_models():
    importlib.import_module("app.integrations.ai.models")
    for module in DOMAIN_MODULES:
        name = f"app.modules.{module}.models"
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name not in (name, f"app.modules.{module}"):
                raise

async def claim_registration(db, registration_id, user_id, *, newly_created_user=False):
    """Claim only this proven registration; opt-in initialization is new-user-only."""
    from sqlalchemy import update
    from app.core.models import MediaAsset
    await db.execute(update(MediaAsset).where(MediaAsset.owner_registration_id==registration_id).values(owner_user_id=user_id,owner_registration_id=None))
    for module in DOMAIN_MODULES:
        name = f"app.modules.{module}.service"
        try:
            service = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name not in (name, f"app.modules.{module}"):
                raise
            continue
        if newly_created_user:
            initialize = getattr(service, "initialize_registration_user", None)
            if initialize:
                await initialize(db, registration_id, user_id)
        hook = getattr(service, "claim_registration", None)
        if hook:
            await hook(db, registration_id, user_id)
