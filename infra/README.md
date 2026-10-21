# Local and staging validation

These commands prepare a reviewable G1 candidate/coordinator environment. They do
not deploy to production. G2, G3 and P20 require their own domain implementations
and evidence; a green G1 does not complete the full implementation plan.

## Empty checkout with Docker

Install Node 26, pnpm 11.3, Python 3.12 and Docker Compose. From the repository root:

```sh
cp infra/.env.example infra/.env
# Replace the local password in infra/.env.
docker compose --env-file infra/.env -f infra/compose.yaml up --build -d
curl --fail http://127.0.0.1:8001/ready
```

Open http://127.0.0.1:8080. Set `OPORA_RELEASE` to the reviewed commit when
building a release; `/version.json` through the web origin forwards the API's
configured runtime release. PostgreSQL, API, web and optional dev inbox ports bind
loopback. The one-shot migration service must succeed before API/worker start.
Do not add fixtures to migrations. The default development inbox is a database
outbox sink; `dev_inbox` proves only local capture. Optional Mailpit can be started
with `--profile delivery-dev` for the local SMTP adapter. Mailpit does not configure
or prove email delivery by itself. AI/RTC/external delivery remain unavailable
until adapters and credentials are configured and tested.

`docker compose --env-file infra/.env -f infra/compose.yaml logs migrate api worker io-worker`
shows startup issues without HTTP payload/access logs. `down` preserves the
PostgreSQL and private-asset volumes. `down -v` destroys local data and is not part of validation.

The supplied workers use explicit bounded job lists. `worker` handles only
`outbox.deliver`; `io-worker` handles `studio.close`, `studio.revoke`,
`studio.reconcile_participant`, `knowledge.index`, `knowledge.ingest`,
`ai.generate` and `reporting.digest`. The opt-in media overlay handles
`slides.convert`, `recording.capture` and `followups.audio`. Its media tools and
acceptance gates are documented in [media-runtime.md](media-runtime.md).

Provider settings are passed from the same private environment to API and the
workers that need them: `OPORA_AI_BASE_URL/API_KEY/MODEL/TRANSCRIPTION_MODEL`,
`OPORA_AI_ENABLED`, the `OPORA_RTC_*` settings, and the shared
`OPORA_SECRET_KEY`. The API and media worker receive capture opt-in/origin;
only the media image has the executable Chrome path. SMTP settings are passed to
the outbox worker. Defaults keep AI/capture disabled, RTC unconfigured and email
in the explicit development inbox. Setting a URL alone is not provider
acceptance. Do not print expanded environment/configuration with credentials.
Telegram identity linking additionally passes `OPORA_TELEGRAM_LINK_ENABLED`,
`OPORA_TELEGRAM_BOT_USERNAME` and `OPORA_TELEGRAM_WEBHOOK_SECRET` to the API only.
It remains disabled with empty provider fields by default; this configuration
does not supply or enable an outbound Telegram delivery transport.

## Native PostgreSQL (Docker unavailable)

Create a dedicated disposable database using local PostgreSQL 16. No SQLite
fallback is accepted for concurrency, constraints or migration evidence.

```sh
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install -e 'apps/api[test]'
npm install --global pnpm@11.3.0
pnpm install --frozen-lockfile
export OPORA_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_test'
export OPORA_ACTIVITIES_PERF_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_activities_perf_test'
export OPORA_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_domain_test'
export OPORA_LEARNING_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_learning_test'
export OPORA_PARTICIPANTS_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_participants_test'
export OPORA_CANDIDATES_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_candidates_test'
export OPORA_CRM_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_crm_test'
export OPORA_KNOWLEDGE_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_knowledge_test'
export OPORA_STUDIO_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_studio_test'
export OPORA_PROFILE_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_profile_test'
export OPORA_SIMULATOR_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_simulator_test'
export OPORA_REPORTING_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_reporting_test'
export OPORA_ADMIN_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_admin_test'
export OPORA_DOBRO_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_dobro_test'
export OPORA_TELEGRAM_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_telegram_test'
# Only for a fresh local PostgreSQL instance, creates/migrates the fourteen dedicated fixture DBs:
python infra/scripts/prepare-test-dbs.py
export OPORA_ASSET_ROOT="${TMPDIR:-/tmp}/opora-private-test-assets"
export OPORA_ENVIRONMENT=development
export OPORA_TRUSTED_ORIGINS='["http://127.0.0.1:5174","http://localhost:5174"]'
sh infra/scripts/verify.sh
# In separate terminals, with the same database/environment:
(cd apps/api && uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log)
(cd apps/api && OPORA_WORKER_RUNTIME_DIR=/tmp/opora-outbox-runtime python -m app.worker.main)
pnpm dev
```

The command above starts only the outbox process. In another terminal with the
same private database, asset root and encryption/provider configuration, start
the bounded I/O process to consume domain jobs:

```sh
(cd apps/api && OPORA_WORKER_RUNTIME_DIR=/tmp/opora-io-runtime python -m app.worker.main --kind studio.close --kind studio.revoke --kind studio.reconcile_participant --kind knowledge.index --kind knowledge.ingest --kind ai.generate --kind reporting.digest)
```

Media jobs require the separate tested toolchain and opt-in configuration from
`infra/media-runtime.md`; their explicit native command is
`OPORA_WORKER_RUNTIME_DIR=/tmp/opora-media-runtime python -m app.worker.main --kind slides.convert --kind recording.capture --kind followups.audio`.
Do not add these kinds to either API-image worker or infer provider readiness
from a running process. Each process admits one job at a time.

The CLI creates invented fixture identities and staff grants. It is the only way
to bootstrap staff; no public role switch is allowed. Keep session-cookie fixture
JSON outside the checkout, mode 0600. Do not attach tokens, contact answers,
private notes or database dumps to CI artifacts. G1 HTTP/browser commands and
acceptance coverage are documented in `tests/e2e/README.md`.

## Staging release and rollback checklist

Before any staging rollout, record the commit SHA and clean working-tree state,
image identifiers, migration head and successful CI. Use a separate staging
PostgreSQL/database, encryption secret, private asset root, secure cookies,
exact HTTPS origins and `OPORA_DEV_INBOX=false`. Never reuse local demo sessions
or staging data in production. Runtime `/version.json` must equal the release SHA.

1. Back up staging PostgreSQL and private assets; restore to an isolated database
   and compare schema head plus representative row counts/attachment references.
2. Review the forward migration and previous-release compatibility. Test upgrade
   from the last release, rather than only from an empty database. Do not promise
   a schema downgrade when a data migration is irreversible.
3. Run migrations once, then start API/web/worker at that exact revision. Check
   readiness and runtime version, plus a real write/read/reload under two scoped
   identities. Check worker leases/retry and unavailable-provider reporting.
4. Run the independent G1 suite and inspect desktop/mobile browser artifacts.
   Record commands, environment, exact SHA, passed tests and unresolved gaps.
5. On failure, stop writes if schema compatibility is uncertain; restore the
   pre-rollout backup to an isolated database and verify it before redirecting
   staging. Restore assets consistently. Keep the failed database for analysis.

A successful image build or healthcheck does not prove deploy success. Production
release requires separate user authorization. No script here targets production.

For an isolated fresh G1 database, after `alembic upgrade head`,
`sh infra/scripts/run-g1.sh` seeds CLI-only credentials, starts a local API, runs
all independent HTTP tests and stops its API. It deletes only its temporary
credential file, never a database. Use a different database from backend unit
checks, since their MFA enrollment consumes the same fixture TOTP counter.
`OPORA_G1_FIXTURE_FILE` can point to the preserved initial seed output instead.
The runner defaults to port 8001; set `OPORA_G1_BASE_URL=http://127.0.0.1:8002`
for a separate QA port. Stop any previous API on the chosen port first.
It forwards quoted pytest arguments, for example `sh infra/scripts/run-g1.sh -k
'verified_login or csrf_origin'`. Backend fixture quota isolation never mutates
the HTTP G1 database; its ordinary server limits remain active across requests.

Domain test fixtures deliberately drop/recreate their model tables. Keep their
fourteen fixture URLs separate from development/staging and the external G1 database. Their
exact database names are asserted by the domain suites. The CI pytest plugin
rejects skipped checks; an unset URL is a gate failure, never a passing test run.
`prepare-test-dbs.py` refuses existing databases and never drops one.

For repeated integration checks on the specifically assigned QA cluster, the
explicit command below resets only the fifteen allowlisted disposable fixture schemas
and migrates them from empty. It fixes test-only `create_all`/Alembic stamp drift
after new models arrive. The script pins loopback port 56148, verifies the exact
QA data directory and database names, and cannot target proof/restore/G1 databases.
It is unnecessary in fresh CI and must not be used for development or staging data.

```sh
python infra/scripts/reset-qa-test-schemas.py --reset-disposable-test-schemas --api-source "$PWD/apps/api"
```

The dedicated opt-in media image, sandbox settings and acceptance commands are in
[media-runtime.md](media-runtime.md). Capture is disabled by default; Compose
syntax validation does not prove a container build or media acceptance.

## Separate board runtime gate

The board sidecar has its own Starlette/CRDT environment. Do not install its
requirements into the API virtualenv. The API pytest command excludes the sidecar
directory; CI runs the actual loopback WebSocket tests separately and rejects skips.

```sh
python3.12 -m venv /tmp/opora-board-venv
/tmp/opora-board-venv/bin/python -m pip install -r apps/api/app/integrations/rtc/sidecar/requirements.txt 'pytest==8.3.5' 'pytest-asyncio==0.26.0'
OPORA_SIDECAR_PYTHON=/tmp/opora-board-venv/bin/python sh infra/scripts/verify-sidecar.sh
```

Install the web workspace dependencies and use Node 26 before this gate.
These tests cover viewer/drawer authorization, persisted Yjs state after restart,
invalid grants and the installed JS y-websocket/Yjs client on loopback. They do not prove browser camera/microphone,
external media, deployment or strict revocation of an already issued LiveKit JWT.

## Isolated private-image restore drill (P20 subset)

With the assigned QA PostgreSQL running at loopback 56148 and data directory
`/private/tmp/opora-qa-pg-data`, run:

```sh
python infra/scripts/private-asset-restore.py --api-source "$PWD/apps/api"
```

The script refuses any other cluster. It creates fresh uniquely named source and
restore databases and fresh asset roots under
`/private/tmp/opora-qa-restore-assets/<run>/`. It never drops or restores over an
existing DB/directory, and never uses the default asset root. It freezes and hashes
API source, migrates/seeds, performs genuine staff HTTP login/MFA and image upload,
binds a participant photo, checks an unrelated principal, stops source writes,
snapshots DB/files, restores both, verifies content hashes and current access, then
revokes only the restored test membership and rechecks denial. Its two API
processes stop automatically. Dumps, encryption key and credentials remain private
outside Git; the summary report contains no auth tokens. Ports 8002/8003 must be
free. Supply `--pg-bin` if PostgreSQL tools are installed elsewhere.

A frozen working-tree source is labelled with commit plus tree hash. A final
immutable-release rerun remains required; this bounded drill does not complete
full P20 or deploy anything.

## Frozen-source build and graceful worker swap

Build from a committed revision rather than an editable checkout. The helper
archives that Git commit, hashes the archive, configures Compose against only the
archive, sets `OPORA_RELEASE` to the full SHA and labels built application images
with `org.opencontainers.image.revision`. It does not start/stop services or run
migrations. Keep its final JSON and the build's image digests with release evidence.

```sh
export OPORA_ENV_FILE=/absolute/private/path/opora-local.env
sh infra/scripts/build-frozen.sh HEAD --check-only
sh infra/scripts/build-frozen.sh HEAD
# Add --media only on an approved native amd64 Docker host.
```

`--check-only` proves archive/configuration preparation, not an image build.
The media helper refuses an ARM Docker daemon instead of enabling binfmt or
emulation. The existing [media build attempt](evidence/media-container-build-attempt-2026-10-21.md)
remains a failed amd64-on-ARM gate; supported-host build, sandboxed Chrome and real
synthetic capture acceptance are still required. After starting reviewed images,
compare `/version.json` through the web origin with the intended full SHA, inspect
actual image IDs/OCI labels and verify the live Alembic head against that source.
A release environment variable alone is not source proof.

Every worker now has a small stdlib heartbeat and an expiring admission gate,
adapted from OD's pinned `_media_drain.py` and `_worker_heartbeat.py`. The heartbeat
records only release, readiness, active/idle and gate identity. It becomes ready
after a successful database claim attempt, stays fresh during the current job and
becomes unready after database failure or shutdown. It proves the worker loop;
it does not prove SMTP, ASR, LiveKit, media tools, schema compatibility or delivery.
The API's `/ready` currently checks database/Alembic-table reachability only.

For a reviewed local/staging swap, request a gate separately in each existing
worker container. An operator-created UUID identifies this deployment; it is not
an authentication credential. Use the same private environment and Compose files
as that environment. This example targets the media lane; repeat for `worker` and
`io-worker` before a complete worker swap.

```sh
owner=$(python3 -c 'import uuid; print(uuid.uuid4())')
docker compose --env-file "$OPORA_ENV_FILE" -f infra/compose.yaml -f infra/compose.media.yaml --profile media exec -T media-worker python -m app.worker.runtime drain-start --owner "$owner"
# Repeat/renew the exact command at least every 30 seconds until its JSON says
# acknowledged:true and active:false. The owner gate expires after 90 seconds.
# Stop/replace only that acknowledged container within the renewed gate window.
# On abort, reopen claims with:
docker compose --env-file "$OPORA_ENV_FILE" -f infra/compose.yaml -f infra/compose.media.yaml --profile media exec -T media-worker python -m app.worker.runtime drain-stop --owner "$owner"
```

Never swap on a missing/stale acknowledgement. Only the main worker loop can
acknowledge, after its current transaction/handler returns; a heartbeat cannot
mistake a requested gate for completed work. Reopening an expired gate gets a new
generation, so an old idle marker cannot authorize a swap. SIGTERM/SIGINT stop new
claims and wait for the active job. Compose permits 3 minutes for I/O/outbox and
30 minutes for media, exceeding the registered 1600-second capture-handler timeout.
Do not shorten this with forced kills. Fencing and durable unknown-outcome handling
remain necessary for crashes and host loss; drain does not replace them.

Native workers must each receive a distinct `OPORA_WORKER_RUNTIME_DIR`, for example
`/tmp/opora-outbox-runtime`, `/tmp/opora-io-runtime` and `/tmp/opora-media-runtime`.
A second worker using an occupied directory fails startup rather than overwriting
another lane's heartbeat. Native control/health commands must use that same
lane-specific environment. Containers already isolate the default `/tmp` path.
