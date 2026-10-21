# New verified-user name initialization: independent focused gate

Immutable API source: **`0c6c63c6ea578a639c0da569e427b5799bcb68ec`**, including
the explicit new-user seam and owned-application initializer. Source came from
`git archive`, not the working tree. Its 323 API/schema/contract files retain
their original hashes after the checks; the sorted path/SHA256 manifest hash is
`3410879be78f8daf8815b7712921140c0715fff28d4574febd088160df021b55`.
No prototype or subsequent design source entered this gate.

## Actual PostgreSQL checks

**18 passed, zero skipped, 6.97 seconds**:

```text
apps/api/app/modules/applications/tests/       12 (including 6 new claim cases)
apps/api/tests/test_platform.py                4
apps/api/tests/test_contact_change.py          1
tests/contract/test_rate_limit_boundary.py     1
```

These cover the current submitted application belonging to the proven
registration, verification with a different email than the form, preserving
existing names (including a deliberate default), preserving manual profile
history, refusing an unproven initializer, and avoiding another registration's
application even when its form email matches. Existing auth/MFA, session
rotation, contact collision and real rate-budget checks also passed.

Only owned disposable main/candidate databases on loopback 56148 were used.
The main database remained at migration 19, **`6f4b9231d087` (head)**;
`alembic check` found no new upgrade operations. Its only warning was the existing
informational computed-tsvector comparison warning.

## Ordinary HTTP G1 subset

**6 passed, zero skipped, 20 deselected, 1.24 seconds** through the actual
`infra/scripts/run-g1.sh` lifecycle. QA created a new
`opora_qa_g1_identity_0c6` database after checking exact data directory
`/private/tmp/opora-qa-pg-data`, migrated it from empty, and used a separate asset
root plus API port 8002.

```sh
sh infra/scripts/run-g1.sh -k 'verified_login or csrf_origin or idempotency_payload or public_outcome or logout_revokes or development_delivery'
```

The strengthened verified-login journey deliberately confirms a different email
than the submitted form and reads the actual profile name. Only the current
registration initializes the new account. The original application UUID,
booking, learning progress and another registration's separate records remain
intact, while the old cookie is rejected. The other selected HTTP checks cover
CSRF/origin, optimistic versions, actor-bound idempotency, private/public outcome
fields, logout and truthful development-only delivery state.

QA fixed its pytest fixture boundary before this run: per-test rate-bucket
isolation now applies only to backend fixtures and never to `tests/e2e`. G1 keeps
the live server's real quota state and is not allowed through the disposable-main
DB mutation guard. The runner now safely forwards quoted pytest arguments for
focused selection. Neither change modifies auth runtime behavior.

Afterward API port 8002 was free, no generated G1 credential fixture remained,
and all archived source hashes still matched. The runner stopped only its own
API and removed only its own temporary credential file. No G1, proof, restored,
shared development or production DB was reset; the fresh G1 fixture DB is retained.

This is a focused API/HTTP gate, not a new broad backend aggregate, browser or
design acceptance, external-provider delivery or production result. All names,
contacts and records were synthetic; no external message was sent.
