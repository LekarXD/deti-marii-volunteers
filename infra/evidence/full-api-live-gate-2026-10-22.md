# Full API regression with live recording binding

Immutable source: **`a1deefe202b6208a9036ce9bb773437a0497418d`**.
Result: **219 passed, zero skipped, 162.12 seconds**. No runtime fix or failed
test occurred in this run. The only warnings were five existing PyMuPDF SWIG
deprecations.

The source was extracted with `git archive` into
`/private/tmp/opora-qa-snapshot-a1deefe`, including API, canonical Studio schemas,
contracts, infra and independent contract tests. The 374-file sorted path/SHA256
manifest hash is `e012442bb72cf033e3118654113303fb6869598e570c4be4ca6bb69802df73ca`.
Dirty integration frontend/SDK files were not copied into the frozen source.

Before the run, QA's explicit reset guard rebuilt only its thirteen allowlisted
disposable fixture schemas on PostgreSQL loopback 56148, after checking exact data
directory `/private/tmp/opora-qa-pg-data`. All domain opt-ins were configured,
including the dedicated calendar-performance DB on this same owned cluster. The
portable perf guard accepts its explicit valid port; it no longer requires the
other agent's 56147 instance. G1, proof, restored assets, shared development and
production DBs were excluded from every reset.

After the run, migration 19 remained **`6f4b9231d087` (head)**;
`alembic check` found no new upgrade operations (the existing informational
computed-tsvector warning only). All 374 archived source files retained their
original SHA256 hashes.

```sh
python -m pytest -p infra.pytest_gate -c apps/api/pyproject.toml apps/api tests/contract --ignore=apps/api/app/integrations/rtc/sidecar -q --tb=short -o cache_dir=/private/tmp/opora-qa-final3-cache
```

This includes all API domain tests present at that immutable checkpoint: current
live binding and solo-room guard, capture/publication, real auth/owned registration
claim, Staff/reporting/admin, calendar bulk/performance and worker drain/resume/
shutdown. The independent live publication bridge performs real session/MFA API
verification and tests exact recording review plus separate lesson review, prior
primary retention, one publication ledger row and fresh permission denial. Its
completed-media fixture is explicitly labeled; actual native live bytes were
separately imported and tested as documented in
`live-recording-publication-bridge-2026-10-22.md`.

The separate board sidecar runtime remains excluded because it has its own
dependency/protocol gate. This API run does not claim native media duration,
20-minute capacity, Docker container acceptance, staging or production rollout.
External providers are controlled fixtures; no real participant/device or outbound
provider message was used. Native capture and copied-byte publication are separate
proofs, not a claim that this pytest process performed capture.

Later durability, Telegram binding, Dobro manual transfer and Signal settings
changes are outside this source checkpoint and receive their own focused gates.
