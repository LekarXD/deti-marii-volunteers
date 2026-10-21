"""Create/migrate fresh dedicated test DBs; refuse existing DBs and non-local hosts."""
import os
from pathlib import Path
import subprocess
import sys

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

base = make_url(os.environ["OPORA_DATABASE_URL"])
if base.host not in {"127.0.0.1", "localhost", "::1"}:
    raise SystemExit("Only disposable localhost PostgreSQL is accepted")
targets = {
    "OPORA_TEST_DATABASE_URL": "opora_domain_test",
    "OPORA_LEARNING_TEST_DATABASE_URL": "opora_learning_test",
    "OPORA_PARTICIPANTS_TEST_DATABASE_URL": "opora_participants_test",
    "OPORA_CANDIDATES_TEST_DATABASE_URL": "opora_candidates_test",
    "OPORA_CRM_TEST_DATABASE_URL": "opora_crm_test",
    "OPORA_KNOWLEDGE_TEST_DATABASE_URL": "opora_knowledge_test",
    "OPORA_STUDIO_TEST_DATABASE_URL": "opora_studio_test",
    "OPORA_PROFILE_TEST_DATABASE_URL": "opora_profile_test",
    "OPORA_SIMULATOR_TEST_DATABASE_URL": "opora_simulator_test",
}
admin = base.set(drivername="postgresql", database="postgres").render_as_string(hide_password=False)
with psycopg.connect(admin, autocommit=True) as db:
    existing = db.execute("SELECT datname FROM pg_database WHERE datname=ANY(%s)", (list(targets.values()),)).fetchall()
    if existing:
        raise SystemExit("Refusing existing test databases; provision a fresh PostgreSQL instance or use separately managed URLs")
    for name in targets.values():
        db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
root = Path(__file__).resolve().parents[2]
api_dir = Path(os.environ.get("OPORA_TEST_API_DIR", root / "apps/api"))
for variable, name in targets.items():
    env = dict(os.environ, OPORA_DATABASE_URL=base.set(database=name).render_as_string(hide_password=False))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=api_dir, env=env, check=True)
    print(f"Prepared {variable}: {name}")
