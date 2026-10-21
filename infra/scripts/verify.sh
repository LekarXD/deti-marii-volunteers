#!/bin/sh
# Uses a disposable, already-running PostgreSQL database. Never creates/drops DBs.
set -eu
cd "$(dirname "$0")/../.."
: "${OPORA_DATABASE_URL:?point OPORA_DATABASE_URL at a disposable local or CI PostgreSQL DB}"
case "$OPORA_DATABASE_URL" in postgresql+psycopg://*) ;; *) echo 'A real PostgreSQL database is required' >&2; exit 2 ;; esac
export PYTHONPATH="$PWD/apps/api${PYTHONPATH:+:$PYTHONPATH}"
(
  cd apps/api
  python3 -c 'from alembic.config import Config; from alembic.script import ScriptDirectory; assert len(ScriptDirectory.from_config(Config("alembic.ini")).get_heads()) == 1'
  python3 -m alembic upgrade head
  python3 -m alembic check
)
pnpm typecheck
pnpm build
pnpm test
python3 -m pytest apps/api/tests tests/contract -q
sh infra/scripts/check-openapi.sh
