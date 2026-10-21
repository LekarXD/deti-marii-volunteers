"""CI/backend gate: a missing PostgreSQL opt-in must never look green."""
import os

import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.engine import make_url

from infra.pytest_no_skips import pytest_sessionfinish


def pytest_configure(config):
    # Destructive isolated fixtures must see the exact model set used by Alembic.
    # Otherwise a migrated late module's FK can outlive the incomplete drop_all.
    from app.core.model_loader import load_models
    load_models()


@pytest_asyncio.fixture(autouse=True)
async def isolate_main_fixture_rate_buckets(request):
    """Independent tests must not consume each other's reused fixture login budget.

    Production limits remain active inside every test. Only the disposable main
    test DB is touched; the explicit name/loopback guard excludes development,
    proof, restore and G1 DBs. Domain fixtures retain their separate DBs/schemas.
    """
    # Ordinary HTTP acceptance owns a separate G1 DB and its live server state.
    # It must exercise the real quotas without backend fixture mutations.
    directory = request.node.path.parent
    if directory.name == 'e2e' and directory.parent.name == 'tests':
        return
    url = make_url(os.environ['OPORA_DATABASE_URL'])
    if url.host not in {'127.0.0.1', 'localhost', '::1'} or url.database not in {
        'opora_test', 'opora_qa_test',
    }:
        raise RuntimeError('QA rate-bucket isolation requires the exact disposable main test database')
    from app.core.db import SessionLocal
    from app.core.models import RateLimitBucket
    async with SessionLocal() as db:
        await db.execute(delete(RateLimitBucket))
        await db.commit()
