#!/bin/sh
# Starlette/CRDT versions are intentionally isolated from the FastAPI environment.
set -eu
cd "$(dirname "$0")/../.."
: "${OPORA_SIDECAR_PYTHON:?point to the dedicated sidecar virtualenv Python}"
api_dir="${OPORA_SIDECAR_API_DIR:-$PWD/apps/api}"
export PYTHONPATH="$api_dir:$api_dir/app/integrations/rtc/sidecar/tests:$PWD${PYTHONPATH:+:$PYTHONPATH}"
"$OPORA_SIDECAR_PYTHON" -m pytest -p infra.pytest_no_skips -c "$api_dir/pyproject.toml" "$api_dir/app/integrations/rtc/sidecar/tests" -q
