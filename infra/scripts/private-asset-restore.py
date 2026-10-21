"""Local P20 drill: real private upload + DB/files restore + fresh ACL checks.

Creates new DBs/directories only. All credentials and dumps remain mode 0600 in
an isolated /private/tmp/opora-qa-restore-assets run directory. No default asset
root, Docker, production, existing DB restore, or role-switch endpoint is used.
"""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx
from PIL import Image, ImageDraw
import psycopg
from psycopg import sql
import pyotp
from sqlalchemy.engine import make_url


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run(command, *, cwd=None, env=None):
    process = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    if process.returncode:
        # Commands contain local paths/DB names, never auth or encryption tokens.
        raise RuntimeError(f"Local command failed ({process.returncode}): {command[0]} {process.stderr[-1000:]}")
    return process.stdout


def tree_manifest(root):
    return {str(path.relative_to(root)): {"size": path.stat().st_size, "sha256": digest(path.read_bytes())}
            for path in sorted(root.rglob("*")) if path.is_file()}


def table_snapshot(dsn):
    with psycopg.connect(dsn) as db:
        tables = [row[0] for row in db.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
        return {"head": db.execute("SELECT version_num FROM alembic_version").fetchone()[0],
                "counts": {name: db.execute(sql.SQL("SELECT count(*) FROM {}").format(sql.Identifier("public", name))).fetchone()[0] for name in tables}}


class HttpSession:
    def __init__(self, base, cookies=None):
        self.http = httpx.Client(base_url=base, cookies=cookies, timeout=20)
        response = self.http.get("/api/v1/auth/session")
        assert response.status_code == 200, "Session bootstrap failed"
        self.session = response.json()

    def command(self, method, path, body=None, *, data=None):
        headers = {"Origin": "http://127.0.0.1:5174", "X-CSRF-Token": self.session["csrf_token"], "Idempotency-Key": str(uuid4())}
        if data is not None:
            headers.update({"X-Upload-Offset": "0", "Content-Type": "application/octet-stream"})
            response = self.http.request(method, path, content=data, headers=headers)
        else:
            response = self.http.request(method, path, json=body, headers=headers)
        assert response.status_code in (200, 201), f"{method} {path}: {response.status_code}"
        return response.json()

    def login(self, email, api, env, totp_secret=None):
        challenge = self.command("POST", "/api/v1/auth/challenges", {"email": email, "purpose": "login"})
        inbox = json.loads(run([sys.executable, "-m", "app.cli", "dev-inbox", "--email", email], cwd=api, env=env))
        token = next(row["token"] for row in inbox if row["challenge_id"] == challenge["challenge_id"])
        self.session = self.command("POST", "/api/v1/auth/challenges/verify", {"challenge_id": challenge["challenge_id"], "token": token})
        if totp_secret:
            self.session = self.command("POST", "/api/v1/auth/mfa/verify", {"code": pyotp.TOTP(totp_secret).now()})
            assert self.session["is_staff"] is True
        else:
            assert self.session["is_staff"] is False

    def image(self, path, checksum):
        response = self.http.get(path)
        assert response.status_code == 200, f"Authorized image unavailable: {path}: {response.status_code}"
        assert response.headers["content-type"].startswith("image/png")
        assert "no-store" in response.headers.get("cache-control", "")
        assert digest(response.content) == checksum, "Authorized image checksum differs"
        return len(response.content)

    def denied(self, path):
        response = self.http.get(path)
        assert response.status_code in (403, 404), f"Private asset disclosed: {path}: {response.status_code}"
        assert not response.headers.get("content-type", "").startswith("image/")
        return response.status_code

    def close(self):
        self.http.close()


def start_api(api, env, port, log):
    with socket.socket() as probe:
        assert probe.connect_ex(("127.0.0.1", port)) != 0, f"Refusing occupied local port {port}"
    handle = log.open("w")
    process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port), "--no-access-log"], cwd=api, env=env, stdout=handle, stderr=subprocess.STDOUT)
    handle.close()
    base = f"http://127.0.0.1:{port}"
    until = time.monotonic() + 15
    while time.monotonic() < until:
        if process.poll() is not None:
            raise RuntimeError(f"QA API startup failed; inspect private {log}")
        try:
            if httpx.get(base + "/ready", timeout=1).status_code == 200:
                version = httpx.get(base + "/version.json", timeout=1)
                if version.status_code != 200 or version.json().get("release") != env["OPORA_RELEASE"]:
                    process.terminate()
                    process.wait(timeout=10)
                    raise RuntimeError("Runtime release readback differs")
                return process, base
        except httpx.TransportError:
            pass
        time.sleep(.1)
    process.terminate()
    process.wait(timeout=10)
    raise RuntimeError("QA API readiness timed out")


def stop_api(process):
    if process is not None and process.poll() is None:
        process.terminate()
        process.wait(timeout=10)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-source", required=True, type=Path)
    parser.add_argument("--postgres-url", default="postgresql://iliapetri@127.0.0.1:56148/postgres")
    parser.add_argument("--pg-bin", type=Path, default=Path("/opt/homebrew/opt/postgresql@16/bin"))
    parser.add_argument("--source-port", type=int, default=8002)
    parser.add_argument("--restore-port", type=int, default=8003)
    args = parser.parse_args()
    os.umask(0o077)
    url = make_url(args.postgres_url)
    assert url.host == "127.0.0.1" and url.port == 56148, "Only the assigned isolated QA PostgreSQL is allowed"
    with psycopg.connect(args.postgres_url, autocommit=True) as admin:
        assert admin.execute("SHOW data_directory").fetchone()[0] == "/private/tmp/opora-qa-pg-data", "Refusing another cluster"
    tag = uuid4().hex[:10]
    workspace = Path("/private/tmp/opora-qa-restore-assets") / tag
    workspace.mkdir(parents=True, mode=0o700)
    original_api = args.api_source.resolve()
    repository = original_api.parents[1]
    source_sha = run(["git", "rev-parse", "HEAD"], cwd=repository).strip()
    source_dirty = bool(run(["git", "status", "--porcelain", "--", "apps/api"], cwd=repository).strip())
    api = workspace / "source" / "apps" / "api"
    shutil.copytree(original_api, api, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".env", ".env.*", "*.pyc"))
    source_manifest = tree_manifest(api)
    (workspace / "api-source-manifest.json").write_text(json.dumps(source_manifest, indent=2, sort_keys=True))
    source_tree = digest(json.dumps(source_manifest, sort_keys=True, separators=(",", ":")).encode())
    source_assets, restored_assets = workspace / "source-assets", workspace / "restored-assets"
    source_assets.mkdir(mode=0o700)
    source_name, restored_name = f"opora_qa_assets_{tag}_source", f"opora_qa_assets_{tag}_restore"
    with psycopg.connect(args.postgres_url, autocommit=True) as admin:
        assert not admin.execute("SELECT 1 FROM pg_database WHERE datname=ANY(%s)", ([source_name, restored_name],)).fetchone()
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(source_name)))
    dsn = url.set(database=source_name).render_as_string(hide_password=False)
    restored_dsn = url.set(database=restored_name).render_as_string(hide_password=False)
    secret = uuid4().hex + uuid4().hex
    env = dict(os.environ, OPORA_DATABASE_URL=url.set(drivername="postgresql+psycopg", database=source_name).render_as_string(hide_password=False),
               OPORA_ENVIRONMENT="development", OPORA_SECRET_KEY=secret, OPORA_ASSET_ROOT=str(source_assets),
               OPORA_TRUSTED_ORIGINS='["http://127.0.0.1:5174"]', OPORA_RELEASE=f"{source_sha}-qa-tree-{source_tree[:12]}",
               PYTHONPATH=str(api), PYTHONPYCACHEPREFIX=str(workspace / "pycache"))
    run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=api, env=env)
    fixtures = json.loads(run([sys.executable, "-m", "app.cli", "fixtures", "g1", "--json"], cwd=api, env=env))
    (workspace / "private-bootstrap.json").write_text(json.dumps({"encryption_key": secret, "fixtures": fixtures}))
    source_process = restored_process = None
    sessions = []
    try:
        source_process, base = start_api(api, env, args.source_port, workspace / "source-api.log")
        staff, stranger = HttpSession(base), HttpSession(base)
        sessions.extend([staff, stranger])
        coordinator = fixtures["identities"]["coordinator@example.test"]
        staff.login(coordinator["email"], api, env, coordinator["totp_secret"])
        stranger.login("candidate-one@example.test", api, env)
        assert staff.session["user_id"] != stranger.session["user_id"]
        output = io.BytesIO()
        image = Image.new("RGB", (48, 32), (247, 243, 235))
        draw = ImageDraw.Draw(image)
        draw.rectangle((5, 5, 20, 26), fill=(218, 113, 73))
        draw.ellipse((25, 8, 42, 25), fill=(87, 121, 102))
        image.save(output, format="PNG")
        data = output.getvalue()
        checksum = digest(data)
        asset = staff.command("POST", "/api/v1/assets/upload-intents", {"content_type": "image/png", "expected_size": len(data), "checksum": checksum})
        staff.command("PATCH", asset["upload_url"], data=data)
        ready = staff.command("POST", f"/api/v1/assets/{asset['id']}/complete-upload", {})
        assert ready["state"] == "ready"
        participant = staff.command("POST", "/api/v1/coord/participants", {"display_name": "Участник теста восстановления", "photo_asset_id": asset["id"]})
        paths = [f"/api/v1/coord/participants/{participant['id']}/photo", f"/api/v1/assets/{asset['id']}/content"]
        source_denials = []
        for path in paths:
            assert staff.image(path, checksum) == len(data)
            source_denials.append(stranger.denied(path))
        cookies = dict(staff.http.cookies), dict(stranger.http.cookies)
        for client in sessions:
            client.close()
        sessions.clear()
        stop_api(source_process)
        source_process = None
        # No worker or API writes continue during this consistent DB/files snapshot.
        before = table_snapshot(dsn)
        dump = workspace / "database.dump"
        run([str(args.pg_bin / "pg_dump"), "--format=custom", "--file=" + str(dump), "--dbname=" + dsn])
        shutil.copytree(source_assets, workspace / "files-snapshot")
        files = tree_manifest(workspace / "files-snapshot")
        assert len(files) == 1 and next(iter(files.values()))["sha256"] == checksum
        with psycopg.connect(args.postgres_url, autocommit=True) as admin:
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(restored_name)))
        run([str(args.pg_bin / "pg_restore"), "--no-owner", "--exit-on-error", "--dbname=" + restored_dsn, str(dump)])
        shutil.copytree(workspace / "files-snapshot", restored_assets)
        assert table_snapshot(restored_dsn) == before, "Restored DB head/table counts differ"
        assert tree_manifest(restored_assets) == files, "Restored private files differ"
        restore_env = dict(env, OPORA_DATABASE_URL=url.set(drivername="postgresql+psycopg", database=restored_name).render_as_string(hide_password=False), OPORA_ASSET_ROOT=str(restored_assets))
        restored_process, restored_base = start_api(api, restore_env, args.restore_port, workspace / "restored-api.log")
        restored_staff, restored_stranger = HttpSession(restored_base, cookies[0]), HttpSession(restored_base, cookies[1])
        sessions.extend([restored_staff, restored_stranger])
        assert restored_staff.session["is_staff"] is True
        restored_denials = []
        for path in paths:
            assert restored_staff.image(path, checksum) == len(data)
            restored_denials.append(restored_stranger.denied(path))
        with psycopg.connect(restored_dsn, autocommit=True) as db:
            changed = db.execute("UPDATE staff_memberships SET revoked_at=now() WHERE user_id=%s AND foundation_id=%s AND revoked_at IS NULL", (coordinator["user_id"], fixtures["foundation_id"])).rowcount
            assert changed == 1
        revoked_denials = [restored_staff.denied(path) for path in paths]
        session = restored_staff.http.get("/api/v1/auth/session").json()
        assert session["is_staff"] is False
        with psycopg.connect(dsn) as db:
            assert db.execute("SELECT revoked_at FROM staff_memberships WHERE user_id=%s AND foundation_id=%s", (coordinator["user_id"], fixtures["foundation_id"])).fetchone()[0] is None
        report = {"outcome": "passed", "source_commit": source_sha, "source_api_dirty": source_dirty,
                  "source_tree_sha256": source_tree, "runtime_release": env["OPORA_RELEASE"],
                  "runtime_version_readback": "source and restored matched", "cluster_port": 56148, "source_database": source_name, "restored_database": restored_name,
                  "source_asset_root": str(source_assets), "restored_asset_root": str(restored_assets),
                  "migration_head": before["head"], "table_count": len(before["counts"]), "private_files": files,
                  "image_sha256": checksum, "image_bytes": len(data), "source_stranger_denials": source_denials,
                  "restored_stranger_denials": restored_denials, "restored_revoked_member_denials": revoked_denials,
                  "revocation_mechanism": "isolated restored staff_memberships fixture UPDATE; no public membership revoke endpoint",
                  "source_membership_unchanged": True,
                  "proof_limit": "Frozen working-tree API snapshot; final immutable release rerun and broader P20 still required"}
        (workspace / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        print(json.dumps({"outcome": "passed", "report": str(workspace / "report.json"), "source_tree_sha256": source_tree,
                          "migration_head": before["head"], "table_count": len(before["counts"]), "image_sha256": checksum,
                          "source_and_restored_authorized_image": "checksum matched", "stranger_and_revoked_member": "denied"}))
    finally:
        for client in sessions:
            client.close()
        stop_api(source_process)
        stop_api(restored_process)


if __name__ == "__main__":
    main()
