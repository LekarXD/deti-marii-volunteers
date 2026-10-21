# Opora board sidecar

Dedicated environment/process; never install this requirements file into the FastAPI API environment. The CRDT hub, binary Yjs channel filtering, SQLite store and log redaction are ported from pinned OD source `38c92cd49b1b6c229ed473de991479ed261e4052`. Opora supplies its own namespace and resource authentication; no school identity or storage namespace is reused.

Run `PYTHONPATH=apps/api python -m app.integrations.rtc.sidecar --port <dedicated port>` in an environment built from this directory's `requirements.txt`. Configure `OPORA_RTC_BOARD_SECRET` (at least 32 characters), `OPORA_RTC_BOARD_AUTH_URL` (the private API `/api/v1/studio-board/authorize` endpoint), and `OPORA_RTC_BOARD_DATA_DIR`. The API uses the same signing secret plus browser-facing `OPORA_RTC_BOARD_URL`. TLS/proxy and deployment/retention choices remain integration-owner configuration.

The sidecar verifies issuer/audience/expiry/room/resource claims before joining. It calls current API authorization before accepting and every 10 seconds thereafter; unavailable authorization fails closed. Permission changes/expired tokens close the socket, and the browser obtains a fresh scoped grant. A viewer's raw Yjs sync-update/step2 messages are rejected server side. Input sizes, malformed varints, awareness rates, room/client counts and idle time are bounded. Writer backpressure coalesces into bounded current-document snapshots instead of retaining an unbounded update queue.

Secrets in y-websocket's mandatory token query are redacted from Uvicorn handshake logs as well as normal access logs. Access logging is disabled by the entrypoint. No raw JWT is saved in localStorage.

The transport tests use actual local WebSocket/Yjs clients and SQLite restart persistence; the authorization HTTP adapter is controlled. Separate API PostgreSQL tests prove that already-issued board tokens fail authorization after auth-session revocation. Continuous board capture/replay is not claimed: P18A preview can mount an approved read-only board into the canonical content rect, while capture remains gated on an explicit signed board projection/clock/manifest or approved immutable snapshots.
