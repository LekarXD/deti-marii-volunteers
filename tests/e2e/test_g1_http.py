"""G1 journeys against committed server state and PostgreSQL, never localStorage."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from uuid import uuid4

import pytest



PRIVATE_SENTINEL = "G1-PRIVATE-NOTE-NOT-FOR-CANDIDATE"


def answers():
    suffix = uuid4().hex[:10]
    return {
        "firstName": "Анна", "lastName": "Проверочная", "birthdate": "2010-01-01",
        "phone": "+7 (999) 123-45-67", "email": f"g1-{suffix}@example.test",
        "area": "Другой город", "directions": ["Творчество"],
        "participation": "Каждую неделю", "volExp": "Нет",
        "specialExp": "Хочу обсудить на встрече", "record": "Хочу обсудить",
        "source": "Друзья",
    }


def submit(client):
    draft = client.read("/registration/draft")
    data = answers()
    saved = client.command("PUT", "/registration/draft", {
        "expected_version": draft["version"], "step": 1, "answers": data,
    })
    assert client.read("/registration/draft")["answers"] == saved["answers"]
    payload = {"expected_version": 0, "answers": data,
               "consents": {"personal_data": True, "news": False, "document_version": "4"}}
    key = str(uuid4())
    result = client.command("POST", "/applications/submit", payload, key)
    repeated = client.command("POST", "/applications/submit", payload, key)
    assert repeated["id"] == result["id"]
    assert repeated["version"] == result["version"]
    return result


def slots(staff, candidate):
    day = date.today() + timedelta(days=10 + (int(uuid4().hex[:6], 16) % 3000))
    window = staff.command("POST", "/coord/interview-availability", {
        "local_start_date": day.isoformat(), "start_minute": 600, "end_minute": 720,
        "timezone": "Europe/Moscow", "recurrence": "once", "interval_weeks": 1,
        "weekdays": [], "duration_minutes": 30, "buffer_after_minutes": 10,
        "venue": "Онлайн, тестовая встреча", "active": True,
    })
    result = candidate.read(f"/interview-slots?from={day.isoformat()}&to={(day + timedelta(days=1)).isoformat()}&timezone=Europe%2FMoscow")
    own = [slot for slot in result if slot["series_id"] == window["id"]]
    assert len(own) >= 2, "A two-hour availability must provide independent slots"
    return own


def book(candidate, slot):
    payload = {"slot_id": slot["id"], "slot_version": slot["version"]}
    key = str(uuid4())
    result = candidate.command("POST", "/interviews", payload, key)
    replay = candidate.command("POST", "/interviews", payload, key)
    assert replay["id"] == result["id"]
    return result


def assert_no_private_fields(value):
    if isinstance(value, dict):
        for key, item in value.items():
            assert key not in {"private_note", "private_notes", "internal_notes", "secret_cipher", "token_hash"}, f"Self DTO leaked {key}"
            assert_no_private_fields(item)
    elif isinstance(value, list):
        for item in value:
            assert_no_private_fields(item)
    elif isinstance(value, str):
        assert PRIVATE_SENTINEL not in value, "Private note leaked to candidate"


def test_questionnaire_booking_learning_edit_and_coordinator(candidate, stranger, staff):
    application = submit(candidate)
    assert candidate.read("/me/application")["id"] == application["id"]
    before = candidate.read("/me/preparation")
    assert before["introduction_completed"] is False
    assert before["booking_requires_introduction"] is False
    available = slots(staff, candidate)
    booking = book(candidate, available[0])  # Explicitly before any learning/test.
    assert candidate.read("/me/interviews")[0]["id"] == booking["id"]

    queue = staff.read("/coord/candidates")
    assert application["id"] in {row["id"] for row in queue["items"]}
    detail = staff.read(f"/coord/candidates/{application['id']}")
    staff.command("POST", f"/coord/candidates/{application['id']}/review", {
        "expected_version": detail["version"], "state": "reviewing", "public_message": "Анкета принята в работу",
    })
    staff.command("POST", f"/coord/candidates/{application['id']}/notes", {"text": PRIVATE_SENTINEL})
    request = candidate.command("POST", "/me/candidate-requests", {"kind": "road_help", "text": "Как пройти от остановки?"})
    staff.command("POST", f"/coord/candidate-requests/{request['id']}/respond", {
        "expected_version": request["version"], "text": "Встречаем у главного входа",
    })
    response = candidate.read(f"/me/candidate-requests/{request['id']}")
    assert response["responses"][-1]["text"] == "Встречаем у главного входа"
    denied = stranger.request("GET", f"/me/candidate-requests/{request['id']}")
    assert denied.status_code in (403, 404)

    assignment = candidate.read("/me/preparation")["assignments"][0]
    assert len(assignment["lessons"]) == 4
    for lesson in assignment["lessons"]:
        content = candidate.read(f"/learning/lessons/{lesson['id']}")
        assert content["blocks"], "A module must contain actual published material"
        candidate.command("POST", f"/learning/progress/{lesson['id']}/complete", {"assignment_id": assignment["id"]})
    attempt = candidate.command("POST", f"/assessments/{assignment['assessment_version_id']}/attempts", {})
    assert len(attempt["questions"]) == 10
    assert attempt["score"] is None
    assert all("correct_option" not in question for question in attempt["questions"])
    forged = candidate.request("POST", f"/assessment-attempts/{attempt['id']}/answers", {
        "question_id": attempt["questions"][0]["id"], "selected_option": 0, "score": 10,
    })
    assert forged.status_code == 422
    for question in attempt["questions"]:
        candidate.command("POST", f"/assessment-attempts/{attempt['id']}/answers", {
            "question_id": question["id"], "selected_option": 0,
        })
    scored = candidate.command("POST", f"/assessment-attempts/{attempt['id']}/submit", {})
    assert scored["score"] == 4, "Server must compute four correct all-zero answers from published ten-question source"
    assert candidate.read(f"/assessment-attempts/{attempt['id']}/result")["score"] == 4
    candidate.command("POST", "/policy-acknowledgements", {"assignment_id": assignment["id"]})
    assert candidate.read("/me/preparation")["introduction_completed"] is True
    second = candidate.command("POST", f"/assessments/{assignment['assessment_version_id']}/attempts", {})
    assert second["id"] != attempt["id"]
    assert second["score"] is None
    assert candidate.read(f"/assessment-attempts/{attempt['id']}/result")["score"] == 4

    current = candidate.read("/me/application")
    revised_answers = dict(current["revision"]["answers"], email=f"edited-{uuid4().hex[:8]}@example.test")
    revised = candidate.command("POST", "/me/application/revisions", {
        "expected_version": current["version"], "answers": revised_answers,
        "consents": {"personal_data": True, "news": False, "document_version": "4"},
    })
    assert revised["id"] == application["id"]
    assert candidate.read("/me/interviews")[0]["id"] == booking["id"]
    assert candidate.read(f"/assessment-attempts/{attempt['id']}/result")["score"] == 4
    assert_no_private_fields(candidate.read("/me/application"))
    assert_no_private_fields(candidate.read("/me/interviews"))
    assert_no_private_fields(candidate.read("/me/preparation"))


def test_csrf_origin_acl_and_stale_version(candidate, stranger, staff):
    draft = candidate.read("/registration/draft")
    payload = {"expected_version": draft["version"], "step": 0, "answers": {"firstName": "Проверка"}}
    for headers in ({"X-CSRF-Token": ""}, {"Origin": "https://attacker.invalid"}, {"Origin": "null"}):
        denied = candidate.request("PUT", "/registration/draft", payload, extra_headers=headers)
        assert denied.status_code == 403
    saved = candidate.command("PUT", "/registration/draft", payload)
    stale = candidate.request("PUT", "/registration/draft", payload)
    assert stale.status_code == 409
    assert stale.json()["current_version"] == saved["version"]
    assert stranger.request("GET", "/coord/candidates").status_code == 403
    assert stranger.request("GET", "/coord/interview-availability").status_code == 403
    assert candidate.read("/registration/draft")["answers"]["firstName"] == "Проверка"


def test_booking_race_and_failed_move_preserve_original(candidate, stranger, staff):
    submit(candidate)
    submit(stranger)
    available = slots(staff, candidate)
    payload = {"slot_id": available[0]["id"], "slot_version": available[0]["version"]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda client: client.request("POST", "/interviews", payload), [candidate, stranger]))
    assert sorted(result.status_code for result in results) == [201, 409]
    winner = candidate if results[0].status_code == 201 else stranger
    loser = stranger if winner is candidate else candidate
    booking = winner.read("/me/interviews")[0]
    assert loser.read("/me/interviews") == []
    occupied = book(loser, available[1])
    failed = winner.request("POST", f"/interviews/{booking['id']}/reschedule", {
        "expected_version": booking["version"], "slot_id": available[1]["id"], "slot_version": available[1]["version"],
    })
    assert failed.status_code == 409
    preserved = winner.read("/me/interviews")[0]
    assert preserved["slot_id"] == booking["slot_id"]
    assert preserved["version"] == booking["version"]
    denied = loser.request("POST", f"/interviews/{booking['id']}/cancel", {
        "expected_version": booking["version"], "reason": "Чужая запись",
    })
    assert denied.status_code in (403, 404)
    assert loser.read("/me/interviews")[0]["id"] == occupied["id"]


def test_idempotency_payload_conflict_and_actor_isolation(candidate, stranger):
    data = {"expected_version": 0, "step": 0, "answers": {"firstName": "Первая"}}
    key = str(uuid4())
    original = candidate.command("PUT", "/registration/draft", data, key)
    replay = candidate.command("PUT", "/registration/draft", data, key)
    assert replay == original
    conflict = candidate.request("PUT", "/registration/draft", dict(data, answers={"firstName": "Подмена"}), key)
    assert conflict.status_code == 409
    own = stranger.command("PUT", "/registration/draft", dict(data, answers={"firstName": "Вторая"}), key)
    assert own["id"] != original["id"]
    assert candidate.read("/registration/draft")["answers"]["firstName"] == "Первая"
    assert stranger.read("/registration/draft")["answers"]["firstName"] == "Вторая"


def test_public_outcome_and_private_note(candidate, staff, postgres, environment):
    submit(candidate)
    booking = book(candidate, slots(staff, candidate)[0])
    payload = {"expected_version": booking["version"], "outcome": "first_visit",
               "public_agreement": "Договорились о первом знакомстве с группой",
               "private_note": PRIVATE_SENTINEL}
    too_soon = staff.request("POST", f"/interviews/{booking['id']}/complete", payload)
    assert too_soon.status_code == 409
    # Local fixture time travel avoids any public test-clock endpoint. Only this
    # invented booking is moved; the product command itself must enforce authz.
    with postgres.cursor() as cursor:
        cursor.execute("""UPDATE interview_bookings
            SET starts_at=now()-interval '1 day', ends_at=now()-interval '1 day'+interval '30 minutes',
                busy_until=now()-interval '1 day'+interval '40 minutes'
            WHERE id=%s AND foundation_id=%s AND status='booked'""",
            (booking["id"], environment["fixture"]["foundation_id"]))
        assert cursor.rowcount == 1
    result = staff.command("POST", f"/interviews/{booking['id']}/complete", payload)
    assert result["status"] == "completed"
    assert result["private_note"] == PRIVATE_SENTINEL
    own = candidate.read("/me/interviews")[0]
    assert own["result"]["public_agreement"] == payload["public_agreement"]
    assert_no_private_fields(own)
    with postgres.cursor() as cursor:
        cursor.execute("SELECT count(*) FROM interview_results WHERE booking_id=%s", (booking["id"],))
        assert cursor.fetchone()[0] == 1


def test_revoke_is_fresh_and_group_scope_does_not_grant_global_queue(staff, postgres, environment):
    identity = environment["fixture"]["identities"]["coordinator@example.test"]
    with postgres.cursor() as cursor:
        cursor.execute("""SELECT g.id FROM permission_grants g
            JOIN staff_memberships m ON m.id=g.membership_id
            WHERE m.user_id=%s AND m.foundation_id=%s AND g.permission='candidates.read'
              AND g.revoked_at IS NULL AND g.scope_type='foundation'""",
            (identity["user_id"], environment["fixture"]["foundation_id"]))
        grants = [str(row[0]) for row in cursor.fetchall()]
    assert grants, "Fixture coordinator must initially have queue permission"
    assert staff.request("GET", "/coord/candidates").status_code == 200
    try:
        for grant in grants:
            staff.command("POST", f"/coord/staff/grants/{grant}/revoke", {})
        assert staff.request("GET", "/coord/candidates").status_code == 403
        assert "candidates.read" not in staff.refresh()["permissions"]
        scoped = staff.command("POST", "/coord/staff/grants", {
            "user_id": identity["user_id"], "permission": "candidates.read",
            "scope_type": "group", "scope_id": str(uuid4()),
        })
        assert staff.request("GET", "/coord/candidates").status_code == 403
        staff.command("POST", f"/coord/staff/grants/{scoped['id']}/revoke", {})
    finally:
        staff.command("POST", "/coord/staff/grants", {
            "user_id": identity["user_id"], "permission": "candidates.read", "scope_type": "foundation",
        })
    assert staff.request("GET", "/coord/candidates").status_code == 200


def test_logout_revokes_cookie_and_no_http_dev_inbox(candidate):
    cookie = candidate.http.cookies.get("opora_session")
    candidate.command("POST", "/auth/logout", {})
    denied = candidate.http.get("/api/v1/me/preparation", headers={"Cookie": f"opora_session={cookie}"})
    assert denied.status_code == 401
    assert candidate.http.get("/api/v1/auth/dev-inbox").status_code == 404


def test_learning_can_finish_before_booking_without_pass_threshold(candidate, staff):
    submit(candidate)
    assignment = candidate.read("/me/preparation")["assignments"][0]
    for lesson in assignment["lessons"]:
        candidate.command("POST", f"/learning/progress/{lesson['id']}/complete", {"assignment_id": assignment["id"]})
    attempt = candidate.command("POST", f"/assessments/{assignment['assessment_version_id']}/attempts", {})
    # All-zero answers deliberately produce a non-perfect instructional score.
    for question in attempt["questions"]:
        candidate.command("POST", f"/assessment-attempts/{attempt['id']}/answers", {
            "question_id": question["id"], "selected_option": 0,
        })
    scored = candidate.command("POST", f"/assessment-attempts/{attempt['id']}/submit", {})
    assert scored["score"] == 4
    candidate.command("POST", "/policy-acknowledgements", {"assignment_id": assignment["id"]})
    assert candidate.read("/me/preparation")["introduction_completed"] is True
    booking = book(candidate, slots(staff, candidate)[0])
    assert booking["status"] == "booked"


def test_availability_edit_races_booking_without_stale_success(candidate, staff):
    submit(candidate)
    selected = slots(staff, candidate)[0]
    window = staff.read(f"/coord/interview-availability/{selected['series_id']}")
    # Move the entire window by three hours, preserving its duration/timezone.
    changed = {key: value for key, value in window.items()
               if key not in {"id", "coordinator_id", "version", "exceptions"}}
    changed.update(expected_version=window["version"],
                   start_minute=window["start_minute"] + 180,
                   end_minute=window["end_minute"] + 180)
    payload = {"slot_id": selected["id"], "slot_version": selected["version"]}
    with ThreadPoolExecutor(max_workers=2) as pool:
        booking_future = pool.submit(candidate.request, "POST", "/interviews", payload)
        edit_future = pool.submit(staff.request, "PATCH", f"/coord/interview-availability/{window['id']}", changed)
        booking, edit = booking_future.result(), edit_future.result()
    assert (booking.status_code, edit.status_code) in {(201, 409), (409, 200)}, \
        f"Conflicting booking/window edit must serialize: {booking.status_code}/{edit.status_code}"
    own = candidate.read("/me/interviews")
    if booking.status_code == 201:
        assert own[0]["id"] == booking.json()["id"]
        assert own[0]["starts_at"] == selected["starts_at"]
    else:
        assert own == []


def test_development_delivery_is_never_claimed_as_provider_success(candidate, environment):
    import json
    import os
    from pathlib import Path
    import subprocess
    import sys
    email = f"delivery-{uuid4().hex[:10]}@example.test"
    result = candidate.command("POST", "/auth/challenges", {"email": email, "purpose": "login"})
    assert result["status"] == "queued"
    assert result["delivery"] == "dev_inbox"
    assert "token" not in result
    process = subprocess.run(
        [sys.executable, "-m", "app.cli", "dev-inbox", "--email", email],
        cwd=os.environ.get("OPORA_G1_API_DIR", str(Path(__file__).resolve().parents[2] / "apps/api")),
        check=True, capture_output=True, text=True,
    )
    rows = json.loads(process.stdout)
    message = next(row for row in rows if row["challenge_id"] == result["challenge_id"])
    assert message["state"] in {"queued", "dev_inbox"}
    assert message["state"] not in {"sent", "delivered", "provider_accepted"}


@pytest.mark.parametrize("replay", [False, True])
def test_revoke_commits_before_waiting_staff_command_and_receipt(staff, postgres, environment, replay):
    """Force HTTP auth to precede revoke but its mutation guard to follow commit."""
    from hashlib import sha256
    import time
    identity = environment["fixture"]["identities"]["coordinator@example.test"]
    foundation = environment["fixture"]["foundation_id"]
    with postgres.cursor() as cursor:
        cursor.execute("""SELECT g.id FROM permission_grants g JOIN staff_memberships m ON m.id=g.membership_id
            WHERE m.user_id=%s AND m.foundation_id=%s AND g.permission='interviews.manage'
              AND g.revoked_at IS NULL AND g.scope_type='foundation'""", (identity["user_id"], foundation))
        grants = [str(row[0]) for row in cursor.fetchall()]
    assert len(grants) == 1, "Deterministic fixture requires one active interviews.manage grant"
    lock = int.from_bytes(sha256(f"authz:{foundation}:{identity['user_id']}".encode()).digest()[:8], "big", signed=True)
    day = date.today() + timedelta(days=4000 + int(uuid4().hex[:4], 16) % 3000)
    body = {"local_start_date": day.isoformat(), "start_minute": 600, "end_minute": 720,
            "timezone": "Europe/Moscow", "recurrence": "once", "duration_minutes": 30,
            "buffer_after_minutes": 10, "venue": "Проверка отзыва", "active": True}

    key = str(uuid4())
    if replay:
        staff.command("POST", "/coord/interview-availability", body, key)

    def wait_for_waiters(expected):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            with postgres.cursor() as cursor:
                cursor.execute("""SELECT count(*) FROM pg_locks WHERE locktype='advisory' AND NOT granted
                    AND database=(SELECT oid FROM pg_database WHERE datname=current_database())""")
                if cursor.fetchone()[0] >= expected:
                    return
            time.sleep(.02)
        raise AssertionError(f"Expected {expected} HTTP requests waiting on shared authz guard")

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            with postgres.transaction():
                postgres.execute("SELECT pg_advisory_xact_lock(%s)", (lock,))
                revoke = pool.submit(staff.request, "POST", f"/coord/staff/grants/{grants[0]}/revoke", {})
                wait_for_waiters(1)
                command = pool.submit(staff.request, "POST", "/coord/interview-availability", body, key)
                wait_for_waiters(2)
            revoked, denied = revoke.result(), command.result()
        assert revoked.status_code == 200
        assert denied.status_code == 403, \
            f"A command ordered after committed revoke must fail before action or receipt: {denied.status_code}"
    finally:
        staff.command("POST", "/coord/staff/grants", {
            "user_id": identity["user_id"], "permission": "interviews.manage", "scope_type": "foundation",
        })
