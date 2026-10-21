# Opora API foundation

Python 3.12, PostgreSQL 16 only. Install `pip install -r requirements.lock`; run from this folder with `OPORA_DATABASE_URL=postgresql+psycopg://...`.

```
python -m alembic upgrade head
python -m app.cli fixtures g1 --json
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
python -m app.worker.main
python -m pytest
```

The root integrator owns `app.main`. Call `install_platform(app)` and include auth/staff/assets/domain routers. Health: `/health`, `/ready`, `/version.json`. `OPORA_RELEASE` records the build. Development cookies intentionally permit loopback HTTP. Production fails startup unless Secure cookies, a configured secret and disabled dev inbox are set. Configure exact trusted origins with `OPORA_TRUSTED_ORIGINS` JSON.

Fixtures contain invented identities and print a TOTP bootstrap secret once. Save that local output securely; it is not an HTTP login shortcut. `python -m app.cli dev-inbox --email coordinator@example.test` reads encrypted development messages. No external delivery is claimed: worker marks `dev_inbox` locally; unconfigured external delivery retries then dead-letters. Never enable dev inbox outside development.

Auth flow: GET `/api/v1/auth/session`; use returned CSRF token with exact Origin for POST `/auth/challenges` `{email,purpose:"login"}`; read actual development challenge; POST `/auth/challenges/verify` `{challenge_id,token}`. This rotates identity and cookie. Staff then POST `/auth/mfa/verify` `{code}` and receive another rotated session. Email possession never supplies staff assurance. Permission checks query current DB grants. Revokes become effective for authorizations after commit. Scoped grants require a resource-specific domain check. Technical admin has no implicit private notes permission.

Domain extension protocol: subclass `Base`, import `get_db` and `Principal`; all writes use one session and commit before reporting success. `authz_guard` precedes sensitive mutations; recheck permission after it. `begin_command`/`finish_command` protect actor/operation/key/payload; authorize before replay. Call `audit` and enqueue helpers in the same transaction. A domain service may export `claim_registration(db,registration_id,user_id)`, invoked only after atomic email verification; conflicts roll back the whole verification. Model discovery lists five modules in `core/model_loader.py`. Domain owners submit exact models/constraints to the sole Alembic writer; no competing migration branches. Migrations contain static DDL, not runtime `create_all`.

Worker claim uses `FOR UPDATE SKIP LOCKED`, expiry, claim token and fenced completion/heartbeat. Jobs survive restart and stale workers cannot complete newer leases. Unknown handlers are unavailable, never noop success. CPU/media handlers are future dedicated workers.

Assets use private local development storage, acknowledged chunks, digest/type/size validation, full image decoding, owner authorization and an optional domain permission after attachment. PNG/JPEG/PDF supported initially. Uploads are capped, PDFs are attachment downloads, no external malware scanner or production S3 adapter is represented as configured.

Reuse provenance (patterns adapted, no production access): curator-bot commit `38c92cd49b1b6c229ed473de991479ed261e4052`, `backend/routers/web_tasks/receipts.py` (canonical actor-bound hash), `backend/db/email_verification_tokens.py` (hashed one-time challenge and encrypted outbox), `backend/services/grader_ledger/durable_lease.py` (lease loss/fencing). New SQLAlchemy/PostgreSQL implementations replace Supabase and cookie sessions replace JWT. Regression tests cover concurrent receipt replay, altered payload, one-use challenge, CSRF, MFA, dynamic ACL revoke and stale lease completion. Source tests were read as references; only Opora tests establish guarantees here.
