# Frontend mount

Default local mount is `/`. To build and serve the application below the existing
OD site, set `VITE_APP_BASE_PATH=/deti-marii` at **build time** and use the ordinary
web build script (including `sync-studio-assets.mjs`). The value accepts only strict
origin-local path segments; it is never an origin, CDN URL or redirect target.

Vite's public base and React Router basename use that one value. Existing Link /
Navigate routes remain logical application paths. The sole API transport qualifies
both logical API paths and legacy `/api/v1/...` paths exactly once. Direct native
media, private photos, files, slide images and local board chunks/fonts use the
same mount. Signed external provider URLs, blob URLs and data URLs stay unchanged.

The gateway must serve the frontend at `/deti-marii/`, preserve the mount on SPA
refresh/deep links, and strip it only when forwarding to the API/RTC upstream.
The API independently trusts `OPORA_APP_MOUNT_PREFIX=/deti-marii` and emits public
URLs/cookie paths from that setting. API, board and LiveKit grant authorizers remain
server-owned; a frontend base setting does not grant access.

The private document is exactly `/deti-marii/recorder.html`; it retains no ordinary
application cookie bootstrap, URL ticket, analytics or controls. Its purpose API
and assets are under `/deti-marii/api/v1/recording-renderer/`. The orchestrator's
separate exact-origin/path allowlist must match; the client does not widen it.

The pinned board SDK's local webpack assets are generated at
`studio-board-assets/excalidraw-assets/`; its embedded-font export alias is generated
at `studio-board-assets/dist/excalidraw-assets/`. Both stay inside the configured
mount, with no public CDN fallback. Generated copies are ignored by Git.

Unit checks cover default and mounted API/media resolution, SPA deep-link/login
return behavior and isolated purpose transport. Release verification must also
exercise actual gateway refreshes, native asset ranges and real provider/board
connections at the deployed public URL.
