from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_gekko_portal_exists_and_links_to_published_build():
    portal = read("public/gekko/index.html")
    home = read("public/index.html")
    downloads = read("public/downloads/index.html")

    assert "<title>GEKKO" in portal
    assert 'id="gekko-omnibox"' in portal
    assert 'class="gekko-bottom-dock"' in portal
    assert 'data-gekko-search' in portal
    assert '/assets/brand-2026/gekko-mark.svg' in portal
    assert '/mail/' in portal and '/pulse/' in portal and '/vision/' in portal
    assert '/news/' in portal
    assert 'https://github.com/Sansahd/AURA-WEB/actions/runs/38311597450' in portal
    assert 'GEKKO-2.4-beta13-Windows-x64' in portal

    assert 'href="/gekko/"' in home
    assert '>GEKKO<' in home
    assert 'id="gekko"' in downloads
    assert 'href="/gekko/"' in downloads


def test_gekko_logo_is_real_crisp_vector_art():
    mark = read("public/assets/brand-2026/gekko-mark.svg")
    assert 'viewBox="0 0 256 256"' in mark
    assert 'id="earth"' in mark
    assert 'id="gecko"' in mark
    assert 'class="continent"' in mark
    assert 'class="toe"' in mark
    assert 'data:image/png;base64' not in mark
    assert '<circle' in mark and '<path' in mark


def test_gekko_preview_matches_actual_glass_layout():
    portal = read("public/gekko/index.html")
    css = read("public/gekko/gekko-v3.css")
    js = read("public/gekko/gekko.js")

    for marker in (
        'class="gekko-showcase"',
        'class="gekko-browser-shell"',
        'class="gekko-browser-topbar"',
        'class="gekko-scene"',
        'class="gekko-side-rail"',
        'class="gekko-bottom-dock"',
        'class="gekko-omnibox"',
        'id="gekko-omnibox"',
    ):
        assert marker in portal

    assert 'RECONSTITUTION HTML' in portal
    assert 'Maquette' not in portal or 'reconstitué' in portal
    assert 'prefers-reduced-motion' in css
    assert 'backdrop-filter' in css
    assert 'radial-gradient' in css
    assert 'drop-shadow' in css
    assert 'search.brave.com' in js
    assert 'window.open' in js
