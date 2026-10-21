# Dedicated media image build: host execution gap

Immutable source: **`a51d7bfe1fb5e0e016c047c6f24a8ab3700d07d8`**, frozen with
`git archive` from the integration checkout. Only `apps/api`,
`packages/studio-core` and `infra/docker` entered the context. There were315 files;
the sorted path/SHA256 manifest hash was
`50bde83fde42b1be8602750f4b6f13bc6ea35797a02ec9c95fcda5b5d24c34ea`.
The builder received3.902MB. No private assets, credentials, session files,
browser profiles, local databases or workspace dependencies were supplied.

The existing daemon readout was Docker **29.5.2 / linux/aarch64**. Buildx was not
installed, so the bounded build used the available legacy builder:

```sh
DOCKER_BUILDKIT=0 docker build --platform linux/amd64 -f infra/docker/media.Dockerfile -t opora-qa-media:a51d7bf .
```

The official `mcr.microsoft.com/playwright:v1.58.2-noble` pull completed at digest
**`sha256:6446946a1d9fd62d9ae501312a2d76a43ee688542b21622056a372959b65d63d`**.
The first executable build step, before package installation or application
startup, failed with **`exec /bin/sh: exec format error` (exit255)**. The existing
ARM daemon cannot execute the recipe's amd64 image in this environment. The
exact Playwright1.58.2 registry selects Chrome for Testing on Linux x64 and a
non-CfT Chromium build on Linux arm64; see the versioned source in the media runbook.

This is a host execution gap. The final media image was not built; Node/Python
dependency installation, sandbox launch, container Stage capture and MP4 output
were not reached or claimed. Native Stage recording evidence belongs to A1's
separate checkpoint and does not establish container acceptance.

Only this attempt's stopped intermediate container `625eb8d42d8a` and untagged
ENV-only intermediate image `46d40352ceac` were removed. The official base cache
was retained. No Docker context, existing service, network or volume was changed;
no privileged binfmt installation, sandbox bypass or host IPC was attempted.

The next container gate needs an amd64 host or separately provisioned reviewed
emulation. It must execute the recipe, prove nonroot Chromium namespace/seccomp
sandbox and then perform synthetic capture/recovery checks. This attempt is not a
deployment or production result.
