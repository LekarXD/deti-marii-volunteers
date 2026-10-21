# Bounded release audit — 22 October 2026

Scope: independently reviewed implementation domains, source-controlled workers, trusted subpath deployment, and reproducible synthetic local PostgreSQL/HTTP/browser flows. Findings below are confirmed defects, not speculative hardening. This is not an exhaustive security scan or a claim of zero remaining bugs.

| Trigger / impact | Minimal implemented fix | Integration commit / evidence |
|---|---|---|
| Concurrent occurrence/series cancellation, assignment approval or capacity update reused stale ORM instances after waiting for row locks; returned500 or admitted stale capacity | Refresh authoritative locked objects before version/business checks | `c3b4339`, four controlled PG/HTTP race tests |
| Concurrent follow-up update reopened a completed or no-contact-cancelled CRM task | Refresh volunteer/task under existing locks; reject stale version with409 | `3a1a2cf`, two PG/HTTP race tests; activities+CRM+performance32 passed |
| Hours entered by another coordinator while a Dobro reminder was being delivered produced a stale internal message | Same foundation fence held through fresh projection and message commit, with existing authorization lock order | `031bb49`, independent failing baseline then passing regression; affected19 passed; bounded-core-audit evidence |
| Profile save response overwrote edits made during request | Rebase saved version while preserving newer draft | `97b2733`, focused UI regression |
| Photo preparation continued after unmount/principal change | Abort and recheck principal across asynchronous preparation/upload/completion | `97b2733`, focused UI regression; merge independently rechecked after prefix port |
| Notification preference refresh discarded unsaved quiet/channel settings | Keep dirty state, expose version conflict and explicit reload | `97b2733`, focused UI regression |
| Route change carried a private question/restricted flag to another assignment | Assignment-keyed workspace and pending-action guard | `97b2733`, focused UI regression; frontend audit20 focused+28 regression passed |
| Worker died on last capture attempt; queue became dead but take stayed permanently starting/capturing/stopping | Reconcile authoritative dead job under existing locks; fail take/revoke renderer grant, allow explicit new take | `3c439e5`, real PG expiry→GET→retake regression; no blind rerecord or job resurrection |
| Media child process discarded image NODE_PATH, making Playwright unavailable outside a repository node_modules tree | Preserve only PATH/LANG/NODE_PATH; keep credentials and NODE_OPTIONS excluded | `9d6426e`, targeted environment regression; native Linux image acceptance remains a separate gate |
| Pinned board SDK requested nested fonts/locale chunks while build copied assets flat | Match exact pinned SDK asset layout and prefixed asset base | `9f0cf45`, actual loopback HTTP font/locale/resource200 checks |
| Long presenter name covered most of camera overlay | Bounded one-line label; full accessible name/title; preserve video mount | `064d503`, Stage11 passed |
| Web Docker build compiled a cross-language test importing a JSON fixture absent from image context | Copy exact canonical fixture and include it in minimal source archive | `30d9a2a`, actual failed remote build; rerun image acceptance is separate |
| Preview IO manifest omitted followups.rules and dobro.reminders.scan | Add both existing handlers; compare all preview workload owners with canonical registry manifests | `e202aa9`, worker manifest+sandbox4 passed |

## Verification boundaries

Full frontend `80db674`:292 passed/60files, typecheck and build passed. Later Stage fix has11 focused passes. API/SDK generated contract check passed at369 paths. Trusted-prefix API42 passed/zero skips, including actual private PNG bytes, hostile forwarded prefix, stranger denial and scoped logout.

The first final complete API attempt was interrupted by local PostgreSQL DiskFull after140 passes;153 setup errors are environment failures, not passed tests. The owned cluster was recovered by normal redo/checkpoint and only reproducible own archives were removed. The same-source complete rerun passed293 tests/zero skips at3c439e5; final9d6426e delta passed16 tests/zero skips. These overlapping sets are not summed. Exact-source evidence is in final-complete-api-gate-2026-10-22.md. No WAL files were manually removed.

Main push and image build alone do not establish deployment. Remote runtime SHA, migrations, health, preserved gateway routes and native recording capacity require independent server evidence. Kinescope transfer is **not implemented**; current video bytes use private application asset storage. AI/ASR/email/Telegram delivery is not claimed configured. Newly arrived product changes are tracked in `docs/implementation/product-delta-2026-10-22.md`.
