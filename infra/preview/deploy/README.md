# Preview auto-deploy

Every push to `main` goes live at https://www.odschool.ru/deti-marii/ through
`.github/workflows/deploy-preview.yml`. The workflow skips a commit that is already
contained in the live release and a commit that changes nothing listed in
`../build-context-paths.txt`. Otherwise it builds the web app for `/deti-marii`, bundles
`git archive` of the build-context paths with `apps/web/dist`, and pipes the bundle to
the preview host over SSH.

The CI key on the host (`root`, `/root/.ssh/authorized_keys`) is restricted to
`restrict,command="/usr/bin/python3 /opt/odschool/opora-preview/bin/opora_deploy.py"`:
it can only run this deploy for one commit. Repository secrets: `PREVIEW_DEPLOY_KEY`
(private key) and `PREVIEW_KNOWN_HOSTS` (the host's pinned key).

## What the host script does

`opora_deploy.py` (installed in `/opt/odschool/opora-preview/bin/` together with the two
Dockerfiles here; pushes never update the installed copy):

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

Logs and `rollout.json` for each commit: `/opt/odschool/opora-preview/evidence/<sha>/`.

## When the deploy refuses

- **Dependency input changed**: build full images by hand from the release source
  (`infra/docker/*.Dockerfile`, web with `--build-arg VITE_APP_BASE_PATH=/deti-marii`),
  roll them out, then point `private/deploy-bases.json` at that revision.
- **Runtime configuration change** (Compose, gateway, secrets): review and roll out by
  hand as described in `../README.md`; later pushes then deploy automatically again.

## Install or update on the host

```sh
scp infra/preview/deploy/{opora_deploy.py,source-overlay.Dockerfile,web-overlay.Dockerfile} \
  root@5.42.116.162:/opt/odschool/opora-preview/bin/
```

Re-run by hand for one commit: `opora_deploy.py <sha> < bundle.tgz` on the host.
