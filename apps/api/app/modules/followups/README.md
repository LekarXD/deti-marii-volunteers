# P12 — preparation and human support

This module owns assignment checklists/questions, voluntary reflection drafts/submissions,
public review decisions and scoped support signals/history. P09 remains the source for
assignment ownership, confirmation, cancellation, occurrence conditions and attendance.
CRM remains the only follow-up task store. No reflection/checklist result grants an
assignment or settles attendance/minutes.

## Contracts and permissions

`router` exports the `/api/v1` endpoints from the implementation contract. Frontend exports
`FirstShiftPage`, `ReflectionPage`, `SignalsPage` for the canonical routes
`/my/assignments/:id/preparation`, `/my/assignments/:id/reflection`, `/fund/signals`.
`SignalsPage` also accepts `?reflection_id=UUID` for a direct staff review.

Staff permissions are `followups.read` and `followups.manage`, scoped to foundation or
group. A restricted/psychological case additionally requires `signals.restricted`; ordinary
staff receive neither its list entry nor details. Internal review notes are physically
separate in `reflection_review_notes` and require `followups.private_notes`. Self DTOs do
not load these notes. UI capabilities come from the server and do not infer authority
from a role label. Current entity scope and private permissions are checked before
idempotency receipt replay, including after grant revocation.

All commands run current authz and the shared contact guard before assignment/reflection
locks. Receipts, field-name-only audit and changes commit before success. Editable
aggregates use expected versions. Checklist keys are versioned and validated; progress
changes only after the server accepts the command.

Questions are linked to a genuine owned assignment, create a support queue entry plus a
CRM follow-up and expose the actual public staff answer back in preparation. A cancelled
assignment can request a different date; this does not silently create another assignment.
Reflection is voluntary and available after the confirmed occurrence ends. Draft save is
independent of submission. A help request, difficult mood, restricted case or wish to
change/pause/finish creates a durable support signal and revision-fenced CRM task.
Current no-contact policy suppresses contact tasks without dropping the reflection.

A restricted escalation needs an active eligible specialist. When none is configured,
submission returns `support_team_unconfigured`; the separately saved draft remains
editable and no forwarded/specialist response is claimed. The ordinary coordinator does
not gain a broad restricted audience automatically.

Staff public decisions cover next date, another role, discussion, pause and finish. They
persist in the reflection review, appear in self/staff DTOs and update CRM through its
owned `first_visit_outcome` and `schedule_user_follow_up` service boundaries. A restricted
case's text is not duplicated into broadly visible CRM agreements/task titles. Signal
assign/resolve/dismiss/reopen actions record reason, actor and history and update the same
CRM task store. Staff decisions do not automatically change volunteer event assignments.

CRM read seam: `latest_reflection_for_user(db, foundation_id, user_id, principal=None)`
returns only the latest visible submitted public fields. Missing/currently unauthorized
principals return None. Restricted details require the same explicit private-case grant;
internal notes are never included.

## Voice boundary

No fake timer, transcript or microphone request is rendered. `voice_available` is false
and the text alternative is explicit. The owner-checked audio-intent endpoint returns
503 `transcription_unconfigured`, creates no asset/job and claims no processing. Shared
purpose-bound upload/worker interfaces exist in P01, but no transcription provider is
configured. Actual recorder/ASR integration is an explicit remaining capability, not a
successful part of this text-support acceptance.

## Verification

Use the participant-owned PostgreSQL16 database, never a shared development database:

```sh
OPORA_PARTICIPANTS_TEST_DATABASE_URL=postgresql+psycopg://iliapetri@127.0.0.1:56147/opora_participants_test \
PYTHONPATH=apps/api:apps/api/tests python -m pytest apps/api/tests/followups -q
```

The suite uses real opaque-cookie/CSRF sessions and actual P09 invitation, approval and
confirmation commands. Eleven tests cover checklist CAS/idempotency, question -> staff
queue -> public answer, help -> single CRM task, restricted row/receipt revocation,
separate internal notes, missing specialist preserving a draft, truthful unavailable ASR,
no-contact suppression, all five review decisions on both sides/CRM and attendance
recorded before any reflection without minutes changing after submission. Three UI tests
cover saved draft after failed escalation, server-acknowledged checklist progress and a
public pause decision without private-note capability. TypeScript is checked against the
actual generated followups schemas.

A1 owns the seven-table forward migration and model discovery. A0 owns route mounting,
SDK generation and integrated visual acceptance. No production deployment, external
message or browser microphone permission was requested or used.

### Operational threshold signals

`GET/POST /coord/followups/rules` exposes foundation settings; `/reset` restores source defaults and `/evaluate` explicitly queues a fresh check. Defaults match `prototype/Admin.dc.html:656`: 2 consecutive recorded absences, 21 days since a recorded CRM contact, 14 days since learning assignment/progress, 3 days since application submission without a public response, 7 days until a role has no confirmed volunteer. Thresholds are positive bounded integers. Foundation `followups.manage` configures them with CAS/receipts and an audit event; group grants cannot change foundation settings.

The fenced `followups.rules` job evaluates real source tables and schedules the next hourly check. Revoked owner authorization blocks evaluation. Each source additionally requires the owner's current source-domain permission. Missing attendance is unknown and interrupts an absence streak; no CRM contact history is unknown rather than inferred silence. Learning uses canonical assignments/progress, never a service-time ledger. A source cap is reported unknown rather than silently truncating evaluation. Direct help/restricted reflection signals keep their original behavior.

`/coord/followups/rule-signals` is an internal queue, scoped by current `followups.read` foundation/group access and source permission (`assignments.manage`, `crm.read`, `learning.read`, `candidates.read`, `schedule.read` respectively). Read checks precede query limiting. Dismiss requires current matching manage/read capabilities, CAS and a reason; receipt replay rechecks them. An unchanged observation stays dismissed; a changed source observation reopens it. Clean evaluations resolve conditions no longer matching; incomplete/unknown evaluations do not silently resolve old observations. No automatic message is sent to anyone.
