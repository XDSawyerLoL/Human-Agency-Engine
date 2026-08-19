from app.main import app
from app.routers.settlement_permit import public_router, router


def test_settlement_permit_routes_are_mounted_with_public_verify_separated():
    methods_by_path = {
        route.path: set(getattr(route, "methods", set()) or set())
        for route in app.routes
        if hasattr(route, "path")
    }
    app_settlement_paths = sorted(path for path in methods_by_path if "settlement-permit" in path)
    private_router_paths = sorted(getattr(route, "path", "") for route in router.routes)
    public_router_paths = sorted(getattr(route, "path", "") for route in public_router.routes)
    diagnostic = {
        "app_settlement_paths": app_settlement_paths,
        "private_router_paths": private_router_paths,
        "public_router_paths": public_router_paths,
    }
    assert "/v1/settlement-permits/verify" in methods_by_path, diagnostic
    assert "POST" in methods_by_path["/v1/settlement-permits/verify"], diagnostic
    assert "/v1/settlement-permits/consume" in methods_by_path, diagnostic
    assert "POST" in methods_by_path["/v1/settlement-permits/consume"], diagnostic
    assert any(path.startswith("/v1/settlement-permits/users/") for path in methods_by_path), diagnostic
