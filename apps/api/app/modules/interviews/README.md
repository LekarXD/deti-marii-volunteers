# P06 interviews

`router.router` mounts `/api/v1` routes. Booking and application review/introduction progress are independent. A submitted application is the only application-state prerequisite. Registration ownership is adopted through `service.claim_registration` in the auth verification transaction.

Availability stores local dates/minutes plus IANA timezone. Once and weekly rules support selected weekdays, week intervals, end dates and dated skip/override/restore exceptions. Reads materialize requested ranges (at most 93 days per request, any navigable period). Dates in slot queries use the viewer timezone; returned instants are UTC. Nonexistent DST times and intervals whose real duration differs from their configured duration are skipped; ambiguous times choose the earlier occurrence.

Each write rechecks auth under the shared actor guard, uses actor/operation/key payload receipts, flushes domain facts/audit/outbox and commits before success. Availability changes reject affected booked snapshots. Pause only closes free availability. Active booking uniqueness, buffer-aware PostgreSQL exclusions and shared candidate/coordinator resource reservations protect races with both interviews and confirmed activities. A rejected move rolls back its booking, reservation, receipt and event together.

Self booking DTOs omit private notes. Staff DTOs include only the name projection needed by the meeting UI, avoiding a second broader candidate permission requirement. Private text is excluded from public events and outbox payloads.

## Verification

`OPORA_TEST_DATABASE_URL=<disposable postgresql+psycopg URL> PYTHONPATH=apps/api pytest apps/api/tests/interviews -q -o asyncio_mode=auto -o asyncio_default_fixture_loop_scope=function`

Each test creates and drops an isolated PostgreSQL schema. The suite checks competing bookings, idempotent replay/payload conflict, candidate ACL, failed-move rollback, successful stable-ID move, global resource conflict rollback, pause, version conflicts, protected window edits/exceptions, private/public outcome separation, post-guard permission revocation, viewer midnight boundaries, multiweek recurrence, buffers and DST.

## Remaining integration boundaries

- `next_contact_date` is a persisted public agreement. Creation of a real CRM `follow_up_tasks` record belongs to P11's shared service and remains a cross-package integration gate.
- Transactional internal outbox events include booking ID/version. P17 must resolve the current booking and drop stale versions before delivery. P06 does not claim external delivery or Telegram linkage.
- The integration owner supplies Alembic revisions, router wiring and generated OpenAPI TypeScript. This package does not maintain competing schema or root entrypoints.
