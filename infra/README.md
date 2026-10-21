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

Open http://127.0.0.1:8080. PostgreSQL, API, web and optional dev inbox ports bind
loopback. The one-shot migration service must succeed before API/worker start.
Do not add fixtures to migrations. The default development inbox is a database
outbox sink; `dev_inbox` proves only local capture. Optional Mailpit can be started
with `--profile delivery-dev` for a later SMTP adapter. Mailpit does not configure
or prove email delivery by itself. AI/RTC/external delivery remain unavailable
until adapters and credentials are configured and tested.

`docker compose --env-file infra/.env -f infra/compose.yaml logs migrate api worker`
shows startup issues without HTTP payload/access logs. `down` preserves the
PostgreSQL volume. `down -v` destroys local data and is not part of validation.

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
# Only for a fresh local PostgreSQL instance, creates/migrates the three DBs:
python infra/scripts/prepare-test-dbs.py
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
three URLs separate from development/staging and the external G1 database. Their
exact database names are asserted by the domain suites. The CI pytest plugin
rejects skipped checks; an unset URL is a gate failure, never a passing test run.
`prepare-test-dbs.py` refuses existing databases and never drops one.
