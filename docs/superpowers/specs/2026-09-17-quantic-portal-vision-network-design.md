# Quantic Portal + Quantic Vision + Quantic Network — Design

## Goal

Turn the current Providence public site into the single public entry point for the Quantic ecosystem while keeping the underlying services isolated and independently recoverable.

The public root becomes **Quantic**. Providence/HORIZON becomes **Quantic Vision**. Quantic Mail is accessible from the same portal. Quantic Network status is visible from the same portal, and Hostinger is prepared to become an additional Quantic relay without making the public web process itself the relay.

## Product model

The user sees one product family:

- **Quantic Vision** — world intelligence, forecasting, early warning, personal exposure and the historical Providence/HORIZON capabilities.
- **Quantic Mail** — encrypted Quantic-to-Quantic messaging.
- **Quantic Network** — identities, relay mesh, direct transport and node health.
- **Quantic Ecosystem** — Quantic OS, Quantic Glide and future Quantic services.

Internally these remain separate services with explicit boundaries.

## Public information architecture

### `/` — Quantic public landing page

The current Providence landing page moves to `/vision/`.

The new root must answer three questions immediately:

1. What is Quantic?
2. What can I do with it?
3. How do I enter the unified workspace?

Primary actions:

- `Entrer dans Quantic` → `/quantic/`
- `Découvrir Quantic Vision` → `/vision/`

Primary product cards:

- Vision → `/vision/`
- Mail → `/mail/`
- Network → `/network/`
- Ecosystem → `/products/`

### `/quantic/` — unified dashboard

The dashboard is the operational entry surface after the public landing page. It contains four concise cards:

- Vision summary and entry point
- Mail summary and entry point
- Network status and entry point
- Ecosystem/products entry point

No backend secret is embedded into the page.

### `/vision/` — Quantic Vision

This page preserves the current Providence public experience and reframes it as Quantic Vision.

Existing deep routes stay valid, including current predictions, alerts, analyst, cameras, track record and other public Providence surfaces.

Providence remains visible as the founding technology/history of Quantic Vision, but is no longer presented as a separate competing top-level product. The shared Providence shell uses `/vision/` as its internal home route and displays Quantic Vision at product level.

### `/mail/` — Quantic Mail inside the portal

Phase 1 uses a same-portal shell that embeds the existing Quantic Mail web app in a sandboxed cross-origin frame when allowed by the remote app and always exposes a direct fallback button.

The shell must never receive, inspect or persist private Quantic Mail key material.

A later same-origin native integration may replace the frame without changing the route or user-facing navigation.

### `/network/` — Quantic Network status

Shows service reachability and configured topology without exposing secrets or private keys.

Initial visible nodes:

- Render relay
- Railway relay
- Hostinger relay slot (reported as pending until actually deployed)
- Quantic Mail application
- Quantic Vision runtime

Status is obtained from a same-origin portal API. Browser-side code does not probe arbitrary URLs directly.

### `/products/` — ecosystem catalogue

Presents Quantic Vision, Mail, Network, Glide, OS and Providence history in one coherent product family.

## Navigation

Desktop global navigation:

- Quantic logo/home
- Vision
- Mail
- Network
- Produits
- `Entrer dans Quantic`

Mobile keeps the same primary product access with a compact layout.

The existing Providence-specific navigation remains inside Vision pages where useful, but its home link returns to `/vision/`, not the global Quantic root.

## Visual direction

The site keeps the dark, high-contrast visual language already used by Providence but removes the impression of multiple unrelated brands.

Design rules:

- one Quantic wordmark at ecosystem level;
- restrained glass/translucent surfaces;
- no decorative dashboard overload;
- clear hierarchy before animation;
- status colors have textual labels, never color alone;
- responsive layout from narrow mobile to desktop;
- reduced-motion support;
- keyboard-focus states on all actionable controls;
- no fake metrics or fabricated network health.

## Service architecture

The repository currently has two supported Hostinger runtime paths. The public contract is intentionally identical across both so the product does not need another rewrite when infrastructure evolves.

### Current Hostinger Node Web App

```text
Public browser
    |
    v
Hostinger managed Node app
    |-- Express static `public/`
    |-- /api/quantic-portal/status
    |      \-- fixed allowlist probes
    |
    +--> Quantic Mail web app (cross-origin embedded/fallback link)

Providence / Vision Node runtime
    |-- existing prediction APIs
    |-- analyst / timeline / alert surfaces
    +-- Quantic portal status route installed before the catch-all
```

### Prepared Hostinger VPS / Compose path

```text
Public browser
    |
    v
Hostinger Nginx public web
    |-- static portal pages
    |-- /api/quantic-portal/* --> HORIZON/FastAPI API
    |
    +--> Quantic Mail web app (cross-origin embedded/fallback link)

HORIZON/FastAPI API
    |-- existing Vision/HORIZON endpoints
    +-- Quantic portal status endpoint
          |-- probes fixed allowlisted services only
          |-- never accepts a user-provided URL
```

### Quantic Network

```text
Quantic Network
    |-- Render relay
    |-- Railway relay
    +-- Hostinger relay (separate long-running service, added in a later deployment task)
```

Neither the Hostinger Node web process nor the Hostinger public Nginx process is itself a Quantic relay. The Hostinger relay must run as a separate process/container so a portal restart cannot erase, replace or impersonate relay state.

## Quantic portal status API

Public same-origin endpoint:

`GET /api/quantic-portal/status`

Runtime implementations:

- current managed Node deployment serves it directly;
- VPS/Compose deployment proxies it to FastAPI `GET /v1/quantic/portal/status`.

Both return the same public shape:

```json
{
  "status": "ok",
  "services": [
    {
      "id": "vision",
      "label": "Quantic Vision",
      "kind": "vision",
      "reachable": true,
      "url": "/vision/"
    }
  ]
}
```

Rules:

- service targets are an immutable server-side allowlist;
- outbound probes have a strict timeout;
- failures are returned as `reachable: false`, not as a portal-wide 500;
- no exception body, credential, connection string or stack trace is returned;
- the endpoint itself does not claim cryptographic security or audit status;
- Hostinger relay is `pending` until a real relay service exists.

## Quantic Mail integration

The portal uses the existing public Quantic Mail application URL as the initial application surface.

The Mail page includes:

- full-height embedded application area when framing is permitted;
- visible direct-open fallback;
- short explanation that the Mail app is a separate encrypted service;
- no duplicated login or key-entry UI in the portal.

The portal must not proxy message plaintext, private identity material or private device keys through either Vision runtime.

## Vision preservation

The existing public Providence homepage is preserved under `/vision/` before the root is replaced.

Existing data-backed public pages remain in place. The migration does not delete or rename their URLs in this phase.

The current HORIZON API and its `/ui/` cockpit remain available for operator use on the VPS/Compose path.

## Hostinger relay boundary

A Hostinger Quantic relay is part of the target architecture, but it is implemented as a separate deployment unit from this portal change.

Requirements for that relay task:

- run QuanticMail standalone relay code, not a reimplementation;
- unique relay identity secret;
- independent persistent database/volume from other relay processes;
- bootstrap to Render and Railway;
- publish a stable HTTPS public endpoint;
- add the Hostinger endpoint to QuanticMail client bootstrap configuration only after live verification;
- preserve Render and Railway during migration so Hostinger is additive, not a cutover dependency.

## Failure behaviour

- Vision unavailable: portal still loads where the static web surface is available; Vision card reports unavailable; Mail and Network links remain visible.
- Mail web app unavailable: Mail shell keeps a direct retry/fallback action; Vision still works.
- one relay unavailable: Network page marks that node unavailable; other relays remain listed.
- status API unavailable: portal renders products normally and displays status as unknown rather than hiding services.
- JavaScript disabled: landing-page navigation remains usable through normal anchors.

## Security

- no secrets in static assets;
- no relay private keys in the portal repository;
- no user-controlled URL probing;
- no Quantic Mail private key handling in the Vision backend;
- cross-origin Mail integration is isolated by browser origin boundaries;
- HORIZON API key remains scoped to HORIZON operator functions and is not reused as Quantic identity.

## Testing

Tests verify:

- public root contains Quantic navigation and required product routes;
- `/vision/` preserves the former Providence landing experience;
- Vision deep-route navigation returns to `/vision/` and identifies the product as Quantic Vision;
- `/quantic/`, `/mail/`, `/network/`, `/products/` all exist and expose their required primary controls;
- portal status services have a fixed allowlist and fail-closed error normalization;
- current Hostinger Node runtime serves `/api/quantic-portal/status` as JSON before the catch-all;
- Nginx exposes the same-origin status API path to the internal FastAPI service on the VPS path;
- current HORIZON/Python suite, Node product smoke tests and Compose validation remain green.

## Deployment

This work lands through a feature branch and pull request. Existing CI must pass before merge.

The first production deployment changes the public site and status surface only. It does not remove Render or Railway relay infrastructure.

The Hostinger relay is the next infrastructure task after the portal is live and verified.