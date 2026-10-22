# Preview auto-deploy

Every new commit on `main` goes live at https://www.odschool.ru/deti-marii/ without CI.
On the preview host the `opora-preview-autodeploy.timer` runs `opora_autodeploy.py`
once a minute:

1. Fetches `main` into `/opt/odschool/opora-preview/autodeploy/repo.git` over a
   read-only GitHub deploy key (`private/github-deploy-key`, GitHub host keys pinned in
   `private/github-known-hosts`).
2. Does nothing when the live release already contains `main`, or when no path from
   `../build-context-paths.txt` changed since the live release.
3. Builds the web app for `/deti-marii` in `opora-preview/web-builder` (Node 26,
   pnpm 11.3; uid 10001, no capabilities, 2 GiB memory, 1.5 CPU) from `git archive`
   of the build-context paths, then removes the dependencies again.
4. Pipes `source/` plus `dist/` to `opora_deploy.py <sha>`.

A failed commit is not retried until `main` moves. A busy release lock, another Compose
rollout or low resources (exit code 75) only postpone the deploy to the next minute.

## What opora_deploy.py does

1. Takes the preview's own release lock and checks the running state the same way the
   earlier guarded rollouts did (capture off, Compose files inside the preview directory,
   `runtime.env` release equal to the running API).
2. Requires 6 GiB free disk and 1 GiB available memory (`../README.md`).
3. Builds `api` and `media` as overlays of fixed full-build bases from
   `private/deploy-bases.json`, `web` as the base Nginx image with the new `dist`, and
   `board` from `board.Dockerfile`. Images therefore do not grow with each release.
   The overlay is refused when a dependency input of a base build changed
   (`requirements.lock`, `pyproject.toml`, `alembic.ini`, the API/media/web Dockerfiles,
   media package files, `infra/docker/nginx.conf`).
4. Under the shared `/var/lock/odschool-deploy.lock`, verifies that the rendered Compose
   configuration differs only in image tags and release variables, rewrites only the
   `OPORA_RELEASE` line of `runtime.env`, and runs `docker compose up -d` (migrations run
   through the `migrate` service).
5. Waits for healthy services and checks `/deti-marii/`, `/ready` and `/version.json`.
   Any failure restores the previous `runtime.env` and Compose files and brings the
   previous release back. Ertad and OD routes are recorded, never touched.
6. Keeps the new release, its predecessor, the base builds and the Compose working
   directory; removes this preview's older image tags and source trees only.

## Where to look

- `journalctl -u opora-preview-autodeploy` — one line per decision.
- `autodeploy/state.json` — last `main` seen and the result.
- `evidence/<sha>/` — web build log, image build logs, `deploy.log`, `rollout.json`.

## When a deploy is refused

- **Dependency input changed**: build full images by hand from the release source
  (`infra/docker/*.Dockerfile`, web with `--build-arg VITE_APP_BASE_PATH=/deti-marii`),
  roll them out, then point `private/deploy-bases.json` at that revision.
- **Runtime configuration change** (Compose, gateway, secrets): review and roll out by
  hand as described in `../README.md`; later commits then deploy automatically again.
- **Retry the same commit**: delete `autodeploy/state.json`.

## Install or update on the host

The installed copies are not updated by pushes; copy them after a reviewed change:

```sh
scp infra/preview/deploy/{opora_deploy.py,opora_autodeploy.py,source-overlay.Dockerfile,web-overlay.Dockerfile,web-builder.Dockerfile} \
  root@5.42.116.162:/opt/odschool/opora-preview/bin/
scp infra/preview/deploy/opora-preview-autodeploy.{service,timer} root@5.42.116.162:/etc/systemd/system/
ssh root@5.42.116.162 'systemctl daemon-reload && systemctl enable --now opora-preview-autodeploy.timer'
```

Pause: `systemctl stop opora-preview-autodeploy.timer`.
