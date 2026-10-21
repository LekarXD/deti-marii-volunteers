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
with `--profile delivery-dev` for a later SMTP adapter. Mailpit does not configure
or prove email delivery by itself. AI/RTC/external delivery remain unavailable
until adapters and credentials are configured and tested.

`docker compose --env-file infra/.env -f infra/compose.yaml logs migrate api worker`
shows startup issues without HTTP payload/access logs. `down` preserves the
PostgreSQL and private-asset volumes. `down -v` destroys local data and is not part of validation.

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
export OPORA_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_domain_test'
export OPORA_LEARNING_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_learning_test'
export OPORA_PARTICIPANTS_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_participants_test'
export OPORA_CANDIDATES_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_candidates_test'
export OPORA_CRM_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_crm_test'
export OPORA_KNOWLEDGE_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_knowledge_test'
export OPORA_STUDIO_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_studio_test'
export OPORA_PROFILE_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_profile_test'
export OPORA_SIMULATOR_TEST_DATABASE_URL='postgresql+psycopg://opora:local-password@127.0.0.1:55647/opora_simulator_test'
# Only for a fresh local PostgreSQL instance, creates/migrates the nine domain DBs:
python infra/scripts/prepare-test-dbs.py
export OPORA_ASSET_ROOT="${TMPDIR:-/tmp}/opora-private-test-assets"
export OPORA_ENVIRONMENT=development
export OPORA_TRUSTED_ORIGINS='["http://127.0.0.1:5174","http://localhost:5174"]'
sh infra/scripts/verify.sh
# In separate terminals, with the same database/environment:
(cd apps/api && uvicorn app.main:app --host 127.0.0.1 --port 8001 --no-access-log)
(cd apps/api && python -m app.worker.main)
pnpm dev
```

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

Domain test fixtures deliberately drop/recreate their model tables. Keep their
nine domain URLs separate from development/staging and the external G1 database. Their
exact database names are asserted by the domain suites. The CI pytest plugin
rejects skipped checks; an unset URL is a gate failure, never a passing test run.
`prepare-test-dbs.py` refuses existing databases and never drops one.

## Separate board runtime gate

The board sidecar has its own Starlette/CRDT environment. Do not install its
requirements into the API virtualenv. The API pytest command excludes the sidecar
directory; CI runs the actual loopback WebSocket tests separately and rejects skips.

```sh
python3.12 -m venv /tmp/opora-board-venv
/tmp/opora-board-venv/bin/python -m pip install -r apps/api/app/integrations/rtc/sidecar/requirements.txt 'pytest==8.3.5' 'pytest-asyncio==0.26.0'
OPORA_SIDECAR_PYTHON=/tmp/opora-board-venv/bin/python sh infra/scripts/verify-sidecar.sh
```

These tests cover viewer/drawer authorization, persisted Yjs state after restart
and invalid grants on loopback. They do not prove browser camera/microphone,
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
