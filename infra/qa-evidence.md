# Independent G1 QA evidence — 21 October 2026

This records local functional evidence from the integrated implementation working
tree. It is not a production deployment or immutable final-release certification.
Final acceptance must record the integrator's final commit and runtime release.

## Verified

- External HTTP G1: all 12 then-current cases passed against an actual localhost
  API on port 8002 with PostgreSQL 16.14 (`opora_qa_g1_v2`). Two subsequently added
  cases also passed independently: verified login claims only its registration,
  and a migrated global assignment reservation blocks interview booking atomically.
- The flows cover both questionnaire → booking → learning and questionnaire →
  completed learning → booking. Four published modules, ten questions, server
  score 4/10 for all-zero answers, repeat attempt history, acknowledgement without
  a new pass threshold, revision preserving identity/progress/booking, coordinator
  queue/review/public reply and private notes are checked by server readback.
- ACL/CSRF/exact Origin, stale versions, actor-bound receipts and payload mismatch,
  competing candidates, availability edit versus booking, failed move preserving
  the original, fresh grant/revoke/group scope, logout and old-cookie revocation
  have explicit checks. Deterministic PostgreSQL advisory-lock tests verify revoke
  commits before a waiting staff command and before a cached receipt replay.
- Three OpenAPI contract checks passed. Browser test collection lists six smoke
  cases successfully; this does not count as running a browser.
- Empty migration to head and upgrade of the populated G1 database passed;
  `alembic check` reports no new upgrade operations after migration
  `30b4f832ef68`. The prior head was `b3566c48dbbb`.
- A separate QA PostgreSQL cluster was initialized at
  `/private/tmp/opora-qa-pg-data`, loopback port 56148, with private Unix socket.
  It is separate from the integrator's cluster on port 56147. Existing domain
  databases on the integrator's cluster were not reused or dropped.
- Database-only recovery drill: `pg_dump --format=custom` from the QA core database,
  restore into a new QA database, then compare migration head and every public
  table's row count. All 55 table counts and head matched. The dump contains only
  invented test data and is stored privately outside the checkout.
- Compose syntax validates with `docker-compose ... config --quiet`.

## Defects found and resolved

1. A waiting interview mutation could execute after a committed permission revoke.
   A real queued HTTP revoke returned 200 and the forbidden mutation returned 201.
   The domain owner added a fresh permission check after the shared transaction
   guard and before receipts. Both new-command and replay race cases then passed.
2. Real migration/schema parity was incomplete: current application revision FK,
   matching role-version composite FK and its referenced unique pair were missing.
   The platform owner added forward migration `30b4f832ef68`; empty and populated
   upgrade checks now pass without editing an applied base migration.
3. Aggregate pytest initially reported 19 skipped domain checks when their database
   opt-ins were absent. CI now provisions separate disposable databases and enables
   all opt-ins. `infra.pytest_gate` makes any skipped check fail the gate. Its
   negative check returned exit 1 for six intentionally unconfigured domain tests.
4. The complete no-skip backend/contract run exposed a fixture mismatch: 26 passed,
   one interview global-ledger test failed because ORM `create_all` omitted the
   exclusion constraint supplied by the migration. The actual migrated HTTP
   global-ledger check passed. The platform owner supplied metadata parity fix
   `1291819`; aggregate confirmation after integration is tracked by the integrator.

## Proof boundaries

Actual two-context browser and visual acceptance belongs to the integrator's CUA
run. The authored Playwright suite was collected, not launched. The six smoke
checks cover draft/reload, network recovery and widths 390/768/1050/1440; they do
not replace the ordinary complete questionnaire/coordinator browser journey.

Docker images and the container stack have not been built or started here. The
`docker compose` plugin is absent; the selected existing Docker daemon denied
socket access. No Docker context or existing service was changed. Native
PostgreSQL/API evidence is available, and Compose configuration was validated.

The recovery drill proves database contents only. Private-asset restoration,
provider-backed email/AI/RTC outcomes, all later domain packages, full P20 and a
staging deployment require their own evidence. No production system was accessed.
