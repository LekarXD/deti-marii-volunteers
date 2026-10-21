# Trusted private-prefix API gate — 2026-10-22

Immutable integration source `3a1a2cf7a5d2e549184d0774cc514777f8f88224`, extracted by `git archive`; 415 files, manifest SHA256 `e29b6d79bff207d45a5461b1d59a13f9cf0337374ce5395d96593acceb3198d8`. The independently added private-byte contract ran from the QA worktree against that frozen API source. Frontend working-tree changes were excluded.

**42 passed, zero skipped, 10.97 seconds**, with `infra.pytest_gate` and the API pytest configuration:

- `apps/api/tests/test_mount_prefix.py` (all12 cases).
- `apps/api/tests/test_platform.py`.
- `apps/api/tests/test_contact_change.py`.
- `apps/api/app/modules/applications/tests` (application/claim identity).
- `apps/api/tests/test_recording_capture.py`.
- `tests/contract/test_worker_manifest.py` (job declarations/owners, provider defaults and lazy notice imports).
- New `tests/contract/test_prefixed_private_asset.py`.

The added contract uses a trusted strip-proxy ASGI harness with the ordinary authentication/CSRF and private asset routes. It generates a tiny synthetic PNG, uploads actual bytes using the server-returned prefixed URL, completes validation, reads identical bytes as owner, denies a stranger with404, and verifies logout removes only the `/deti-marii` session cookie and denies old private access with401. A forged `X-Forwarded-Prefix` cannot change returned upload paths. No principal override was added.

The mounted-prefix tests additionally check secure/HttpOnly cookie scope, exact allowed Origin, mount shape rejection, exact recorder entry, and dedicated same-origin RTC provider path. Other tests retain their normal defaults and verify existing root-mode behavior after the prefix changes.

`node apps/api/scripts/recording_boundary_contract.cjs` independently passed under Node26.0.0: exact prefixed recorder entry; ordinary API/other-app HTTP denied; static assets allowed only under the prefix; WebSocket provider path bounded. This script uses protocol doubles and is not a fresh native Chrome capture or media-image acceptance proof.

All database operations used the agent-owned disposable cluster127.0.0.1:56148 and fictitious fixtures. No live gateway, deployed private host, external provider, actual Telegram callback, device or outbound message was used. Source hashes were verified unchanged after the run.

The deployment overlay must still pass the trusted mount prefix, actual Origin and secure-cookie settings consistently to API/media. Local base Compose defaults alone do not establish that deployment behavior. Frontend base/bundle behavior and remote deployment acceptance are separate gates owned by their respective agents. Counts here do not replace or combine the earlier full219 and other focused runs into a latest full-suite claim.
