# Focused follow-up gates after the 183-test aggregate

The immutable aggregate remains `64f4f88603653b9aa9efb082e3aa78a6619b265b`;
these subsequent results cover their explicit newer source checkpoints. No broad
aggregate rerun is silently implied.

## Capture, worker, publication, digests and webinar summary

Source: **`c5f4b92c6b57ef5af9cb9b46d37567631eca1f1f`**.
Result: **32 passed, zero skipped, 80.52 seconds**.
The Git-archive snapshot contains 316 API/schema/contract files; its sorted
path/SHA256 manifest hash is
`ce940a2a68c7de4360cc23149df3623473cd77ad70c9305b7e464316e2488838`.

On the owned loopback PostgreSQL 56148, the main disposable DB upgraded to
migration 19, **`6f4b9231d087` (head)**. `alembic check` found no new upgrade
operations; only the existing informational computed-tsvector warning appeared.
The focused paths were:

```text
apps/api/tests/test_recordings.py
apps/api/tests/test_recording_capture.py
apps/api/tests/test_worker_extensions.py
apps/api/tests/learning/test_recording_publication.py
apps/api/app/modules/reporting/tests/test_digests.py
apps/api/app/modules/studio/tests/test_summary.py
tests/contract/test_worker_manifest.py
```

They cover the updated capture/worker fences and API admission versus worker
executable validation, exact reviewed recording publication, terminal digest
suppression, and reviewed/published summary with the real P17 internal dispatcher.
The summary path checks actual persisted messages plus current enrollment,
sender grant/session revoke, no-contact/quiet policy, audience refresh and
supersession. Bounded source review found no additional concrete summary defect.

The separate manifest test loads the real job registry in a clean subprocess and
checks every registered kind has exactly one declared owner: seven I/O kinds,
three media kinds, plus the existing outbox kind. It verifies workload isolation
and required provider settings while defaults remain disabled/unconfigured.
Compose syntax also passes. This establishes manifest coverage, not a running
container or configured external-provider acceptance.

## Read-only administration audit API

Source: **`35ccedf2718e5f2903b0edbf0e5f23f501f883ba`**.
Result: **6 passed, zero skipped, 6.83 seconds** in
`apps/api/app/modules/admin/tests/test_audit.py`.
Its archive contains 322 API/schema/contract files; the sorted path/SHA256
manifest hash is `58d31d60065700f607bdb4a43f59e7fc7115589c96589511cf1c4630ca07ac14`.

QA created only `opora_admin_test` on the verified owned cluster and migrated it
from empty before the tests. The suite checks foreign-foundation denial, safe
metadata projection, current foundation management/MFA requirements, ordinary,
revoked and group-only denial, and stable equal-timestamp cursor pagination bound
to its filters/snapshot. No write endpoint or new migration was introduced by
this API.

`OPORA_ADMIN_TEST_DATABASE_URL` is now explicit in CI and native setup; fresh
provisioning and the owned reset allowlist include `opora_admin_test`. There are
eleven separate domain databases plus the main disposable DB. The skip-rejecting
gate therefore cannot silently omit this new suite for missing configuration.

## Shared proof boundaries

All DB operations used the assigned synthetic QA cluster, never shared development,
G1, proof, restore or production databases. External providers are controlled test
adapters; no real messages, physical camera/microphone or real participants were
used. Native Stage MP4/privacy evidence belongs to A1. The separate amd64
container host-execution gap remains open and was not worked around.
