# Dedicated private media worker

This opt-in recipe packages the media runtime; it is not a container-build,
sandbox-launch, shared-stage recording, or deployment acceptance result.
The ordinary API and outbox worker retain their existing image. Current capture
must additionally have A1's registered `recording.capture` implementation; the
older kernel deliberately returns unavailable.

## Runtime contract

- `infra/docker/media.Dockerfile` uses the official
  `mcr.microsoft.com/playwright:v1.58.2-noble` image and separately installs the
  exact `playwright@1.58.2` package. The pinned upstream image source uses Node 24;
  the build also asserts Node >=22. Its full Chrome for Testing is selected through
  `chromium.executablePath()`, rather than the separate headless-shell binary.
  The overlay pins `linux/amd64`: the exact Playwright v1.58.2
  [executable registry](https://github.com/microsoft/playwright/blob/v1.58.2/packages/playwright-core/src/server/registry/index.ts)
  selects Chrome for Testing there and a non-CfT Chromium build on Linux arm64.
  On the available aarch64 Docker daemon this requires
  emulation; any resulting smoke must record that fact, and cannot establish
  long-recording throughput or latency acceptance.
- Python 3.12, the API lockfile, ffmpeg/ffprobe and LibreOffice Impress support the
  capture/encode and slide-conversion processes. Canonical `packages/studio-core`
  schemas accompany the API source. The web image must separately copy/build
  `apps/web/recorder.html`, including its canonical Stage assets, as a Vite entry.
- Only `slides.convert` and `recording.capture` are claimed. The default worker
  retains `outbox.deliver`; no media kind is added to its environment.
- UID/GID 10001 matches private-asset ownership in the API image. Assets share the
  existing private volume; the read-only root filesystem has bounded private
  temporary/home mounts, 1GiB shared memory and explicit CPU/memory/PID limits.
- The Dockerfile-specific build-context allowlist includes only API source/locks,
  migrations, canonical schemas and media package files. It excludes credentials,
  local private assets/DBs, browser profiles, dependencies and reference datasets
  before the builder receives the context. Do not replace it with a broad copy.
- Chromium must launch with `chromiumSandbox: true` in the source. The overlay
  uses the official version-pinned seccomp profile to permit user namespaces.
  It never requests privileged mode, SYS_ADMIN, host IPC, a Docker socket,
  `seccomp=unconfined`, or `--no-sandbox`. A kernel refusing user namespaces is a
  failed runtime gate; do not disable sandbox to turn it green.

Source verification: [Playwright Docker guidance](https://playwright.dev/docs/docker),
[v1.58.2 Dockerfile](https://github.com/microsoft/playwright/blob/v1.58.2/utils/docker/Dockerfile.noble),
[browser registry](https://github.com/microsoft/playwright/blob/v1.58.2/packages/playwright-core/browsers.json),
and [seccomp profile](https://github.com/microsoft/playwright/blob/v1.58.2/utils/docker/seccomp_profile.json).
The vendored profile SHA256 is
`cc3e61cabda6bbc1e53e54d27ba4d55a9d3be829b6dd1a596f4a7b31b1cc7849`.
The source tag pins the Playwright browser revision, not every apt package or the
final image digest; record the built image digest and runtime versions at acceptance.

## Prepare and inspect

Use a dedicated local or staging database/asset volume. Never attach production
assets or credentials for this check. Keep the existing `infra/.env` private.

```sh
docker-compose --env-file infra/.env -f infra/compose.yaml -f infra/compose.media.yaml --profile media config --quiet
docker-compose --env-file infra/.env -f infra/compose.yaml -f infra/compose.media.yaml --profile media build media-worker
docker-compose --env-file infra/.env -f infra/compose.yaml -f infra/compose.media.yaml --profile media run --rm --no-deps media-worker sh -c 'id; node --version; node -p "require(\"playwright/package.json\").version"; python --version; /usr/local/bin/opora-capture-chrome --version; ffmpeg -version; ffprobe -version; libreoffice --version'
```

An existing deployment may use `docker compose` when the Compose plugin is
installed. Do not print expanded Compose config with credentials to evidence.
The native syntax check above has passed; Docker was unavailable in this QA run,
so the build and binary checks are instructions awaiting actual execution.

## Enable only after runtime acceptance

The overlay starts with `OPORA_CAPTURE_ENABLED=false`. Configure the actual
trusted private recorder origin as `OPORA_CAPTURE_RENDERER_URL`, with exact
`/recorder.html` and no query/fragment. A non-loopback Compose service name such as
`http://web:8080` is not an allowed development origin: use a trusted HTTPS gateway
reachable from the worker, or a separately reviewed loopback-only local contour.
An arbitrary HTTP hostname must not be added as an exception.

Configure `OPORA_RTC_URL`, `OPORA_RTC_PUBLIC_URL`, `OPORA_RTC_API_KEY` and
`OPORA_RTC_API_SECRET` only for the intended local/staging LiveKit service. Both
browser and worker must reach their configured endpoints. Never put renderer
tickets, access credentials, cookies, or API secrets in recorder URLs, process
arguments, Compose commands, or captured logs. The private Node protocol receives
one-use tickets through stdin; real device APIs remain denied.

After setting `OPORA_CAPTURE_ENABLED=true` in the private environment, start with:

```sh
docker-compose --env-file infra/.env -f infra/compose.yaml -f infra/compose.media.yaml --profile media up -d media-worker
```

Before accepting this image, run an actual synthetic local SharedStage capture
through the normal application flow: exact 1920x1080/DPR1, actual encoded first
chunk, H264/AAC MP4 and audio/visual content, current projection/checksum fences,
revoke/privacy/lease-loss/timeout behavior, private file read denial, and explicit
human review before publication. Record the exact source SHA, image digest,
migration head, safe tool versions, sandbox proof and outcomes. No test here
authorizes real participants, external delivery, retention deletion or production.
