#!/usr/bin/env python3
"""Explicitly rebuild only disposable fixture schemas on the assigned QA cluster."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

import psycopg

DATABASES = (
    "opora_qa_test", "opora_domain_test", "opora_learning_test",
    "opora_participants_test", "opora_candidates_test", "opora_crm_test",
    "opora_knowledge_test", "opora_studio_test", "opora_profile_test",
    "opora_simulator_test",
    "opora_reporting_test",
    "opora_admin_test",
)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--reset-disposable-test-schemas", action="store_true", required=True)
parser.add_argument("--api-source", type=Path, default=Path(__file__).resolve().parents[2] / "apps/api")
args = parser.parse_args()
api_dir = args.api_source.resolve(strict=True)
if not (api_dir / "alembic.ini").is_file():
    parser.error("API source must contain alembic.ini")
for name in DATABASES:
    # Both endpoint and database names are fixed; no input can target proof DBs.
    with psycopg.connect(f"postgresql://iliapetri@127.0.0.1:56148/{name}", autocommit=True) as db:
        if db.execute("SHOW data_directory").fetchone()[0] != "/private/tmp/opora-qa-pg-data":
            raise SystemExit("Refusing a different PostgreSQL cluster")
        if db.execute("SELECT current_database()").fetchone()[0] != name:
            raise SystemExit("Refusing a different database")
        db.execute("DROP SCHEMA public CASCADE")
        db.execute("CREATE SCHEMA public")
    env = dict(os.environ, OPORA_DATABASE_URL=f"postgresql+psycopg://iliapetri@127.0.0.1:56148/{name}")
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=api_dir, env=env, check=True)
    print(f"Rebuilt disposable fixture schema: {name}", flush=True)
