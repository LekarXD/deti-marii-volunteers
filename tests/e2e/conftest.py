"""Independent localhost HTTP acceptance, using CLI-only fixture credentials."""
import json
import os
import subprocess
import sys

import pyotp
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import pytest


class Client:
    def __init__(self, base_url, origin, cookie=None):
        self.http = httpx.Client(base_url=base_url, timeout=15, follow_redirects=False)
        self.origin = origin
        if cookie:
            self.http.cookies.set("opora_session", cookie)
        self.session = self.read("/auth/session")

    def request(self, method, path, payload=None, key=None, extra_headers=None):
        headers = {"Origin": self.origin, "X-CSRF-Token": self.session["csrf_token"]}
        if method not in ("GET", "HEAD"):
            headers["Idempotency-Key"] = key or str(uuid4())
        headers.update(extra_headers or {})
        return self.http.request(method, "/api/v1" + path, json=payload, headers=headers)

    def read(self, path):
        result = self.http.get("/api/v1" + path)
        assert result.status_code == 200, f"GET {path}: {result.status_code}"
        return result.json()

    def command(self, method, path, payload=None, key=None):
        result = self.request(method, path, payload, key)
        assert result.status_code in (200, 201), f"{method} {path}: {result.status_code} {result.text[:300]}"
        return result.json()

    def refresh(self):
        self.session = self.read("/auth/session")
        return self.session

    def close(self):
        self.http.close()


@pytest.fixture(scope="session")
def environment():
    base = os.environ.get("OPORA_G1_BASE_URL", "http://127.0.0.1:8001")
    parsed = urlparse(base)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise pytest.UsageError("G1 writes are limited to a disposable localhost API")
    path = os.environ.get("OPORA_G1_FIXTURE_FILE")
    if not path:
        raise pytest.UsageError("OPORA_G1_FIXTURE_FILE must name the CLI-generated private JSON fixture")
    fixture = Path(path)
    if fixture.stat().st_mode & 0o077:
        raise pytest.UsageError("G1 credential fixture must have mode 0600")
    data = json.loads(fixture.read_text())
    return {"base": base, "origin": os.environ.get("OPORA_G1_ORIGIN", "http://127.0.0.1:5174"), "fixture": data}


@pytest.fixture
def candidate(environment):
    client = Client(environment["base"], environment["origin"])
    yield client
    client.close()


@pytest.fixture
def stranger(environment):
    client = Client(environment["base"], environment["origin"])
    yield client
    client.close()


@pytest.fixture(scope="session")
def staff(environment):
    client = Client(environment["base"], environment["origin"])
    identity = environment["fixture"]["identities"]["coordinator@example.test"]
    challenge = client.command("POST", "/auth/challenges", {"email": identity["email"], "purpose": "login"})
    assert challenge["delivery"] in {"dev_inbox", "pending", "unavailable"}
    # Decryption is a local CLI operation; there is no public inbox/token endpoint.
    process = subprocess.run(
        [sys.executable, "-m", "app.cli", "dev-inbox", "--email", identity["email"]],
        cwd=os.environ.get("OPORA_G1_API_DIR", str(Path(__file__).resolve().parents[2] / "apps/api")), check=True,
        capture_output=True, text=True,
    )
    inbox = json.loads(process.stdout)
    token = next(row["token"] for row in inbox if row.get("challenge_id") == challenge["challenge_id"])
    client.command("POST", "/auth/challenges/verify", {"challenge_id": challenge["challenge_id"], "token": token})
    client.refresh()
    assert "candidates.read" not in client.session["permissions"], "Email verification must not grant staff assurance"
    client.command("POST", "/auth/mfa/verify", {"code": pyotp.TOTP(identity["totp_secret"]).now()})
    client.refresh()
    assert client.session["is_staff"] is True
    yield client
    client.close()


@pytest.fixture(scope="session")
def postgres(environment):
    import psycopg
    dsn = os.environ.get("OPORA_DATABASE_URL", "").replace("postgresql+psycopg://", "postgresql://", 1)
    if urlparse(dsn).hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise pytest.UsageError("G1 DB fixture access requires a disposable localhost PostgreSQL URL")
    connection = psycopg.connect(dsn, autocommit=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('server_version'), EXISTS (SELECT 1 FROM foundations WHERE id=%s)",
                       (environment["fixture"]["foundation_id"],))
        version, found = cursor.fetchone()
        assert version.startswith("16."), "Acceptance must run against PostgreSQL 16"
        assert found, "CLI fixture foundation must be in the same test database"
    yield connection
    connection.close()
