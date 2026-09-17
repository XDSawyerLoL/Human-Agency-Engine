# Quantic Portal + Vision + Network Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Providence public root with a unified Quantic portal, preserve Providence as Quantic Vision, integrate Quantic Mail as a portal surface, and expose safe live Quantic Network/service status.

**Architecture:** The Hostinger Nginx `web` service continues to serve static pages from `public/`. HORIZON/FastAPI remains an isolated API/collector stack and gains one allowlisted status endpoint. Existing Providence pages are preserved; only the public root changes role. Quantic Mail remains a separate encrypted application and is embedded cross-origin with a direct fallback link.

**Tech Stack:** Static HTML/CSS/vanilla JS, Nginx 1.27, Python 3.12, FastAPI, urllib, pytest, Docker Compose.

**Spec:** `docs/superpowers/specs/2026-09-17-quantic-portal-vision-network-design.md`

## Global Constraints

- Root `/` is Quantic, not Providence.
- Current Providence homepage is preserved at `/vision/`.
- Existing Providence deep routes are not renamed or deleted.
- No Quantic Mail private key or message plaintext is processed by the HORIZON API.
- Portal service probing uses a fixed server-side allowlist only.
- Hostinger relay is displayed as pending until a real relay service has been deployed and verified.
- Render and Railway relays stay active during this change.
- No new paid platform or frontend framework is introduced.

---

### Task 1: Add red portal contract tests

**Files:**
- Create: `tests/test_quantic_portal.py`

**Interfaces:**
- Consumes: repository files under `public/` and `hostinger/evidence-nginx.conf`
- Produces: executable acceptance contract for public routes and Nginx status proxy

- [ ] **Step 1: Write failing static-route tests**

```python
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
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `pytest -q tests/test_quantic_portal.py`

Expected: FAIL because `/vision/`, `/quantic/`, `/mail/`, `/network/`, `/products/` and the proxy do not exist yet, and root is still Providence.

- [ ] **Step 3: Commit the red tests**

```bash
git add tests/test_quantic_portal.py
git commit -m "test: define Quantic portal public contract"
```

---

### Task 2: Build the static Quantic portal and preserve Vision

**Files:**
- Modify: `public/index.html`
- Create: `public/vision/index.html`
- Create: `public/quantic/index.html`
- Create: `public/mail/index.html`
- Create: `public/network/index.html`
- Create: `public/products/index.html`
- Create: `public/quantic.css`
- Create: `public/quantic.js`

**Interfaces:**
- Consumes: existing Providence assets and public deep routes
- Produces: public Quantic landing, dashboard, Vision landing, Mail shell, Network status shell and product catalogue

- [ ] **Step 1: Copy the current Providence root into `public/vision/index.html`**

Preserve existing Providence CSS/JS references and prediction/alert links. Change the ecosystem-level brand copy to `Quantic Vision` while keeping Providence identified as the founding engine.

- [ ] **Step 2: Replace `public/index.html` with the Quantic landing page**

Required anchors are literal normal links so navigation still works without JavaScript:

```html
<a href="/quantic/">Entrer dans Quantic</a>
<a href="/vision/">Découvrir Quantic Vision</a>
<a href="/mail/">Quantic Mail</a>
<a href="/network/">Quantic Network</a>
<a href="/products/">Produits</a>
```

- [ ] **Step 3: Add the unified `/quantic/` dashboard**

Render exactly four primary cards: Vision, Mail, Network, Ecosystem. The Network card contains a status element with `data-quantic-status-summary` for `quantic.js`.

- [ ] **Step 4: Add the `/mail/` integration shell**

Use a full-height cross-origin iframe and an always-visible direct fallback:

```html
<iframe
  class="mail-frame"
  src="https://quanticmail.onrender.com"
  title="Quantic Mail"
  loading="eager"
  referrerpolicy="no-referrer"
></iframe>
<a class="button secondary" href="https://quanticmail.onrender.com" target="_blank" rel="noopener noreferrer">Ouvrir Quantic Mail directement</a>
```

Do not request or store keys in the portal.

- [ ] **Step 5: Add `/network/` and `/products/`**

`/network/` contains cards with `data-service-id="vision"`, `mail`, `relay-render`, `relay-railway`, and `relay-hostinger`.

`/products/` lists Vision, Mail, Network, Glide and OS and states that Providence is the founding technology of Vision.

- [ ] **Step 6: Add shared responsive styling**

`public/quantic.css` provides the Quantic shell, responsive product grids, focus-visible outlines, reduced-motion support and status states. Avoid framework dependencies.

- [ ] **Step 7: Add shared portal JavaScript**

`public/quantic.js` fetches `/api/quantic-portal/status`, updates only elements with matching `data-service-id`, and falls back to `État inconnu` on any request/parsing failure. It must never hide a product because status failed.

- [ ] **Step 8: Run static contract tests**

Run: `pytest -q tests/test_quantic_portal.py`

Expected: only the Nginx/status backend-related assertion may still fail; static page assertions PASS.

- [ ] **Step 9: Commit static portal**

```bash
git add public tests/test_quantic_portal.py
git commit -m "feat: add unified Quantic public portal"
```

---

### Task 3: Add allowlisted Quantic portal status backend

**Files:**
- Create: `app/quantic_portal_status.py`
- Create: `app/routers/quantic_portal.py`
- Modify: `app/horizon_api.py`
- Modify: `tests/test_quantic_portal.py`

**Interfaces:**
- Produces: `GET /v1/quantic/portal/status`
- Internal function: `build_portal_status(probe: Callable[[ServiceTarget], dict] = probe_service) -> dict`
- Internal type: `ServiceTarget(id, label, kind, probe_url, public_url, state="active")`

- [ ] **Step 1: Extend tests with a failing backend contract**

```python
from app.quantic_portal_status import QUANTIC_SERVICE_TARGETS, build_portal_status


def test_status_targets_are_fixed_and_include_current_network():
    ids = {target.id for target in QUANTIC_SERVICE_TARGETS}
    assert ids == {"vision", "mail", "relay-render", "relay-railway", "relay-hostinger"}


def test_status_normalizes_probe_failure_without_failing_payload():
    def fake_probe(target):
        if target.id == "relay-render":
            raise TimeoutError("offline")
        return {"reachable": True, "http_status": 200}

    payload = build_portal_status(probe=fake_probe)
    services = {item["id"]: item for item in payload["services"]}
    assert payload["status"] == "ok"
    assert services["relay-render"]["reachable"] is False
    assert "offline" not in str(services["relay-render"])
    assert services["relay-hostinger"]["state"] == "pending"
```

- [ ] **Step 2: Run and verify RED**

Run: `pytest -q tests/test_quantic_portal.py -k status`

Expected: import failure because `app.quantic_portal_status` does not exist.

- [ ] **Step 3: Implement minimal status model**

`app/quantic_portal_status.py` defines a frozen dataclass, fixed HTTPS targets for Quantic Mail, Render and Railway, a local Vision target, and a Hostinger pending target. `build_portal_status` catches all probe exceptions and emits only sanitized availability metadata.

- [ ] **Step 4: Add the FastAPI router**

```python
from fastapi import APIRouter
from ..quantic_portal_status import build_portal_status

router = APIRouter(prefix="/quantic/portal", tags=["quantic-portal"])

@router.get("/status")
def quantic_portal_status():
    return build_portal_status()
```

Import this router in `app/horizon_api.py` and add it to `HORIZON_ROUTERS`, which are already mounted under `/v1`.

- [ ] **Step 5: Run focused tests**

Run: `pytest -q tests/test_quantic_portal.py`

Expected: backend tests PASS; Nginx proxy assertion still fails until Task 4.

- [ ] **Step 6: Commit backend**

```bash
git add app/quantic_portal_status.py app/routers/quantic_portal.py app/horizon_api.py tests/test_quantic_portal.py
git commit -m "feat: expose safe Quantic portal service status"
```

---

### Task 4: Wire Nginx same-origin API access

**Files:**
- Modify: `hostinger/evidence-nginx.conf`

**Interfaces:**
- Consumes: internal Compose hostname `api:8000`
- Produces: public `/api/quantic-portal/*` proxy to FastAPI `/v1/quantic/portal/*`

- [ ] **Step 1: Add the proxy before the catch-all location**

```nginx
location /api/quantic-portal/ {
    proxy_pass http://api:8000/v1/quantic/portal/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_connect_timeout 3s;
    proxy_read_timeout 8s;
    add_header Cache-Control "no-store" always;
}
```

- [ ] **Step 2: Run portal tests**

Run: `pytest -q tests/test_quantic_portal.py`

Expected: PASS.

- [ ] **Step 3: Validate Compose**

Run:

```bash
HORIZON_POSTGRES_PASSWORD=test0123456789abcdef0123456789abcdef \
HORIZON_API_KEY=test-api-key-0123456789abcdef0123456789abcdef \
HORIZON_TOKEN_ENCRYPTION_KEY=test-encryption-key \
docker compose -f docker-compose.hostinger.yml config >/dev/null
```

Expected: exit 0.

- [ ] **Step 4: Commit proxy**

```bash
git add hostinger/evidence-nginx.conf
git commit -m "feat: proxy Quantic portal status through Hostinger web"
```

---

### Task 5: Full verification and PR

**Files:**
- Modify if needed: `README.md`

**Interfaces:**
- Produces: reviewable feature branch with green CI

- [ ] **Step 1: Update README public-surface documentation**

Document `/`, `/quantic/`, `/vision/`, `/mail/`, `/network/`, `/products/` and the status endpoint. Do not claim the Hostinger relay is live yet.

- [ ] **Step 2: Run full local verification**

```bash
python -m compileall -q app scripts migrations
rm -f test.db
DATABASE_URL=sqlite:///./test.db API_KEY=change-me pytest -q
HORIZON_POSTGRES_PASSWORD=test0123456789abcdef0123456789abcdef \
HORIZON_API_KEY=test-api-key-0123456789abcdef0123456789abcdef \
HORIZON_TOKEN_ENCRYPTION_KEY=test-encryption-key \
docker compose -f docker-compose.hostinger.yml config >/dev/null
```

Expected: all commands exit 0.

- [ ] **Step 3: Open PR against `main`**

PR title: `Quantic Portal — unify Vision, Mail and Network`

- [ ] **Step 4: Wait for GitHub CI and inspect failures if any**

Expected: CI test job green.

- [ ] **Step 5: Merge only after green verification**

After merge, verify the public Hostinger deployment mechanism available to the repository/account before claiming the site is live.

---

## Follow-on infrastructure plan

After this plan is merged and the portal is verified, create a separate implementation plan for the Hostinger Quantic relay. That plan will package the existing QuanticMail standalone relay as a reusable container, run it as its own Hostinger service with persistent encrypted identity, bootstrap it to Render/Railway, and only then change the Network page from `pending` to live.