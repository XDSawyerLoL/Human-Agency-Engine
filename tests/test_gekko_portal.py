from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_gekko_portal_exists_and_is_integrated():
    portal = read("public/gekko/index.html")
    home = read("public/index.html")
    downloads = read("public/downloads/index.html")

    assert "<title>GEKKO" in portal
    assert 'id="gekko-omnibox"' in portal
    assert 'class="gekko-bottom-dock"' in portal
    assert "/assets/brand-2026/gekko-mark.svg" in portal
    assert "AURA" in portal and "/mail/" in portal and "/pulse/" in portal
    assert "/news/" in portal and "/vision/" in portal
    assert "https://github.com/Sansahd/AURA-WEB" in portal

    assert 'href="/gekko/"' in home
    assert ">GEKKO<" in home
    assert "QUANTIC GLIDE" not in home

    assert 'id="gekko"' in downloads
    assert 'href="/gekko/"' in downloads
    assert "Quantic Glide 1.2.6" not in downloads


def test_gekko_mark_keeps_earth_and_gecko():
    mark = read("public/assets/brand-2026/gekko-mark.svg")
    assert 'id="earth"' in mark
    assert 'id="gecko"' in mark
    assert 'class="continent"' in mark
    assert 'class="toe"' in mark


def test_gekko_portal_script_is_safe_and_reduced_motion_ready():
    css = read("public/gekko/gekko.css")
    js = read("public/gekko/gekko.js")
    assert "prefers-reduced-motion" in css
    assert "search.brave.com" in js
    assert "window.open" in js
