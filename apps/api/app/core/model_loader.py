import importlib
from app.core import models

DOMAIN_MODULES = ("applications", "interviews", "activities", "participants", "learning")
def load_models():
    for module in DOMAIN_MODULES:
        name = f"app.modules.{module}.models"
        try:
            importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name not in (name, f"app.modules.{module}"):
                raise

async def claim_registration(db, registration_id, user_id):
    """Domain hooks claim only this proven registration; never match arbitrary contacts."""
    for module in DOMAIN_MODULES:
        name = f"app.modules.{module}.service"
        try:
            service = importlib.import_module(name)
        except ModuleNotFoundError as exc:
            if exc.name not in (name, f"app.modules.{module}"):
                raise
            continue
        hook = getattr(service, "claim_registration", None)
        if hook:
            await hook(db, registration_id, user_id)
