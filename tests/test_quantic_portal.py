from pathlib import Path
from threading import Barrier

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
    assert "quanticmail.onrender.com" not in mail\n    assert "Quantic Mail" in mail
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


def test_status_probes_active_services_concurrently():
    barrier = Barrier(4)

    def synchronized_probe(_target):
        barrier.wait(timeout=1)
        return {"reachable": True, "http_status": 200}

    payload = build_portal_status(probe=synchronized_probe)
    active = [item for item in payload["services"] if item["state"] != "pending"]
    assert len(active) == 4
    assert all(item["reachable"] is True for item in active)


def test_quantic_desire_visual_system_is_wired():
    root = text("public/index.html")
    css = text("public/quantic.css")
    js = text("public/quantic.js")
    assert 'q-hero-stage' in root
    assert 'class="q-hero-aurora"' in root
    assert 'class="q-signal-ribbon"' in root
    assert 'data-q-reveal' in root
    assert 'data-q-tilt' in root
    assert "--q-ease:" in css
    assert ".q-hero-stage" in css
    assert ".q-hero-aurora" in css
    assert ".q-noise" in css
    assert ".q-signal-ribbon" in css
    assert "@media(prefers-reduced-motion:reduce)" in css
    assert "IntersectionObserver" in js
    assert "pointermove" in js


def test_quantic_surfaces_share_premium_shell():
    for path in (
        "public/quantic/index.html",
        "public/mail/index.html",
        "public/network/index.html",
        "public/products/index.html",
        "public/plans/index.html",
    ):
        page = text(path)
        assert 'class="q-body q-premium"' in page
        assert 'class="q-noise"' in page
        assert "quantic.css?v=2.0" in page


def test_all_quantic_primary_surfaces_load_unified_providence_visual_layer():
    for path in (
        "public/index.html",
        "public/quantic/index.html",
        "public/vision/index.html",
        "public/mail/index.html",
        "public/network/index.html",
        "public/products/index.html",
    ):
        page = text(path)
        assert "quantic-unified.css?v=3.0" in page, path


def test_providence_internal_shell_uses_quantic_navigation_not_software_sidebar():
    shell = text("public/providence-v15-shell.js")
    assert "q-global-nav" in shell
    assert "q-vision-subnav" in shell
    assert "quantic-unified.css?v=3.0" in shell
    assert "p15-sidebar" not in shell
    assert "p15-topbar" not in shell


def test_unified_visual_layer_inherits_providence_color_language():
    css = text("public/quantic-unified.css")
    for token in ("#148cff", "#20d8ff", "#9b5cff", "#ffc74d", "#02050b"):
        assert token in css
    assert ".q-global-nav" in css
    assert ".q-vision-subnav" in css
    assert ".q-unified-hero" in css
    assert "@media(prefers-reduced-motion:reduce)" in css


def test_all_vision_product_routes_load_unified_css_before_runtime_shell():
    routes = (
        "alerts", "analyst", "backtest", "cameras", "causal", "crypto",
        "horizons", "intelligence", "matches", "modules", "predictions",
        "sports", "settings", "sources", "track-record",
    )
    for route in routes:
        page = text(f"public/{route}/index.html")
        assert "quantic-unified.css?v=3.0" in page, route


def test_legacy_v14_shell_bridges_to_unified_v15_shell():
    shell = text("public/providence-v14-shell.js")
    assert "providence-v15-shell.js" in shell


def test_mail_status_is_local_to_hostinger():
    target = next(item for item in QUANTIC_SERVICE_TARGETS if item.id == "mail")
    assert target.public_url == "/mail/"
    assert target.probe_url is None
