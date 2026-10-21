# Expanded API/contract and current-source G1 checkpoint

## Immutable expanded aggregate

Source checkpoint: **`c6e35434188d46cdd19d8f7a351d183909483f0f`**.
Result: **140 passed, zero skipped, 121.79 seconds**.

The first run at `29f5048fc6e0d730e2afffee2a371ad8a58b04e7` produced 139 passes and
one failure: the new contact-change test called session bootstrap before seeding
the foundation. Its unchanged focused rerun passed after later tests seeded it.
Owner fix `17332202d8e1b2b0ada944f84a69d15665b4df9a` adds explicit fixture setup;
it changes no runtime behavior. The fresh-schema complete rerun included that fix.

The running frozen tree was compared byte-for-byte with a Git archive of
`c6e3543`: all 264 source files in `apps/api`, `packages/contracts` and
`packages/studio-core` matched. The path/hash manifest SHA256 is
`ebe3d9777fac36571830e689f12a998719e938ac4e3a7505eda74dc2d33ba1e3`.
Only generated pytest caches were excluded from that comparison.

Before the successful run, the explicit `reset-qa-test-schemas.py` guard rebuilt
only its ten allowlisted disposable fixture schemas on loopback 56148, after
checking `/private/tmp/opora-qa-pg-data`. Every schema migrated from empty. No G1,
backup, restored-asset, proof or active integrator database was reset. Final core
migration: **`c74a006971d4` (head)**; `alembic check`: **no new upgrade operations**.
The only warnings were PyMuPDF SWIG deprecations and Alembic's informational
computed-tsvector comparison warning.

The command selected all `apps/api` paths and the independent `tests/contract`
suite with `-p infra.pytest_gate`, excluding only the separate board sidecar
runtime. All nine domain opt-in URLs were set to dedicated own-cluster databases.
No runtime implementation was edited by QA. With the documented dedicated DB
URLs exported, the aggregate command was:

```sh
python -m pytest -p infra.pytest_gate -c /private/tmp/opora-qa-snapshot-29f5048/apps/api/pyproject.toml /private/tmp/opora-qa-snapshot-29f5048/apps/api /private/tmp/opora-qa/tests/contract --ignore=/private/tmp/opora-qa-snapshot-29f5048/apps/api/app/integrations/rtc/sidecar -q --tb=short -o cache_dir=/private/tmp/opora-qa-final-pytest-cache
```

The historical snapshot directory name is retained; its tracked contents matched
`c6e3543` as verified above.

## Ordinary HTTP G1

Runtime source/release: **`29f5048fc6e0d730e2afffee2a371ad8a58b04e7`**; the subsequent
`c6e3543` checkpoint changes only the contact test setup described above.
Result: **26 passed, zero skipped, 4.89 seconds** through the actual
`infra/scripts/run-g1.sh` lifecycle, fresh `opora_qa_g1_29f5048` database on the
owned cluster, isolated asset root and API port 8002.

The updated journey submits current form v5 with valid `specialExp: Нет`, keeps
consent document version 4, books before learning, reads the four current modules
and validates their source revision/hash, cards/feed/cards/feed modes and 4/4/3/5
published blocks. It submits ten questions, rejects client score injection,
checks server score 4/10, current-source repeat denial (`409 /
repeat_not_available`), and preserves the prior result across application edits.
Legacy source repeat/history remains covered separately in the expanded API suite.
The ordinary coordinator queue/review/answer, private fields, session claim,
CSRF/origin, races, idempotency, fresh grant/member revoke and old receipts also
passed. The temporary API stopped and its temporary secret fixture was removed.

## Packaging maintenance and remaining gates

New Studio schemas and web asset preparation introduced source dependencies absent
from earlier Docker COPY rules. API now includes `packages/studio-core`; web
includes `apps/web/scripts`, `packages/design-tokens` and `packages/studio-core`.
The private-asset restore runner now freezes/hashes the canonical schemas with API
source. Compose syntax validates; these packaging edits do not constitute a
container build/runtime or a new restore-drill run.

The separate board gate was already verified: three real loopback WebSocket tests
plus actual installed JS Yjs/y-websocket host sync and denied viewer updates.
It was not needlessly repeated for this API-only checkpoint. Browser acceptance
belongs to the integrator's CUA evidence. No browser consent operation, external
AI/email/media provider, physical device, production service, Docker context,
deployment or actual MP4 capture was used or claimed. These results do not complete
full P20 or the next reporting/renderer phase.
