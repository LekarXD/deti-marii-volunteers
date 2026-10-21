# Bounded Knowledge, followup, notification and media verification

Source: integration working tree on 2026-10-21, initially during commits
`6133592`–`e894070`; privacy closure checked after integrated `84ccd64` at
`70de126`. Main/router/SDK integration remained in progress. These are bounded
local functional results, not final immutable-release or production evidence.

## Executed checks

Only newly added suites were selected: `apps/api/tests/knowledge`,
`apps/api/tests/followups`, `apps/api/tests/test_notifications.py` and
`apps/api/app/modules/studio/tests`. Result: **32 passed, zero skipped,
18.18 seconds**. Tests used the QA-owned PostgreSQL 16 cluster on loopback 56148,
with separate core, participant, Knowledge and Studio test databases and isolated
`OPORA_ASSET_ROOT=/private/tmp/opora-qa-new-module-assets`.

Provider tests used controlled HTTP transports and generated test media. The
notification test used an actual loopback SMTP receiver; it did not contact an
external recipient. The PDF converter processed a generated PDF in its isolated
child process. No real AI endpoint, camera or microphone was used.

The independent board runtime used `/private/tmp/opora-board-venv`, separate from
the FastAPI environment: **3 passed, zero skipped, 1.07 seconds**. Actual loopback
WebSocket/Yjs tests cover viewer/drawer authorization, persistence across restart
and invalid grants. API collection now excludes that separate process directory;
CI runs it in a dedicated virtualenv and rejects skips for both runtime gates.

Requested P09 followup checks also passed independently: ongoing activities reject
attendance; an existing attendance fact prevents cancellation and keeps factual
correction available. **2 passed, zero skipped, 5.15 seconds**. This closes the
two defects recorded in `expanded-domain-audit-2026-10-21.md` after owner fixes
`cf8ae5e` and `9b8d261`.

## Confirmed Knowledge defect and independent closure

Original `apps/api/app/modules/knowledge/service.py::mentor_view` selected the
current body of an approved human answer before checking the source's current
visibility. A candidate's answered question could therefore reveal a newly
staff-only source body even while search and citations correctly hid it.

Actual PostgreSQL/HTTP trigger: create a candidate question, publish a coordinator
answer, then edit its linked source to a synthetic private body, review, publish
and index it as staff-only. Candidate search returned no private fragment, but
GET of the owned mentor run returned the private body with zero citations.
QA reported this to the owner and did not change domain code.

Owner fix `1556f72`, integrated as `84ccd64`, applies the same current visible
source/version query before projecting the answer body. Independently reran
`test_published_search_acl_unknown_question_human_answer_and_withdrawal` against a
freshly migrated isolated Knowledge schema: **1 passed, zero skipped, 0.38 seconds**.
The regression checks the real source edit/review/publish/index path and suppresses
private text in direct run, history, old ask receipt and saved report evidence.

The old destructive test DB had tables created by newer `Base.metadata.create_all`
before its migration stamp advanced. It was rebuilt only in the owned disposable
Knowledge schema; this test-fixture mismatch was not counted as a runtime defect.

## Bounded read-only review

Reviewed current AI provenance/citation filtering, budgets and durable calling
markers, ambiguous-provider failure states, fresh permission before old receipt
projection, notification opt-out/current contact checks and explicit
accepted/unknown/unavailable outcomes. Reviewed media commands' fresh permissions,
enrollment, source bindings, lease fencing and board introspection. No additional
concrete defect was established within this pass; the tests do not prove all
interleavings or external provider behavior.

Core migration upgrade through `59a1319905d3` succeeded. `alembic check` still
reported the known in-progress notification companion model fields (quiet hours,
topics and defer time); parity was not reported green. No candidate consent UI,
shared browser profile, production service, Docker context or external messaging
was operated. Simulator runtime and full P20/provider/media/deployment gates remain
outside this completed bounded check.
