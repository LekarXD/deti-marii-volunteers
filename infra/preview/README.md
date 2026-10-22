# Isolated Timeweb preview

Public mount: `https://www.odschool.ru/deti-marii/`. This contour owns only project
`opora-preview`, `/opt/odschool/opora-preview`, its `opora_stage` database, volumes,
private/egress networks and image tags `opora-preview/*:<full-SHA>`. Only its web
edge joins the existing gateway network under alias `opora-preview-web`.
The existing app projects, databases, assets and secrets are never reused.

Releases are automatic: a timer on the host deploys every new `main` commit within a
few minutes, keeping the guarded checks and rollback described below
([deploy/README.md](deploy/README.md)). The manual procedure below remains for full
image rebuilds and runtime configuration changes the automatic deploy refuses.

Use only a final pushed main commit. Stream `git archive <SHA> <paths from
build-context-paths.txt>` into a fresh `releases/<SHA>` directory; do not archive
reference materials/prototypes or use local mutable web output. Build API, web,
board and media from that exact directory with OCI revision labels. The web build
requires `--build-arg VITE_APP_BASE_PATH=/deti-marii`. Record image IDs/digests and
`source_revision`, source path list/hash, Alembic head and live `/version.json`.
An environment label alone is not source evidence.

For a source-only API/media update on the space-constrained preview host,
`runtime-source-overlay.Dockerfile` may reuse the currently deployed exact-SHA
image. First verify its OCI revision and prove that `requirements.lock`,
`pyproject.toml`, the original API/media Dockerfiles and media package lock files
are unchanged between that revision and the new pushed source. Copy the complete
app, migrations and studio-core trees from the new source archive, attach the new
OCI revision, and record both base image ID and resulting image ID. Otherwise use
the original full build. This avoids installing identical dependencies twice.

`compose.yml` is standalone, not an override of the local Compose defaults.
Use the same private `runtime.env` (0600) with `docker compose --env-file ... -f
releases/<SHA>/infra/preview/compose.yml`. Keep `OPORA_STAGE_PRIVATE_DIR` set to
`/opt/odschool/opora-preview/private`. Generate independent encryption, PostgreSQL,
LiveKit and board secrets there; never print the expanded Compose configuration.
Create `private/demo` with UID/GID10001 and mode0700; only API mounts it at
`/run/opora-private`. Other private operator/config files remain root-only.
Seed only invented identities through the guarded `python -m app.stage_demo` CLI;
see `docs/implementation/stage-demo-fixtures.md`. Public dev inbox stays disabled,
normal verification/MFA is required and unconfigured SMTP/AI is not claimed ready.

The API needs both `OPORA_APP_MOUNT_PREFIX=/deti-marii` and Uvicorn
`--root-path /deti-marii`. Gateway strips this outer prefix once. Owned Nginx serves
the prefixed SPA build, forwards `/api` unchanged, strips only the outer `/rtc`
provider mount, and preserves the `/board` sidecar route. RTC/admin origin is
HTTPS; browser RTC is WSS within the same scoped `/deti-marii/rtc` subtree.

The LiveKit private YAML must set `port:7880`, `rtc.tcp_port:18085`,
`rtc.udp_port:18084`, `rtc.node_ip:5.42.116.162`, `rtc.use_external_ip:false` and the
new stage key pair. Only18084/UDP and18085/TCP may be published for public ICE;
verify they remain unused and add only corresponding commented firewall rules.
Do not change existing firewall defaults or existing listeners. Web diagnostics
bind loopback18081; API/PostgreSQL/board have no host ports.

Start base services first, verify current migration head and normal public auth,
then enable only one media worker with `--profile media`. It is capped at2GiB,
1.5CPUs,256PIDs and uses `media-seccomp-sandbox.json`: sandbox stays enabled,
capabilities remain dropped, AppArmor/host sysctls stay unchanged. This lower cap
bounds impact on the shared server; an OOM/slow capture is a failed own-contour
acceptance, not permission to consume existing production capacity. Monitor host
available memory, pressure, own container CPU/RSS/PIDs and disk during builds and
capture. Stop only own tests/workloads if available memory falls below1GiB,
free root disk below6GiB, or sustained host pressure threatens other projects.
Never prune other images/volumes/builders. One disposable named BuildKit builder
may have explicit memory/CPU limits; remove only that owned builder/cache afterward.

## Gateway preservation

The live gateway has a top-level Ertad JSON route absent from its mounted Caddyfile.
Before any change, save complete live JSON, adapted canonical JSON and original
Caddyfile privately. Confirm live-minus-exact-Ertad equals the canonical JSON.
`gateway.caddy` adds only the new own mount and persists identical Ertad semantics.
Build a canonical candidate by inserting this fragment into only the existing
`www.odschool.ru` block. Adapt/validate it inside the running Caddy container.
After removing just these two added path routes and normalizing generated group
identifiers, every other object must match the previous canonical configuration.

Activate by adding only the exact host/path Opora route to the saved LIVE JSON;
removing that one object must reproduce the entire previous live JSON exactly.
Validate that JSON before reload. Persist the reviewed canonical candidate
atomically for future restarts, acquire the existing short gateway/deploy lock,
recheck before-hashes, then reload the full preserved JSON. On validation failure
or concurrent drift, stop; never reload the stale original Caddyfile. Verify both
new application and existing Ertad/OD routes after the atomic reload. No gateway
restart or broad startup-command change is required.
