from pathlib import Path


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
