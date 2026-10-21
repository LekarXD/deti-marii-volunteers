# Read-only admin audit

Mount `app.modules.admin.router.router`. GET `/api/v1/coord/admin/audit` uses current foundation `staff.manage` after a fresh locked authorization check; no additional permission, models or migration.

Parameters: `limit` 1–100 (default30), opaque `cursor`, exact `command`, aware `from_at` inclusive and `until_at` exclusive. Optional `foundation_id` is only a scope assertion; foreign foundations receive403. Encrypted cursors bind foundation/time/command filters, snapshot time and `(created_at,id)` position. Newer events do not move later pages.

The DTO projects only audit metadata. Actor names join only users in the current foundation; no contacts or change values are queried. Unsafe/non-string changed-field entries are dropped. Raw untrusted actor/request identifiers are limited to UUID metadata; other labels remain generic.

Six real PostgreSQL tests run only against guarded `opora_admin_test`: exact foreign foundation denial, ordinary/no-MFA/revoked/scoped-only denial (including a stale principal), safe fields and foreign actor names, equal-timestamp cursor stability/filter binding and invalid inputs.
