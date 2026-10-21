# Participants P10A

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

## Assignment integration boundary

P10B is not implemented. `access.get_assignment_access` denies every assignment by
default. P09 must override this dependency with an adapter implementing
`AssignmentAccess.participants(db, principal, assignment_id)`. The adapter must query
current assignment ownership/state and foundation on every list/photo request and return
only the occurrence's historical participant IDs. It must not infer access from current
group membership. The volunteer page requires `?assignment_id=UUID` and displays the
actual server denial until integration. A staff safe preview is explicitly a preview.

## Verification

Set `OPORA_PARTICIPANTS_TEST_DATABASE_URL` to a dedicated PostgreSQL16 database named
`opora_participants_test`, then run:

```sh
PYTHONPATH=apps/api python -m pytest apps/api/tests/participants -q
```

The suite deliberately refuses a database with any other name. It tests real cookie/CSRF
sessions, current staff revocation, two groups, private-field/search absence, cross-foundation
isolation, denied volunteer list/photo access, membership overlap/history/CAS/concurrency,
idempotency, actual image upload/read, rejected replacement and revoked uploader access.

Local visual acceptance used the shared coordinator shell, real PostgreSQL fixtures and
a genuine cookie/CSRF staff session at desktop 1440px and mobile 390px. Five screenshots
were inspected; no JavaScript error or horizontal overflow occurred. Participant edits
and group title/schedule/location/leader/coordinator edits persisted after browser reload.
Screenshots are temporary review artifacts in `/private/tmp/p10a-*.png`. Shared hero-title
typography was restored from the accepted prototype by the shared UI owner.

Remaining gate: P09/P10B assignment snapshots and real volunteer positive/revoked access.
No fixture people are loaded in a product path and no assignment state is invented.
