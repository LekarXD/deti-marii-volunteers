#!/bin/sh
# Build only an immutable Git archive. Does not start/stop any service or migrate.
set -eu
if [ "$#" -lt 1 ]; then echo 'Usage: build-frozen.sh COMMIT [--media] [--check-only]' >&2; exit 2; fi
cd "$(dirname "$0")/../.."
revision=$(git rev-parse --verify "$1^{commit}")
shift
media=false
check_only=false
for option in "$@"; do
  case "$option" in
    --media) media=true ;;
    --check-only) check_only=true ;;
    *) echo 'Unknown build option' >&2; exit 2 ;;
  esac
done
: "${OPORA_ENV_FILE:?absolute path to a private local or staging Compose environment}"
case "$OPORA_ENV_FILE" in /*) ;; *) echo 'OPORA_ENV_FILE must be absolute' >&2; exit 2 ;; esac
[ -f "$OPORA_ENV_FILE" ] || { echo 'Environment file not found' >&2; exit 2; }
if command -v docker-compose >/dev/null 2>&1; then set -- docker-compose
else set -- docker compose; fi
frozen=$(mktemp -d "${TMPDIR:-/tmp}/opora-frozen-build.XXXXXX")
trap 'rm -rf "$frozen"' EXIT HUP INT TERM
git archive --format=tar "$revision" > "$frozen/source.tar"
archive_sha=$(shasum -a 256 "$frozen/source.tar" | cut -d ' ' -f 1)
mkdir "$frozen/source"
tar -xf "$frozen/source.tar" -C "$frozen/source"
export OPORA_RELEASE="$revision"
set -- "$@" --env-file "$OPORA_ENV_FILE" -f "$frozen/source/infra/compose.yaml"
if "$media"; then set -- "$@" -f "$frozen/source/infra/compose.media.yaml" --profile media; fi
"$@" config --quiet
if ! "$check_only"; then
  if "$media"; then
    arch=$(docker info --format '{{.Architecture}}')
    case "$arch" in x86_64|amd64) ;; *) echo 'Media build requires an approved native amd64 Docker host; emulation is not enabled by this script' >&2; exit 2 ;; esac
  fi
  "$@" build
fi
printf '{"source_revision":"%s","archive_sha256":"%s","build_executed":%s,"media":%s}\n' "$revision" "$archive_sha" "$(if "$check_only"; then echo false; else echo true; fi)" "$media"
