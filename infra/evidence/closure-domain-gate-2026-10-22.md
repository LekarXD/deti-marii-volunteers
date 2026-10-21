# Isolated closure-domain gate — 2026-10-22

This is a focused continuation of the separate full **219 passed, zero skipped** gate at `a1deefe202b6208a9036ce9bb773437a0497418d`. It is not a fresh whole-suite result at the latest SHA. Counts below overlap and must not be added into a claimed aggregate.

## Immutable behavioral checkpoint

- Source: `0badab6c537221423cb365ccfa5d0b148ec87f64`, extracted with `git archive`, excluding working-tree edits.
- 402 files; manifest SHA256 `c9a287ce0d7900ecb81464401056d97e32610b97c42cf86a692042e3e3a6f0b9`.
- **61 passed, zero skipped, 30.95 seconds**.
- Covered recording review/capture/checkpoint/live and publication; worker extension behavior; all migration20 constraint cases; Dobro calculations/HTTP flows; Telegram binding; all eight operational-rule PostgreSQL cases; independent live-recording publication contract.
- The publication contract used its explicitly labeled synthetic completed-media fixture in this run. The separate actual-native-MP4 copy proof is documented in `live-recording-publication-bridge-2026-10-22.md`.

Command, with canonical QA test environment and the frozen root/API/tests on `PYTHONPATH`:

```sh
python -m pytest -p infra.pytest_gate -c apps/api/pyproject.toml \
  apps/api/tests/test_recordings.py apps/api/tests/test_recording_capture.py \
  apps/api/tests/test_recording_checkpoint.py apps/api/tests/test_recording_live.py \
  apps/api/tests/test_platform20_constraints.py apps/api/tests/test_worker_extensions.py \
  apps/api/tests/learning/test_recording_publication.py \
  apps/api/app/modules/dobro/tests \
  apps/api/app/modules/notifications/tests/test_telegram_binding.py \
  apps/api/app/modules/followups/test_rules.py \
  tests/contract/test_live_recording_publication.py -q --tb=short
```

The first independent schema-drift check detected three Dobro composite user/foundation foreign keys missing from ORM metadata. The subsequent final checkpoint includes their metadata alignment; database constraints were retained.

## Final migration21 and changed-runtime checkpoint

- Source: `66b4dd5f5a30bf2d2afdec58d549e3d78e7d694c`, again archived from the commit.
- 405 files; manifest SHA256 `773d00325fb128f37ed332538499a7f3a647d5b72781b3b174b0317fd922e2b1`.
- **25 passed, zero skipped, 4.97 seconds**: seven actual PostgreSQL migration constraint cases, sixteen Dobro tests including reminder delivery/current-grant suppression and unused-link edits, and two runtime-manifest contracts.
- Command: same pytest gate/config, paths `apps/api/tests/test_platform20_constraints.py apps/api/app/modules/dobro/tests tests/contract/test_worker_manifest.py`.
- Main disposable QA DB: upgrade20→21, then **21→20→21** succeeded.
- Exact dedicated Dobro fixture DB: empty schema→21 succeeded.
- `alembic current`: `c72a9064de18 (head)` on both.
- `alembic check`: **No new upgrade operations detected** on both. Only the existing informational warning about the computed knowledge search document remained.

The earlier destructive Dobro fixture recreated ORM tables while leaving Alembic's20 stamp, so its first in-place21 upgrade lacked the old immutable trigger. This was fixture drift: only the exact disposable Dobro schema was reset, then migrated from empty. The real migrated main fixture's20→21 and reverse/reapply succeeded. No migration was weakened.

## Runtime wiring and notice imports

The clean-process job contract compares all literal `register_handler` declarations in production API source with the actually loaded registry, then checks disjoint explicit Compose/Docker owners and workload type. All twelve handlers are covered: `ai.generate`, `dobro.reminders.scan`, `followups.audio`, `followups.rules`, `knowledge.index`, `knowledge.ingest`, `recording.capture`, `reporting.digest`, `slides.convert`, `studio.close`, `studio.reconcile_participant`, `studio.revoke`. `outbox.deliver` has its separate owner.

An additional QA contract executes the ordinary lazy notice-source entry point in a fresh process, without importing domain resolvers from tests. **1 passed, zero skipped, 0.69 seconds** against the final frozen API plus the added contract. All three declared sources load: `dobro_reminder`, `report_digest`, `webinar_summary`.

## Isolation and proof limits

All database operations used only `127.0.0.1:56148`, checked against `/private/tmp/opora-qa-pg-data`, and exact disposable fixture names. New dedicated DBs are `opora_dobro_test` and `opora_telegram_test`; operational rules use the existing isolated Staff fixture. No proof/restore/G1/production database, external provider, outbound message, physical device, or foreign agent cluster was used. All source hashes were rechecked unchanged after each frozen run.

CI/provision/verification now explicitly require the two new fixture URLs. The guarded QA reset allowlist has fifteen exact disposable schemas. Telegram identity settings reach only the API, with linking disabled and provider fields empty by default. Compose parsing, Python compilation and patch whitespace checks passed.

This gate does not establish a production deployment, container sandbox acceptance on a native amd64 host, twenty-minute capture capacity, or a new whole-suite result at66b4dd5. The prior actual native capture and copied-byte publication proofs retain their separately documented boundaries.
