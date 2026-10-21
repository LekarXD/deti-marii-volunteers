# Independent G1 QA evidence — 21 October 2026

This records local functional evidence from the integrated implementation working
tree. It is not a production deployment or immutable final-release certification.
Final acceptance must record the integrator's final commit and runtime release.

## Latest immutable checkpoint

`c6e35434188d46cdd19d8f7a351d183909483f0f`: expanded API/contract gate **140 passed,
zero skipped**. Updated current form/source HTTP G1: **26 passed, zero skipped**
at `29f5048` (runtime unchanged by the subsequent test-only fixture fix).
Migration head `c74a006971d4`, metadata parity passes. Exact commands, source
manifest and proof boundaries are recorded in
`infra/evidence/final-api-g1-gate-2026-10-21.md`. The earlier entries below retain
the historical progression and do not replace that checkpoint.

## Verified

- External HTTP G1: all 14 cases passed together, with zero skipped, in 6.07
  seconds through the actual `run-g1.sh` lifecycle (CLI seed, API startup, tests,
  API stop, temporary-secret cleanup). It used fresh `opora_qa_http_test` on the
  separate QA PostgreSQL 16.14 cluster, API port 8002. This includes verified login
  claiming only its registration and global assignment busy conflicts.
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
- The complete backend/contract aggregate passed 43 checks with zero skipped after
  collecting all `apps/api`, including candidate tests nested under their module.
  Its four domain database opt-ins were set, separately from the core and HTTP G1
  databases. The no-skip plugin was enabled.
- A separate QA PostgreSQL cluster was initialized at
  `/private/tmp/opora-qa-pg-data`, loopback port 56148, with private Unix socket.
  It is separate from the integrator's cluster on port 56147. Existing domain
  databases on the integrator's cluster were not reused or dropped.
- Database-only recovery drill: `pg_dump --format=custom` from the QA core database,
  restore into a new QA database, then compare migration head and every public
  table's row count. All 55 table counts and head matched. The dump contains only
  invented test data and is stored privately outside the checkout.
- Compose syntax validates with `docker-compose ... config --quiet`.

## Bounded follow-up after the P14 receipt finding

Ten additional real HTTP/PG cases passed (1.13 seconds): role, opportunity,
calendar-series, private participant-note and private messaging-group creation,
with both a new command and an old receipt. Each queues an actual capability
revoke before the command's shared authorization guard; revoke commits first,
and the waiting command plus a direct post-commit replay return 403. Capabilities
are restored through the authorized admin API after each isolated test.

Two additional messaging membership cases passed (1.37 seconds). An actual
coordinator member revoke wins the conversation lock before a verified member's
new send or old send receipt. The removed member cannot read detail, history or
sync, and a denied send appends no message. These checks found no further runtime
failure in the five requested domains. They do not certify unrelated commands.

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
   `1291819`; the complete aggregate after integration passed: 43 tests, zero
   skipped, in 7.62 seconds on the separate QA cluster. This includes nested
   candidate tests, calendar, messaging and delivery tests present at that point.

## Private asset backup and restore drill

The real database-plus-private-files drill passed on the separate QA cluster at
56148. Frozen API source: integration commit
`c7c58c0fa3f2ef1481ab07c855dc7891dc60bcaa`, with API working-tree changes, copied
into a private immutable test directory. Its complete API file manifest hashes to
`f30461c549e5bb2143b1557f4241c979ac79e8f967965eca677d7712c421fc9b`.
Both source and restored API `/version.json` returned the corresponding
commit/tree release label. This remains working-tree snapshot proof, not final
immutable-release certification.

A real CLI-seeded coordinator completed HTTP email challenge verification and
TOTP, created an image upload intent, uploaded a generated 227-byte PNG, completed
validation and bound it to a participant through the actual API. A separately
verified ordinary principal received 404 for both the participant photo and raw
asset endpoint. The source API was stopped before taking its database dump and
private-file snapshot; no worker was running.

Restoring into a new database and new private storage root preserved all 69
public-table counts, head `3006f3293ffc` and the file manifest. Both authorized
image endpoints returned the original checksum
`61523728612559eed72614bd2aa44ce6d4d3c9eba90ab02e23055e8f862d74b9`.
The stranger still received 404 on both endpoints. After committing a staff
membership revocation only in the restored fixture database, the original
uploader also received 404 on both endpoints. This proves upload ownership does
not bypass the participant permission after revocation. The source membership
remained active and unchanged.

Revocation uses an explicit isolated test-fixture `staff_memberships` transaction;
there is no public membership-revoke endpoint. All files, DBs and APIs were
isolated from the shared browser profile, the default asset root and production.
Both temporary API processes stopped cleanly. Evidence is checked in at
`infra/evidence/private-asset-restore-2026-10-21.json`; private dumps, encryption
key, fixture credentials and full source manifest remain mode 0600 outside Git.

## Proof boundaries

Actual two-context browser and visual acceptance belongs to the integrator's CUA
run. The authored Playwright suite was collected, not launched. The six smoke
checks cover draft/reload, network recovery and widths 390/768/1050/1440; they do
not replace the ordinary complete questionnaire/coordinator browser journey.

Docker images and the container stack have not been built or started here. The
`docker compose` plugin is absent; the selected existing Docker daemon denied
socket access. No Docker context or existing service was changed. Native
PostgreSQL/API evidence is available, and Compose configuration was validated.

The initial recovery drill proved database contents only; the later isolated
private-image drill above additionally proves one real participant image and its
access boundary survive DB/files restoration. Large/multiple file sets, provider-
backed email/AI/RTC outcomes, media staging, all later domain packages, full P20
and a staging deployment still require their own evidence. No production system was accessed.
