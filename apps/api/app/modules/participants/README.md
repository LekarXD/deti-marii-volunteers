# Participants P10A / P10B

The module owns staff participant records, separate safe briefings and private notes,
private photo attachments, groups, dated membership intervals and leader/coordinator
scope. `router` exports the API; `models` exports the five SQLAlchemy models.
Root/A1 owns model discovery and migrations.

Foundation grants: `participants.read`, `participants.write`,
`participants.private_notes`, `groups.read`, `groups.write`. Group-scoped grants are
supported. An active MFA-authenticated staff member assigned as group leader or
coordinator has read/write access to that group and its current members, but no
implicit private-note permission and no ability to reassign the group's staff.
Unassigned participants can only be created/managed by foundation-scoped staff.
A foundation-scoped group editor can appoint only active staff from the same foundation.

All commands use current authz guard, per-actor idempotency receipts, audit field names
and commit before success. Updates require `expected_version`. Membership intervals
are start-inclusive/end-exclusive; all membership writers lock the group before checking
for overlap. Ending participation shortens its interval and preserves the historical row.
The `at` parameter returns group composition on a particular Moscow calendar date;
it does not replace an occurrence's historical snapshot.

Private notes are available exclusively at `/coord/participants/{id}/private-notes`.
They do not enter participant/group JSON, name search or volunteer DTOs. Photo upload
uses the shared private asset lifecycle, validates ready images before attachment and
retains the old photo when a replacement fails. Attachment changes the generic asset
permission so the uploader cannot retain file access after their staff privilege is revoked.

## Assignment access (P10B)

A0 installs `ActivityAssignmentAccess` from P09 through the `get_assignment_access`
FastAPI dependency. The fallback still denies every request if the adapter is absent.
The concrete adapter checks the current principal, assignment owner, foundation,
confirmed status and occurrence cancellation on every JSON and photo request. An
active staff session or upload ownership does not replace assignment ownership.

P09 captures participant IDs and group IDs at confirmation from the occurrence's local
calendar date and the start-inclusive/end-exclusive membership intervals. This module
reads those captured IDs; it never recalculates a roster from today's group membership.
Backdated membership changes and newly added members do not rewrite a confirmed roster.
The assignment state and its durable snapshots remain exclusively owned by P09.

`GET /me/assignments/{id}/participants` returns only safe participant DTOs.
`GET /me/assignments/{id}/group-briefing` adds only authorized group IDs/titles.
The generic group's current schedule is not represented as an occurrence's conditions.
Both responses are private/no-store. The participant photo path repeats the current P09
check before returning the shared asset's private/no-store response.

The volunteer page at `/me/group?assignment_id=UUID` uses the generated group-briefing
schema and the actual API, displays the authorized group title and safe practical notes,
and uses scoped photo URLs. It refetches on focus and every 15 seconds while visible.
A rejected refetch hides the previously rendered participant and image, even when Query
still holds prior successful data. Opening the page without an assignment requests no data.

## Verification

Set `OPORA_PARTICIPANTS_TEST_DATABASE_URL` to a dedicated PostgreSQL16 database named
`opora_participants_test`, then run:

```sh
PYTHONPATH=apps/api python -m pytest apps/api/tests/participants -q
```

The suite deliberately refuses a database with any other name. It loads the canonical
model graph before resetting its dedicated database so lazily loaded readiness models
are included on repeated scoped runs. It tests real cookie/CSRF
sessions, current staff revocation, two groups, private-field/search absence, cross-foundation
isolation, denied volunteer list/photo access, membership overlap/history/CAS/concurrency,
idempotency, actual image upload/read, rejected replacement and revoked uploader access.

Local visual acceptance used the shared coordinator shell, real PostgreSQL fixtures and
a genuine cookie/CSRF staff session at desktop 1440px and mobile 390px. Five screenshots
were inspected; no JavaScript error or horizontal overflow occurred. Participant edits
and group title/schedule/location/leader/coordinator edits persisted after browser reload.
Screenshots are temporary review artifacts in `/private/tmp/p10a-*.png`. Shared hero-title
typography was restored from the accepted prototype by the shared UI owner.

P10B verification also runs the actual P09 invitation, approval and confirmation APIs,
using two groups/two actors and an actual uploaded PNG. It covers an Auckland-local date
whose UTC date is different, both membership date boundaries, frozen roster after edits,
private-field absence, staff/uploader non-bypass, approved-but-unconfirmed denial,
assignment/event cancellation and account revocation across JSON/briefing/photo endpoints.
A separate database test rejects cross-foundation photo/leader/coordinator references.
The combined P07-P10 PostgreSQL suite passes 25 tests. Two focused UI tests cover the real
rendering branch after successful data then a revoked refetch and missing-assignment safety.

Root integration must install the dependency and regenerate the SDK. The P09 package's
acceptance gate remains owned by A0/A5; this module does not independently declare that
gate complete. No fixture people are loaded in a product path and no assignment state is invented.
