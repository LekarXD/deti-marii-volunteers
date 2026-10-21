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

## Final wrap delta

- `72c51b8`: staff retains coordinator navigation in shared Studio; volunteer navigation remains unchanged.
- `11ac792`: identical Studio errors render once; distinct failures remain visible.
- `9b1beb3`: actual isolated100MiB paused video under64MiB Nginx/tmpfs killed only the test web container; proxy_buffering off passed the identical repeat without buffering growth/OOM.
- `ab1d5a0`: actual Linux sparse WebM advertised1000fps, creating thousands of duplicate frames. Explicit25fps CFR plus rate/frame-count validation fixed a genuine30s Stage export:13.778s encode,1.361s full decode,757frames, complete AAC. Existing recording/frame/checkpoint/live regression28 passed, zero skips. No timeout increase.
- Final frontend298 passed/62files and TypeScript passed. Full API293 and16 overlapping delta remain documented separately; counts are not added.

At user wrap, long/load capture is NOT accepted and public capture remains disabled. Strict live token-revocation policy was not weakened; no additional demo event was saved. A rejected attempt to substitute application revocation semantics made no source changes, and the isolated admission proposal was not promoted. Public coordinator normal login/MFA and private desktop/mobile read flows passed; only ephemeral codes were temporarily handed off under explicit user approval and deleted after use.

## Final deployed code

Immutable app image source ab1d5a04adae6b6c839ea33f107678a7222b4e08 deployed. Independent publicHTTPS version.json returned that exactrelease200; ready returnedready200. Final fresh native exactimage proof:8.938s MP4/25fps175frames/H264AAC1920x1080, full decode,58continuous100mswindows minRMS.04988,440Hz,3journal,onecapturebrowser and source recovery. Prior30s genuineStage proof:13.778s encode/1.361s decode. This is NOT long/load acceptance. Public capture remainsfalse; no strictpolicy change or extra demo event was made. Final CUA normalcoordinator session survived rollout and sharedStudio now retains fund navigation.

## Public form data boundary

Four additional anonymously submitted applications beyond the five seeded records have unknown origin and are preserved unchanged. Do not label them as fictional tests. Evidence contains aggregates only; no personal fields were exported.
