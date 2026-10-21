"""Bounded cross-domain mutation/receipt checks requested after the P14 finding."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from hashlib import sha256
import time
from uuid import uuid4

import pytest


def wait_for_locks(postgres, count):
    until = time.monotonic() + 5
    while time.monotonic() < until:
        postgres.execute("SELECT pg_stat_clear_snapshot()")
        waiting = postgres.execute("""SELECT count(*) FROM pg_stat_activity
            WHERE datname=current_database() AND wait_event_type='Lock' AND pid<>pg_backend_pid()""").fetchone()[0]
        if waiting >= count:
            return
        time.sleep(.02)
    raise AssertionError(f"Expected {count} API requests waiting for transaction locks")


def capability_ids(postgres, user, foundation, permission):
    rows = postgres.execute("""SELECT g.id FROM permission_grants g
        JOIN staff_memberships m ON m.id=g.membership_id
        WHERE m.user_id=%s AND m.foundation_id=%s AND g.permission=%s
          AND g.revoked_at IS NULL AND g.scope_type='foundation'""", (user, foundation, permission)).fetchall()
    return [str(row[0]) for row in rows]


def command_fixture(domain, staff, environment):
    suffix = uuid4().hex[:10]
    if domain == "roles":
        return "roles.manage", "/coord/roles", {"title": f"ACL роль {suffix}"}
    if domain == "opportunities":
        role = staff.command("POST", "/coord/roles", {"title": f"ACL роль возможности {suffix}"})
        return "opportunities.manage", "/coord/opportunities", {"title": f"ACL возможность {suffix}", "role_ids": [role["id"]]}
    if domain == "calendar":
        return "schedule.manage", "/coord/event-series", {
            "title": f"ACL занятие {suffix}", "start_date": (date.today() + timedelta(days=30)).isoformat(),
            "start_time": "10:00:00", "duration_minutes": 60, "location": "Тестовое помещение",
        }
    if domain == "participants":
        participant = staff.command("POST", "/coord/participants", {"display_name": f"Тестовый участник {suffix}"})
        return "participants.private_notes", f"/coord/participants/{participant['id']}/private-notes", {"text": "Закрытая тестовая заметка"}
    if domain == "messaging":
        recipient = environment["fixture"]["identities"]["candidate-one@example.test"]["user_id"]
        return "messaging.manage", "/conversations", {"title": f"Закрытый ACL диалог {suffix}", "member_ids": [recipient]}
    raise AssertionError(domain)


@pytest.mark.parametrize("domain", ["roles", "opportunities", "calendar", "participants", "messaging"])
@pytest.mark.parametrize("replay", [False, True], ids=["new-command", "old-receipt"])
def test_queued_revoke_closes_domain_command_and_old_receipt(domain, replay, staff, postgres, environment):
    permission, path, body = command_fixture(domain, staff, environment)
    identity = environment["fixture"]["identities"]["coordinator@example.test"]
    user, foundation = identity["user_id"], environment["fixture"]["foundation_id"]
    ids = capability_ids(postgres, user, foundation, permission)
    if not ids:
        # Explicit admin setup for a newly integrated domain capability.
        staff.command("POST", "/coord/staff/grants", {"user_id": user, "permission": permission, "scope_type": "foundation"})
        ids = capability_ids(postgres, user, foundation, permission)
    assert len(ids) == 1, "The isolated fixture needs exactly one capability under test"
    key = str(uuid4())
    if replay:
        staff.command("POST", path, body, key)
    lock = int.from_bytes(sha256(f"authz:{foundation}:{user}".encode()).digest()[:8], "big", signed=True)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            with postgres.transaction():
                postgres.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
                revoke = pool.submit(staff.request, "POST", f"/coord/staff/grants/{ids[0]}/revoke", {})
                wait_for_locks(postgres, 1)
                mutation = pool.submit(staff.request, "POST", path, body, key)
                wait_for_locks(postgres, 2)
            revoked, denied = revoke.result(), mutation.result()
        assert revoked.status_code == 200
        assert denied.status_code == 403, f"{domain} {path}: fresh scope must reject before command/receipt ({denied.status_code})"
        assert staff.request("POST", path, body, key).status_code == 403
    finally:
        staff.command("POST", "/coord/staff/grants", {"user_id": user, "permission": permission, "scope_type": "foundation"})


@pytest.mark.parametrize("replay", [False, True], ids=["new-send", "old-send-receipt"])
def test_member_revoke_precedes_waiting_send_and_closes_private_reads(replay, staff, signed_in_candidate, postgres):
    candidate = signed_in_candidate
    conversation = staff.command("POST", "/conversations", {
        "title": f"Проверка отзыва участника {uuid4().hex[:8]}", "member_ids": [candidate.session["user_id"]],
    })
    path = f"/conversations/{conversation['id']}/messages"
    payload = {"text": "Закрытое тестовое сообщение", "asset_ids": []}
    key = str(uuid4())
    if replay:
        sent = candidate.command("POST", path, payload, key)
        assert candidate.read(path)["items"][0]["id"] == sent["id"]
    current = staff.read(f"/conversations/{conversation['id']}")
    with ThreadPoolExecutor(max_workers=2) as pool:
        with postgres.transaction():
            postgres.execute("SELECT id FROM conversations WHERE id=%s FOR UPDATE", (conversation["id"],))
            revoke = pool.submit(staff.request, "POST", f"/conversations/{conversation['id']}/members/revoke", {
                "expected_version": current["version"], "user_id": candidate.session["user_id"],
            })
            wait_for_locks(postgres, 1)
            mutation = pool.submit(candidate.request, "POST", path, payload, key)
            wait_for_locks(postgres, 2)
        revoked, denied = revoke.result(), mutation.result()
    assert revoked.status_code == 200
    assert denied.status_code in (403, 404), f"A removed member must not receive old private message/receipt ({denied.status_code})"
    assert candidate.request("POST", path, payload, key).status_code in (403, 404)
    for private_path in (path, f"/conversations/{conversation['id']}", f"/conversations/{conversation['id']}/sync"):
        assert candidate.request("GET", private_path).status_code in (403, 404)
    after = staff.read(path)["items"]
    assert len(after) == (1 if replay else 0), "A denied command must not append another message"
