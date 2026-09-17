from pathlib import Path

from app.quantic_portal_status import QUANTIC_SERVICE_TARGETS, build_portal_status


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_root_is_quantic_portal():
    page = text("public/index.html")
    assert "QUANTIC" in page
    assert 'href="/quantic/"' in page
    assert 'href="/vision/"' in page
    assert 'href="/mail/"' in page
    assert 'href="/network/"' in page


def test_vision_preserves_providence_experience():
    page = text("public/vision/index.html")
    assert "Quantic Vision" in page
    assert "futurs plausibles" in page
    assert 'href="/predictions/"' in page


def test_operational_surfaces_exist():
    dashboard = text("public/quantic/index.html")
    mail = text("public/mail/index.html")
    network = text("public/network/index.html")
    products = text("public/products/index.html")
    assert "Quantic Vision" in dashboard
    assert "Quantic Mail" in dashboard
    assert "Quantic Network" in dashboard
    assert "quanticmail.onrender.com" in mail
    assert "api/quantic-portal/status" in network
    assert "Quantic Glide" in products
    assert "Quantic OS" in products


def test_nginx_proxies_portal_status_to_internal_api():
    config = text("hostinger/evidence-nginx.conf")
    assert "location /api/quantic-portal/" in config
    assert "proxy_pass http://api:8000/v1/quantic/portal/;" in config


def test_status_targets_are_fixed_and_include_current_network():
    ids = {target.id for target in QUANTIC_SERVICE_TARGETS}
    assert ids == {"vision", "mail", "relay-render", "relay-railway", "relay-hostinger"}


def test_status_normalizes_probe_failure_without_failing_payload():
    def fake_probe(target):
        if target.id == "relay-render":
            raise TimeoutError("offline-secret-detail")
        return {"reachable": True, "http_status": 200}

    payload = build_portal_status(probe=fake_probe)
    services = {item["id"]: item for item in payload["services"]}
    assert payload["status"] == "ok"
    assert services["relay-render"]["reachable"] is False
    assert "offline-secret-detail" not in str(services["relay-render"])
    assert services["relay-hostinger"]["state"] == "pending"
