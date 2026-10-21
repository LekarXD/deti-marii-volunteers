#!/bin/sh
# Dedicated disposable localhost PostgreSQL only. Requires migrated, fresh G1 DB.
set -eu
cd "$(dirname "$0")/../.."
: "${OPORA_DATABASE_URL:?set the disposable G1 PostgreSQL URL}"
export PYTHONPATH="$PWD/apps/api${PYTHONPATH:+:$PYTHONPATH}"
export OPORA_G1_BASE_URL="${OPORA_G1_BASE_URL:-http://127.0.0.1:8001}"
export OPORA_G1_ORIGIN="${OPORA_G1_ORIGIN:-http://127.0.0.1:5174}"
export OPORA_TRUSTED_ORIGINS='["http://127.0.0.1:5174","http://localhost:5174","http://testserver"]'
export OPORA_G1_FIXTURE_FILE="${OPORA_G1_FIXTURE_FILE:-$(mktemp /tmp/opora-g1-fixture.XXXXXX)}"
fixture_created=0
api_pid=''
cleanup() {
  if [ -n "$api_pid" ]; then kill "$api_pid" 2>/dev/null || true; wait "$api_pid" 2>/dev/null || true; fi
  if [ "$fixture_created" = 1 ]; then rm -f "$OPORA_G1_FIXTURE_FILE"; fi
}
trap cleanup EXIT HUP INT TERM
if [ ! -s "$OPORA_G1_FIXTURE_FILE" ]; then
  umask 077
  (cd apps/api && python3 -m app.cli fixtures g1 --json) > "$OPORA_G1_FIXTURE_FILE"
  chmod 600 "$OPORA_G1_FIXTURE_FILE"
  fixture_created=1
fi
python3 -c 'import json,os; d=json.load(open(os.environ["OPORA_G1_FIXTURE_FILE"])); assert d["identities"]["coordinator@example.test"].get("totp_secret"), "Fresh G1 DB or original private fixture required"'
api_port=$(python3 -c 'import os,urllib.parse; print(urllib.parse.urlparse(os.environ["OPORA_G1_BASE_URL"]).port or 8001)')
(cd apps/api && exec python3 -m uvicorn app.main:app --host 127.0.0.1 --port "$api_port" --no-access-log) > /tmp/opora-g1-api.log 2>&1 &
api_pid=$!
python3 - <<'PY'
import os,time,urllib.request
for _ in range(100):
    try:
        with urllib.request.urlopen(os.environ['OPORA_G1_BASE_URL']+'/ready',timeout=1) as result:
            if result.status == 200:
                break
    except OSError:
        time.sleep(.1)
else:
    raise SystemExit('G1 API readiness failed; inspect /tmp/opora-g1-api.log locally')
PY
kill -0 "$api_pid" 2>/dev/null || { echo "The G1 API process exited before acceptance; inspect /tmp/opora-g1-api.log" >&2; exit 1; }
python3 -m pytest -c apps/api/pyproject.toml tests/e2e -q
