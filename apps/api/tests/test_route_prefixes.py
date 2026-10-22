"""The web transport and both nginx configs reach every API route through /api/v1."""
from fastapi.routing import APIRoute
from app.main import create_app

def test_every_api_route_is_mounted_under_api_v1():
    paths={route.path for route in create_app().routes if isinstance(route,APIRoute)}
    assert {'/health','/ready','/version.json'}<=paths
    assert sorted(path for path in paths-{'/health','/ready','/version.json'} if not path.startswith('/api/v1/'))==[]
    assert {'/api/v1/simulator/scenarios','/api/v1/coord/simulator/scenarios','/api/v1/simulation-sessions/{session_id}'}<=paths
