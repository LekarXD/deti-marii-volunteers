# Expanded API aggregate after reporting, Staff, ASR and capture integration

Immutable API source: **`64f4f88603653b9aa9efb082e3aa78a6619b265b`**.
Result: **183 passed, zero skipped, 167.66 seconds**. QA harness: **`baf1694`**.
The separate board sidecar runtime was excluded, as in the earlier aggregate;
its independent protocol result is documented in the previous gate evidence.

The API, canonical Studio schemas and contracts were extracted by `git archive`
to `/private/tmp/opora-qa-snapshot-64f4f88`. The 309-file sorted path/SHA256
manifest hash is `b4144f437e4f6a481022b15816a67b7e11bba78e4b28c9564ef22daad2c4d16c`.
No dirty integration source was copied into the frozen API tree.

Before the successful run, the guarded reset script rebuilt only the eleven
allowlisted disposable fixture schemas on loopback 56148, after verifying exact
data directory `/private/tmp/opora-qa-pg-data`. Domain URLs were separate; the new
reporting URL was configured explicitly. No shared development, G1, proof,
restored-asset or production DB was reset. Final main migration was
**`84fc8b53ac5d` (head)**; `alembic check` reported no new upgrade operations.

With those owned database URLs and the API virtualenv exported:

```sh
python -m pytest -p infra.pytest_gate -c /private/tmp/opora-qa-snapshot-64f4f88/apps/api/pyproject.toml /private/tmp/opora-qa-snapshot-64f4f88/apps/api /private/tmp/opora-qa/tests/contract --ignore=/private/tmp/opora-qa-snapshot-64f4f88/apps/api/app/integrations/rtc/sidecar -q --tb=short -o cache_dir=/private/tmp/opora-qa-aggregate64-cache
```

The only test warnings were existing PyMuPDF SWIG deprecations. The subsequent
schema comparison emitted the existing informational computed-tsvector warning.

## First-run fixture failure and narrow repair

The first fresh-schema run of the same API source produced 179 passes and three
failures in 164.83 seconds. All three stopped before the target domain action at
ordinary coordinator login with `429 / rate_limited`: the expanded suite reused
the same fixture contact and ASGI client IP across independent tests, consuming
the real five-minute contact/IP quotas. Two recording tests and one worker test
were affected. This was fixture cross-contamination, not a confirmed recording or
worker runtime regression.

QA added function-scoped rate-bucket isolation to its own pytest plugin, guarded
to loopback and exact disposable main DB names `opora_test` / `opora_qa_test`.
It deletes only fixture rate buckets between tests. It does not alter the auth
implementation or disable limits within a test. An added actual PostgreSQL check
proves that request eleven still returns `429 / rate_limited`. The focused quota,
recording and worker checks passed 8/8 before the full fresh-schema rerun above.

## Proof boundaries

This aggregate exercises the actual API implementations and PostgreSQL, including
Staff/reporting ACL, export artifacts, ASR and capture job kernel tests. External
AI/transcription/email/RTC providers use controlled tests; no real provider
delivery, physical device or real participant was used. The result is not a new
ordinary HTTP G1 or browser acceptance run, a completed P20, a container rollout
or production proof.

The dedicated media build attempt is documented separately: the current ARM
Docker host cannot execute the pinned amd64 Chrome recipe. Native Stage MP4
proof belongs to A1's own evidence. The subsequent worker-manifest repair and
forthcoming shared-worker privacy fix require their own focused results rather
than being silently included in this immutable aggregate.
