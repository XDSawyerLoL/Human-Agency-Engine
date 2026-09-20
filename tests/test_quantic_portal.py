from pathlib import Path
from threading import Barrier

from app.quantic_portal_status import QUANTIC_SERVICE_TARGETS, build_portal_status, quantic_service_targets


ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_root_is_quantic_portal():
    page = text("public/index.html")
    assert "QUANTIC" in page
    assert 'href="/quantic/"' in page
    assert 'href="/vision/"' in page
    assert 'href="/mail/"' in page
    assert 'href="/downloads/"' in page
    assert 'href="/network/"' not in page


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
    downloads = text("public/downloads/index.html")
    assert "Quantic Vision" in dashboard
    assert "Quantic Mail" in dashboard
    assert "Quantic Network" in dashboard
    assert "quanticmail.onrender.com" not in mail
    assert "Quantic Mail" in mail
    assert '/downloads/#network' in network
    assert 'location.replace(\'/downloads/#network\')' in network
    assert 'url=/downloads/' in products
    assert "Quantic Glide" in downloads
    assert "Quantic OS" in downloads
    assert "Quantic Studio 2.7.3" in downloads
    assert "QuanticStudio-Setup-2.7.3.exe" in downloads
    assert "/assets/brand-2026/studio-mark.svg" in downloads




def test_products_and_tools_are_one_catalogue():
    root = text("public/index.html")
    downloads = text("public/downloads/index.html")
    products = text("public/products/index.html")
    mail_nav = text("public/quantic-mail-portal-nav.js")

    assert "Produits &amp; outils" in root
    assert "Produits &amp; outils" in downloads
    assert "<span>Produits</span>" not in root
    assert "<span>Outils</span>" not in root
    assert 'location.replace(\'/downloads/\'' in products
    assert "Produits &amp; outils" in mail_nav


def test_quantic_studio_is_published_as_a_first_class_product():
    root = text("public/index.html")
    downloads = text("public/downloads/index.html")
    studio_mark = text("public/assets/brand-2026/studio-mark.svg")

    assert "Quantic Studio" in root
    assert 'href="/downloads/#quantic-studio"' in root
    assert 'id="quantic-studio"' in downloads
    assert "Quantic Studio 2.7.3" in downloads
    assert "QuanticStudio-Setup-2.7.3.exe" in downloads
    assert "quantic-studio-v2.7.3" in downloads
    assert "Quantic Studio" in studio_mark

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
        "public/downloads/index.html",
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
        "public/mail/index.html",
        "public/downloads/index.html",
    ):
        page = text(path)
        assert "quantic-unified.css?v=3.0" in page, path
    vision = text("public/vision/index.html")
    assert "quantic-vision-home-v8.css?v=8.0" in vision
    assert "providence-v15.css" not in vision


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


def test_all_vision_product_routes_load_their_native_visual_layer():
    native_v9 = {"alerts", "backtest", "sports", "settings", "sources", "track-record"}
    routes = (
        "alerts", "analyst", "backtest", "cameras", "causal", "crypto",
        "horizons", "intelligence", "matches", "modules", "predictions",
        "sports", "settings", "sources", "track-record",
    )
    for route in routes:
        page = text(f"public/{route}/index.html")
        if route in native_v9:
            assert "quantic-vision-v9.css?v=9.0" in page, route
            assert "quantic-vision-v7.css" not in page, route
            assert "providence-v15.css" not in page, route
        else:
            assert "quantic-unified.css?v=3.0" in page, route


def test_legacy_v14_shell_bridges_to_unified_v15_shell():
    shell = text("public/providence-v14-shell.js")
    assert "providence-v15-shell.js" in shell


def test_mail_status_is_local_to_hostinger():
    target = next(item for item in QUANTIC_SERVICE_TARGETS if item.id == "mail")
    assert target.public_url == "/mail/"
    assert target.probe_url is None


def test_hostinger_relay_activates_only_with_https_url():
    pending = {item.id: item for item in quantic_service_targets({})}
    assert pending["relay-hostinger"].state == "pending"
    assert pending["relay-hostinger"].probe_url is None

    active = {
        item.id: item
        for item in quantic_service_targets(
            {"QUANTIC_HOSTINGER_RELAY_URL": "https://relay-hostinger.example.com/"}
        )
    }
    assert active["relay-hostinger"].state == "active"
    assert active["relay-hostinger"].public_url == "https://relay-hostinger.example.com"
    assert active["relay-hostinger"].probe_url == "https://relay-hostinger.example.com/api/quantic/health"

    invalid = {
        item.id: item
        for item in quantic_service_targets(
            {"QUANTIC_HOSTINGER_RELAY_URL": "http://relay-hostinger.example.com"}
        )
    }
    assert invalid["relay-hostinger"].state == "pending"


def test_quantic_id_is_primary_entrypoint():
    root = text("public/index.html")
    identity = text("public/quantic/index.html")
    assert ">Quantic ID<" in root
    assert "<title>Quantic ID" in identity
    assert "quantic-id-runtime.js" in identity
    assert "data-quantic-id-state" in identity


def test_quantic_mail_requires_local_quantic_id_gate():
    mail = text("public/mail/index.html")
    gate = text("public/quantic-mail-id-gate.js")
    runtime = text("public/quantic-id-runtime.js")
    assert "quantic-mail-id-gate.js" in mail
    assert "127.0.0.1:47621" in runtime
    assert "identityAvailable" in runtime
    assert "window.QuanticID" in runtime
    assert "qid-mail-locked" in gate
    assert "Quantic ID requis" in gate
    assert "QuanticID.probe" in gate
    assert "sessionStorage" not in gate
