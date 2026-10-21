# G1 independent acceptance

The suite targets a running localhost API backed by PostgreSQL. It does not mock
HTTP, bypass authorization in a public route, or infer persistence from a toast.
Staff sessions are issued only by the local fixture CLI. Browser acceptance uses
two isolated contexts for candidate/coordinator and a separate stranger identity.
The integrator captures actual browser proof through CUA.

Run unit/integration/contract checks first with `sh infra/scripts/verify.sh`.
The external HTTP journey will be run with `python -m pytest tests/e2e -q` after
the integrated API exposes the G1 endpoints. Missing endpoints must fail the gate,
not be skipped as optional. Run with `OPORA_G1_BASE_URL=http://127.0.0.1:8001` and
`OPORA_G1_FIXTURE_FILE=/private/tmp/opora-g1-fixture.json` (mode 0600).

Required evidence: ordinary questionnaire submission and reload; booking before
learning; four real published modules and ten questions; server scoring and a
second independent attempt; coordinator queue/review/public answer/outcome;
contact edit retains candidate identity/progress/booking; exact-origin + CSRF;
cross-owner and scope denial; private note absent from self JSON; stale version;
same-key retry and different-payload conflict; competing booking requests; fresh
grant/revoke; provider unavailable without false success. Race/ACL and denied
paths are part of the gate. Full calendar/assignment/RTC/AI/P20 acceptance remains
outside this first G1 gate until the corresponding packages exist.

Create credentials on a fresh disposable DB before starting tests (use the same
Python virtualenv, encryption key and DB URL as the API). Save the initial CLI
output: subsequent idempotent seed calls do not reveal an existing TOTP secret.

```sh
umask 077
(cd apps/api && python -m app.cli fixtures g1 --json) > /private/tmp/opora-g1-fixture.json
export OPORA_G1_BASE_URL=http://127.0.0.1:8001
export OPORA_G1_ORIGIN=http://127.0.0.1:5174
export OPORA_G1_FIXTURE_FILE=/private/tmp/opora-g1-fixture.json
python -m pytest tests/e2e -q
```

The staff fixture uses real HTTP challenge creation, the local CLI dev inbox,
HTTP challenge verification and TOTP MFA. Its cookie rotates at both identity
and assurance changes. Tests never call a public endpoint with a role label or
trust questionnaire email as ownership proof.
