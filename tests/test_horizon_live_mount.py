from app.main import app


def test_horizon_live_routes_are_mounted():
    methods_by_path = {
        route.path: set(getattr(route, "methods", set()) or set())
        for route in app.routes
        if hasattr(route, "path")
    }
    assert "/v1/horizon/live/sync" in methods_by_path
    assert "POST" in methods_by_path["/v1/horizon/live/sync"]
    assert "/v1/horizon/live/sources" in methods_by_path
    assert "GET" in methods_by_path["/v1/horizon/live/sources"]
