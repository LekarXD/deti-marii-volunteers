"""The QA fixture isolates test cases without bypassing actual auth budgets."""
from uuid import uuid4

import pytest

from app.core.db import SessionLocal
from app.core.errors import ApiError
from app.core.rate_limit import rate_limit


@pytest.mark.asyncio
async def test_actual_rate_budget_remains_enforced_within_one_test():
    async with SessionLocal() as db:
        identity = 'independent-synthetic-' + uuid4().hex
        for _ in range(10):
            await rate_limit(db, identity, 'challenge_contact')
        with pytest.raises(ApiError) as denied:
            await rate_limit(db, identity, 'challenge_contact')
        assert denied.value.status_code == 429 and denied.value.code == 'rate_limited'
        await db.rollback()
