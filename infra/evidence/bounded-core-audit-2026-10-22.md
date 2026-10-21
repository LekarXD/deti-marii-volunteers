# Bounded authorization, source-delivery and durability audit — 2026-10-22

Baseline source: `161402dbbedf714912df141e12eed1a7aa38bfb7`. Read-only production-source review, with one new isolated PostgreSQL/ordinary-HTTP reproduction. The concurrent frontend My Path edits were excluded by archiving committed API source. No external provider, production database, actual Telegram callback, device, or deployment mutation was used.

## Confirmed finding: stale Dobro reminder during a concurrent transfer (P2)

**Trigger:** source-bound internal delivery calculates hours due; a different authorized coordinator marks those hours transferred before the delivery transaction inserts its message.

**Evidence:** baseline `apps/api/app/modules/dobro/notifications.py:23-28` read settings, current authority and `transfer_period` without the Dobro foundation advisory lock. Manual marking uses ledger subject locks followed by the foundation lock (`apps/api/app/modules/dobro/service.py:267`); the scheduler already uses that foundation lock (`apps/api/app/modules/dobro/jobs.py:46`). A source resolver's authorization lock protects its owner, so a second coordinator is required to expose the missing shared domain lock.

**Impact:** a source-bound notification tells the coordinator there are hours still to transfer after another coordinator has already completed that transfer. This finding concerns the internal Opora notification; no external message was sent.

**Reproduction:** `tests/contract/test_dobro_reminder_race.py` creates fictitious users and real authenticated sessions through the existing domain fixture, obtains normal HTTP/CSRF headers, queues the real reminder via its worker, and pauses only after its real projection query. Another staff identity performs the actual `mark-entered` HTTP request. At the baseline, that request committed `200` while delivery retained the stale one-hour projection, and the internal message was then inserted. **1 failed in1.36 seconds.** No principal override or test-only authorization bypass was added.

**Fix:** Dobro owner checkpoint `c8ef4a6`, integrated as `031bb49617ddd3309a4ab007a020120b12350beb`. Current authority is checked before taking the shared foundation lock; settings are reread with `populate_existing`, and the lock remains held through the message insert. The resolver never requests ledger subject locks after taking the foundation lock, preserving the attendance/marking lock order. Fixed evidence: `apps/api/app/modules/dobro/notifications.py:23-32`.

**Verification:** the same independent regression passed on an immutable archive of031bb49. The second coordinator waits until delivery commits; marking then succeeds and current hours due become zero. The internal message contains the expected one-hour projection committed before that marking. The affected Dobro suite plus regression passed **19 tests, zero skipped, 4.90 seconds**. A final regression assertion for persisted message content/current-zero state passed **1 test in1.35 seconds**. These overlapping runs are not aggregate counts.

## Other reviewed boundaries: no additional confirmed finding

| Boundary | Concrete reviewed mechanism | Verification boundary |
| --- | --- | --- |
| Telegram binding | `telegram_service.py` purpose-specific hash lookup; exact issuing session/user/foundation; current verified email; expiry/revoke/consumption checks; private non-bot same-ID sender/chat; identity advisory lock; active unique indexes; receipt stores token ID, not bearer | Existing dedicated-PG cases at0badab6 cover different purpose, rotated session, revoked session/user proof, duplicate callbacks, identity conflict and replay. Source unchanged through161402d. No real bot configured/called. |
| Operational rules | `rule_router.py` refreshes authorization before reading/receipt replay; current source permission plus followup scope; worker owner authorization lock; version and scheduled-time fence; missing attendance/contact remains unknown | All eight dedicated-PG cases passed in the previous focused gate. Source unchanged through161402d. No whole-repository concurrency claim. |
| Recording review/publication | Owner/current grant checks precede receipt replay; exact render/content hashes, latest review, take generation/privacy and ready asset checked; opaque claim is bound to the active database transaction and retained row locks before learning publication | Existing independent live→review→publication contract and focused recording tests remain the prior evidence. Relevant source unchanged through161402d. No new native capture or production media action. |
| Completed capture recovery | Captured terminal replay repairs only queue receipt/owned checkpoint cleanup; reusable completed-source encoding passes `checked_take` before and after encoding; current session/grants/privacy/studio generation and queue fence rechecked | Existing durability/checkpoint tests passed at0badab6. This audit adds source review, not a new long-duration/runtime proof. |

The earlier full219 and focused61/25 gates remain separately pinned in their evidence files. This bounded audit is not an exhaustive security scan. Prefix-specific immutable QA and deployment acceptance are separate forthcoming gates. Container sandbox acceptance, twenty-minute capacity and production behavior are not inferred from these local tests.

An initial test collection failed with local ENOSPC before any test executed. Only the agent-owned regenerable Python bytecode cache was removed; the reproduction then ran normally. No other agent's material was deleted.
