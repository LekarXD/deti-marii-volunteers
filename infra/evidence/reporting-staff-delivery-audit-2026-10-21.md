# Bounded Staff / reporting / delivery audit

Immutable API source: `71b75c0c7436c067c3614432d93efbc28cdf94f9`, extracted by
`git archive` to `/private/tmp/opora-qa-snapshot-71b75c0`. Dirty integration
`main.py`, generated SDK and Vite changes were not included in this bounded run.

The existing owned PostgreSQL cluster at loopback 56148 was verified by exact
data directory `/private/tmp/opora-qa-pg-data`. The new
`opora_reporting_test` database contains only synthetic reporting fixtures;
Staff used its own temporary schemas in `opora_domain_test`, and delivery used
`opora_qa_test`. No shared integrator, G1, proof, restore or production DB was reset.

Results:

- Existing Staff9 + reporting4 + delivery6: **19 passed, zero skips, 7.88s**.
- Added independent reporting boundary suite: **2 passed, zero skips, 1.66s**.
  It checks foundation/group scope before writes, denies foreign foundation
  resources, verifies no forbidden report row was inserted, exercises concurrent
  section CAS with exactly one winner, and denies an old receipt after write
  permission is revoked while preserving authorized read access.
- Core migration upgraded the disposable main test DB to
  **`84fc8b53ac5d` (head)**; `alembic check` found no new upgrade operations.
  Only the existing informational computed-tsvector comparison warning appeared.

Commands (using the owned database URLs and the API virtualenv):

```sh
python -m pytest -p infra.pytest_gate -c apps/api/pyproject.toml apps/api/app/modules/staff/tests apps/api/app/modules/reporting/tests apps/api/tests/test_delivery.py apps/api/tests/test_delivery_extensions.py -q --tb=short
python -m pytest -p infra.pytest_gate -c apps/api/pyproject.toml /private/tmp/opora-qa/tests/contract/test_reporting_boundary.py -q --tb=short
```

The independent test source lives in QA's `tests/contract`; both commands used
the frozen API source on `PYTHONPATH`, plus that source's `apps/api/tests` for
existing fixture imports. The skip-rejecting QA plugin loaded the same model set
as Alembic. No domain runtime implementation was edited by QA.

## Confirmed integration gap and owner fix

At this checkpoint `staff/catalog.py` exposed `reports.read` only and gave it
foundation scope only. Reporting requires `reports.write` and `reports.export`
and implements group scope; Staff's `selections()` rejects absent catalog values.
Thus ordinary Staff administration could not grant reporting editing/export or
group reports. `recordings.manage/review/publish` were also absent. This was
reported to Staff's owner, who delivered `9b7d5ee` with the exact missing entries,
scope constraints and an HTTP grant/resolved-principal test. That fix is outside
this immutable 71b75c0 run and needs its integrated follow-up checkpoint.

## Packaging checkpoint

CI, fresh test-DB provisioning and the owned reset allowlist now explicitly
include `OPORA_REPORTING_TEST_DATABASE_URL` / `opora_reporting_test`. There are ten
domain databases, plus the main disposable test DB; Staff uses isolated schemas
and can use the existing domain test URL.

The dedicated media image/overlay/runbook are added separately. Native
`docker-compose -f infra/compose.yaml -f infra/compose.media.yaml --profile media
config --quiet` succeeded with a synthetic local password. The initial sandboxed
Docker read was denied; an approved read-only daemon query subsequently returned
server29.5.2. No context or service was changed. No image build or container
sandbox/capture proof is claimed in this checkpoint. The integrator additionally
fixed the web Dockerfile to copy the new recorder HTML entry after QA reported it.

These are bounded API/fixture results, not a whole-application HTTP/browser gate,
full P20 acceptance, live provider delivery, a container rollout or production proof.
