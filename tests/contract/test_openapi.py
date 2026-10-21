"""Contract drift/safety checks. Reads the application, never a mocked API."""
from collections import Counter

from app.main import create_app


def test_operation_ids_are_unique_and_explicit():
    schema = create_app().openapi()
    operations = [operation for path in schema["paths"].values()
                  for method, operation in path.items()
                  if method in {"get", "post", "put", "patch", "delete"}]
    ids = [operation.get("operationId") for operation in operations]
    assert all(ids), "Every API operation needs a stable operationId"
    assert len(ids) == len(set(ids)), Counter(ids)


def test_no_public_role_switch_or_demo_reset():
    paths = create_app().openapi()["paths"]
    assert not any(fragment in path.lower() for path in paths
                   for fragment in ("switch-role", "role-switch", "demo-fill", "reset-demo"))


def test_g1_commands_exist_in_real_schema():
    paths = create_app().openapi()["paths"]
    expected = {
        "/api/v1/auth/session": "get",
        "/api/v1/registration/draft": "put",
        "/api/v1/applications/submit": "post",
        "/api/v1/me/application": "get",
        "/api/v1/me/application/revisions": "post",
        "/api/v1/coord/candidates": "get",
        "/api/v1/me/preparation": "get",
        "/api/v1/interview-slots": "get",
        "/api/v1/interviews": "post",
        "/api/v1/me/interviews": "get",
    }
    for path, method in expected.items():
        assert method in paths.get(path, {}), f"Missing G1 operation: {method.upper()} {path}"
