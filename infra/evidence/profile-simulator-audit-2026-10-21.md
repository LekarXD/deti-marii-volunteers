# Profile and simulator PostgreSQL gate

Integration source `022da96fe44964f5ba1c1f21a2b0b023abd222bd`, working tree during
ongoing route/SDK integration. Selected only newly integrated P13/P16 suites:
`apps/api/app/modules/profile/tests` and `apps/api/tests/simulator`.
Result: **12 passed, zero skipped, 6.39 seconds**.

Created fresh exact-name `opora_profile_test` and `opora_simulator_test` databases
on the QA-owned PostgreSQL 16 cluster at loopback 56148. Provisioning checked
`data_directory=/private/tmp/opora-qa-pg-data` and refused existing database names.
Both upgraded from empty through current migration head before their deliberately
destructive, isolated test fixtures ran. Existing proof databases and active CUA
fixtures on port 56147 were not reset or used. Media used the isolated root
`/private/tmp/opora-qa-profile-simulator-assets`.

Profile checks exercise concurrent idempotent edits, verified-user scope,
manual-hour correction deltas, real generated PDF/download ACL, suggestion
accept/revert/version conflicts, explicit consent/export/deletion workflow and
actual-attendance ledger projection exactly once. No browser checkbox or existing
human profile was operated.

Simulator checks exercise reviewed dataset/test/publish guards, immutable scenario
versions, distinct fixture evaluation scores, private dialogue ownership,
registration denial, idempotent turns/callback replay, pause/stop/revocation,
rejected forged evidence, human support/appeal/correction, unknown provider timeout
without retry and budget denial. AI calls used controlled HTTP transports;
no external provider or fabricated runtime success was used as acceptance proof.

CI/provisioning now requires both dedicated URLs. This bounded result does not
claim browser acceptance, real AI quality, media permissions, production readiness
or completion of the overall P20 gate.
