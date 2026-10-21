#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
python3 scripts/export_openapi.py
pnpm exec openapi-typescript packages/contracts/openapi.json -o apps/web/src/api/generated/schema.ts
git diff --exit-code -- packages/contracts/openapi.json apps/web/src/api/generated/schema.ts
