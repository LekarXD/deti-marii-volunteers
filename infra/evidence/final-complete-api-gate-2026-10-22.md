# Final complete API gate and explicit release delta — 2026-10-22

## Complete immutable API/backend gate

Source: `3c439e5514ebad3ed1f64073d9b5b0267195cda1`, extracted from the commit with `git archive`, excluding later edits. **293 passed, zero skipped, 175.79 seconds**. The only five warnings are existing PyMuPDF SWIG deprecation warnings in the real PDF conversion test.

The complete command, with all explicit canonical fixture URLs, was:

```sh
python -m pytest -p infra.pytest_gate -c apps/api/pyproject.toml \
  apps/api tests/contract --ignore=apps/api/app/integrations/rtc/sidecar \
  -q --tb=short
```

This includes all API domains, the three guarded stage-demo cases, current application/claim/contact authorization, Telegram binding, Signal rules, Dobro/manual transfer/reminders and their independent race regression, live recording/review/learning publication, durable completed-source recovery, dead-job exhaustion reconciliation, actual worker drain/SIGTERM tests, and prefix/private-asset contracts. The board sidecar keeps its separately provisioned protocol/runtime gate.

All sixteen exact disposable fixture schemas on the assigned PostgreSQL cluster were rebuilt **from empty through migration21**, including the separately opted-in loopback `opora_stage` synthetic fixture. `alembic current` returned `c72a9064de18 (head)` and `alembic check` returned **No new upgrade operations detected**. The computed search-document informational warning remained unchanged.

Frozen source:424files. Canonical file-map SHA256: `d0f99d74babf17c6f86d929c05b8701de260a8f83778fac3e1525031f3741018`. Every file hash remained unchanged after the complete run.

## Last capture/runtime and infrastructure delta

Release source: `9d6426ec65be39232761d19ef071e962fae14fd4`.

The API difference from the complete gate is exactly two files: `app/modules/recordings/jobs.py` and its capture regression test. The fix preserves the dedicated media container's `NODE_PATH` in the sanitized browser child environment while continuing to exclude `NODE_OPTIONS`, database credentials and provider secrets. Relevant final infrastructure also adds the derived seccomp policy and requires the preview worker owners to match the base manifest.

**16 passed, zero skipped, 9.36 seconds**, against an immutable release archive plus the new independent Node-resolution contract:

- Eleven capture cases, including queue exhaustion and the sanitized dependency-path regression.
- Three manifest contracts, including preview/base job-owner parity and clean-process notice imports.
- One seccomp contract: pinned upstream profile is unchanged except the exact `chroot` include condition required by Chrome's user namespace; all capabilities remain dropped.
- One independent actual Node child test: the synthetic dependency exists only in a dedicated runtime directory outside the child cwd's ancestry, so checkout/ancestor `node_modules` cannot mask a missing `NODE_PATH`. The child resolves it while injected `NODE_OPTIONS` and a synthetic provider secret remain absent.

The Node fixture verifies child environment/module resolution. It does not claim to execute Playwright or Chrome, encode media or validate a deployed image.

Main fixture remained `c72a9064de18 (head)` and the final `alembic check` was clean. Release archive:432files, canonical file-map SHA256 `23bf862f9477aa253d9732ce0cb5ebac513dcbf81765f9e544ffa581e6b5038a`; all hashes remained unchanged.

These focused checks overlap the full gate and **must not be summed into a new whole-suite count**. The full run is293at3c; the explicit final delta is16at9d. The API tree at3c, infra-onlye202aa9 and the earlier pushed6efe736 was independently identical (`c1923edfd8d728bfac6587a58a198b18112883fc`); the final9d two-file change is separately verified above.

## Environmental first attempt and recovery

The first attempt at the same complete source ended140passed/153setup errors in107.94seconds after PostgreSQL could not extend its WAL temporary file because the host disk was full. Subsequent setup errors came from the owned database's recovery/unavailable state. This was not accepted as a completed product gate.

Only the agent's reproducible old source archives and bytecode cache were removed, retaining the active final source, manifests, native media evidence and logs. The agent's own cluster recovered through normal PostgreSQL redo/checkpoint; no WAL file was manually deleted. Its local startup retention budget was reduced to256MB maximum/32MB minimum with a60-second checkpoint interval. More than1GiB of headroom was restored. All sixteen disposable schemas were then rebuilt from empty again before the successful293-test run; free space and WAL remained stable during that run. No production limit or application behavior was changed to repair the environment.

## Isolation and remaining acceptance boundaries

Every database operation targeted only `127.0.0.1:56148`, verified against `/private/tmp/opora-qa-pg-data`, and exact disposable fixture names. No shared/native-proof56147, production or remote stage database was used. Stage-demo tests use fictitious identities, private0600 operator files and the normal email-challenge/MFA routes; no public development inbox or principal override was introduced.

The ProfilePage merge was independently checked: versus f3509f1, only the `appPath` import and prefixed avatar URL differ; abort/current-identity checks and latest-draft preservation remain intact. Frontend test/build and remote deployment acceptance belong to their separate gates.

This backend evidence does not establish Caddy activation, remote health/browser acceptance, real provider delivery, a native media-image build/sandbox result or twenty-minute recording capacity. Previously documented native capture and copied-byte publication proofs retain their exact separate durations and boundaries.
