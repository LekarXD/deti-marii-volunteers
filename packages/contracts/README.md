# Integration contract v1 — P00

Reference: 7d07222. Stack: React 18.3/TypeScript, FastAPI/Python 3.12, SQLAlchemy 2 async + psycopg3, PostgreSQL 16, Alembic. One API service and worker. Runtime defaults bind loopback. Root dependencies/lockfile and route wiring belong to A0. Backend dependency manifest/core imports belong to A1; feature agents report additions rather than independently editing dependencies/migrations.

## Backend extension points (A1 implements first)

- `app.main:app`, `app.main:create_app` export FastAPI; app factory accepts no required arguments; settings via env `OPORA_*`.
- `app.core.db:Base`, `get_db` (FastAPI async dependency yields `AsyncSession`), `SessionLocal`. Reads may autobegin; commands **commit before returning success**; errors roll back. Do not nest `session.begin()` after auth reads. Router must await commit after service command/receipt/outbox writes.
- `app.core.auth:Principal`, `get_principal`, `require_permission(name)` (dependency factory). Principal fields: `user_id: UUID|None`, `registration_id: UUID|None`, `foundation_id: UUID`, `session_id: UUID`, `is_staff: bool`, `actor_id: str`. One owner axis per session. Permissions read fresh from DB; staff membership never inferred from an email suffix or UI role switch.
- `app.core.models:User`, `RegistrationSession`, `Foundation`, `StaffMembership`, `PermissionGrant` (exact import names). A1 owns these foundational identity models and Alembic only. Domain agents own their SQLAlchemy models and submit schema delta to A1.
- `app.core.errors:ApiError(status_code, code, message, field_errors=None, current_version=None, retryable=False)`; JSON `{code,message,field_errors,current_version,retryable,request_id}`.
- `app.core.idempotency` and audit/outbox helpers are finalized by A1 before command integration. Idempotency includes actor+operation+key+payload hash; client retries cannot cross identities.
- `GET /api/v1/auth/session` creates limited registration session if absent; returns `{user_id,registration_id,foundation_id,is_staff,permissions,csrf_token}`; no data of an existing user revealed by matching contact strings.
- same-origin cookie `opora_session`; CSRF header `X-CSRF-Token`, exact trusted Origin for unsafe browser commands. Session endpoint may initialize scoped session as explicit documented bootstrap exception; no login-link consume on GET.
- local development staff bootstrap is CLI seed only with fixture email and printed one-time secret, never public role-switch/password endpoint. Auth assurance/MFA remains server-side.

Feature modules export FastAPI `router` in `app.modules.<module>.router`. Model discovery/migrations and main router registration are integrated by A0/A1 only. SQL UUIDs, UTC timestamps, `Europe/Moscow` presentation timezone. All P01/P03/P04/P06 paths from docs/implementation/api-and-frontend.md. No independent competing app entry or DB/session.

## Frontend extension points (A2 implements first)

- `src/api/transport.ts`: `api<T>(path, options?)`, `ApiError`, `initializeSession()`. Path starts `/api/v1` or is prefixed uniformly; generated SDK delegates to this sole transport. Session bootstrap, csrf, bounded errors, abort/principal boundaries owned by A2.
- one QueryClient and canonical query-key factory; domain components never create their own cache or fetch wrapper.
- `src/ui/index.ts` exports controls and tokens; A2 supplies a usage README/API. Candidate + coordinator layouts have top nav and logo aligned. No sidebar or native select/date/time popups. Fonts/SVG/colors/spacing derive from the actual prototype.
- Feature page exports in `src/features/<module>/index.ts`; A0 alone edits `src/app/router.tsx` and root manifests.
- Data hooks use generated `src/api/generated/schema.ts` via shared transport; do not maintain copies of server DTOs after OpenAPI generation.

## Independent states and safety

Application review, introduction progress and interview booking are independent. Booking requires a valid scoped session/contact policy, not a finished test. No hardcoded age minimum, three-month pledge or mandatory blanket certificate. Role requirements are coordinator-configurable. `required/invited/confirmed` counts distinct. Never persist raw auth tokens in localStorage. Private participant notes and interview notes absent from self JSON.

Role definitions are tasks, not staff permissions. Everything stays scoped to one foundation plus optional program/group grants; fixtures contain invented people. External delivery, AI and RTC report unavailable until configured; no success toast for a noop.
