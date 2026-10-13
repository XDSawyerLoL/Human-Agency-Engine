from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_gekko_portal_exists_and_links_to_published_build():
    portal = read("public/gekko/index.html")
    home = read("public/index.html")
    downloads = read("public/downloads/index.html")

    assert "<title>GEKKO" in portal
    assert 'gekko-interface-reelle.webp' in portal
    assert 'Interface réelle GEKKO 2.4' in portal
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


def test_gekko_page_uses_authenticated_real_screenshot():
    portal = read("public/gekko/index.html")
    css = read("public/gekko/gekko-v3.css")
    image = ROOT / "public/gekko/gekko-interface-reelle.webp"

    assert image.is_file() and image.stat().st_size > 4000
    assert image.read_bytes()[:4] == b"RIFF"
    assert 'class="gekko-showcase"' in portal
    assert 'class="gekko-real-shot"' in portal
    assert 'class="gekko-real-screen"' in portal
    assert 'gekko-interface-reelle.webp' in portal
    assert 'Capture de l’application Windows' in portal
    assert 'RECONSTITUTION HTML' not in portal
    assert 'id="gekko-omnibox"' not in portal
    assert '.gekko-real-screen img' in css
    assert 'prefers-reduced-motion' in css
    assert 'radial-gradient' in css
