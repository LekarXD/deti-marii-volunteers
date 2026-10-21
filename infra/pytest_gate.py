"""CI/backend gate: a missing PostgreSQL opt-in must never look green."""
from infra.pytest_no_skips import pytest_sessionfinish


def pytest_configure(config):
    # Destructive isolated fixtures must see the exact model set used by Alembic.
    # Otherwise a migrated late module's FK can outlive the incomplete drop_all.
    from app.core.model_loader import load_models
    load_models()
