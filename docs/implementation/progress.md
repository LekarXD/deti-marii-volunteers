# Реализация

Reference commit: `7d07222`, 43 boards plus Event.html. Branch `codex/implementation`. Historical reference-snapshot.json preserved; active-reference.json records this accepted commit.

| Package | State | Owner | Evidence |
|---|---|---|---|
| P00 | in progress | A0 | contract v1, workspace and reference hashes |
| P01 | queued | A1 | API/DB/auth/worker foundation |
| P02 | queued | A2 | Opora UI foundation |
| QA | queued | A8 | independent PostgreSQL/API/browser acceptance |

No production deployment authorized. Implementation branches/worktrees are isolated from ongoing prototype changes. P00 development assumptions: no age minimum; certificate recommended unless role policy configured; long-read canonical onboarding with card/list variants preserved for product review; staff TOTP with single-use recovery; verified email challenge for returning volunteer, bounded registration session for initial form; dev mail inbox only until real provider connected; participant fixture fields only and default deny for unassigned volunteers. Prelaunch decisions remain tracked in the main plan.
