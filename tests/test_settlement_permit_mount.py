from app.main import app


def test_settlement_permit_routes_are_mounted_with_public_verify_separated():
    methods_by_path = {
        route.path: set(getattr(route, "methods", set()) or set())
        for route in app.routes
        if hasattr(route, "path")
    }
    assert "/v1/settlement-permits/verify" in methods_by_path
    assert "POST" in methods_by_path["/v1/settlement-permits/verify"]
    assert "/v1/settlement-permits/consume" in methods_by_path
    assert "POST" in methods_by_path["/v1/settlement-permits/consume"]
    assert any(path.startswith("/v1/settlement-permits/users/") for path in methods_by_path)
