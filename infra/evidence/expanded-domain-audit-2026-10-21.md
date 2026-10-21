# Expanded domain gate and bounded audit

Requested scope: integrated CRM P11, P09 participation/assignments, P10B current
participant access and newly added Studio/worker models. Source is the integration
working tree during ongoing route/SDK wiring, initially at `971d51f1b0494141513130fa106fa65c15b9edef`.
This is functional evidence, not a final immutable-release claim.

## PostgreSQL verification

All six test databases were isolated on the QA-owned PostgreSQL 16 cluster at
127.0.0.1:56148, data directory `/private/tmp/opora-qa-pg-data`. Existing application
and domain databases on port 56147 were not touched. All ten then-integrated
migrations upgraded successfully, and `alembic check` reported no drift.

The expanded collection includes all `apps/api` paths, including nested application
and CRM tests, plus independent contract checks. Initial run: 47 passed and 26
fixture setup errors. Migrated Studio tables referenced `media_assets`, but the
pytest metadata set did not contain Studio models before early `drop_all` calls.
The test-only `infra.pytest_gate.py` now loads the canonical model set in
`pytest_configure`, matching runtime and Alembic. A focused previously failing
candidate fixture passed, followed by the complete expanded run: **73 passed,
zero skipped, 21.78 seconds**.

CRM's explicit disposable DB opt-in is now included in CI/provisioning:
`OPORA_CRM_TEST_DATABASE_URL`, exact database name `opora_crm_test`.

## Confirmed runtime findings sent to the domain owner

### P09 attendance can be recorded while the activity is still running

Evidence: `apps/api/app/modules/activities/assignment_service.py`, function
`record_attendance`, originally lines 170–174. It rejects only a future start.
`docs/implementation/data-model.md:209` requires verifying activity completion.

Actual PostgreSQL/HTTP reproduction reused the existing invented P09 test fixture:
create/invite/approve/confirm, then set the fixture activity to start one minute
ago and finish one hour ahead. The coordinator attendance POST with 60 minutes
returned **200**, created attendance and a pending ledger event.

Minimal correction: require `ends_at <= now` before recording fact, and advertise
the attendance action only after that boundary. The owner was notified; QA did
not edit domain implementation.

### Cancelling recorded participation makes its fact impossible to correct

Evidence: the same service's `cancel` accepts a confirmed assignment regardless
of existing attendance; `record_attendance` requires the assignment remain
confirmed.

Actual PostgreSQL/HTTP reproduction: confirm → ended activity → attendance 120
minutes → volunteer cancellation. Cancellation returned **200**, changed the
assignment to `cancelled`, and retained attendance 120. The coordinator's ordinary
correction command then returned **409 / attendance_not_available**.

Minimal correction: reject cancellation once attendance exists, including the
calendar cancellation path, or explicitly preserve authorized factual correction
for that state. The owner was notified to choose the consistent implementation
and add focused regression tests. QA did not edit domain implementation.

## Boundaries

The two state reproductions used only invented local PG test fixtures and real
server handlers/authorization. They did not use or attempt the candidate browser
consent path. No browser operation, production access, Docker context change or
external message was performed.

Read-only review confirmed fresh assignment ownership/state checks for participant
JSON/photo access, foundation restrictions and current-user revocation, as exercised
by the P09/P10B tests. CRM consent/no-contact guards, renewed-consent checks,
transactional merge/import handling and fresh command permission checks were
reviewed; no additional concrete defect was established in this bounded pass.
Passing 73 tests does not cover the two newly reproduced state edges or complete
full P20/provider/media/deployment acceptance.
