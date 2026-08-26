# HORIZON Predictive Intelligence

HORIZON is a personal world-anticipation engine. It watches multiple real-world domains, separates facts from hypotheses, models plausible collective responses, checks personal exposure, creates auditable forecasts, then measures whether they materialized and how much lead time was achieved.

Weather is one evidence domain among many; it is not the product boundary.

## Predictive invariant

`FACT -> SOCIAL SIGNALS -> BEHAVIORAL HYPOTHESIS -> PERSONAL EXPOSURE -> FORECAST -> RESOLUTION -> LEAD TIME`

The implementation is deliberately conservative:

- raw observations are not silently upgraded into facts;
- repeated articles from one media source family cannot confirm an event by repetition;
- source-count and convergence scores are not probabilities;
- provider failures are operational failures, not negative real-world evidence;
- incomplete historical outcome coverage cannot authorize a false/miss label;
- backtests are point-in-time and reject future leakage;
- numeric forecast probabilities stay disabled until empirical calibration gates are actually satisfied.

## Current world domains

HORIZON's architecture covers:

- weather and climate
- natural hazards
- transport and mobility
- supply chains and fuel
- energy
- media and collective attention
- geopolitics and security
- economy and labor
- public health
- cyber and technology
- regulation and policy
- financial stress
- personal context and exposure

`GET /v1/horizon/world/coverage` reports the current maturity of each domain. This keeps product development honest: a domain that only has broad discovery remains visibly `discovery_only`; it is not presented as calibrated prediction.

See `docs/ARCHITECTURE_HORIZON.md` for the domain contract.

## What is running today

The HORIZON stack already includes:

- versioned source registry and immutable raw observations
- broad GDELT multi-domain discovery with episode clustering
- official/operational adapters including SNCF, Vigicrues, Météo-France, MeteoAlarm, GDACS, French fuel and RTE
- Windy as a live forecast precursor only
- multi-source independence families and convergence snapshots
- Event Graph with explicit evidence, same-episode and plausible-dependency edges
- versioned Human Response Library
- personal relevance/exposure gate
- provisional and confirmed forecast ledgers
- materialization and expiry resolution
- predictive lead-time measurement
- point-in-time Historical Backtest Factory
- empirical calibration readiness gates
- resumable heat/cold historical calibration corpus
- permanent live collector
- separate low-rate historical corpus worker

The repository also contains older Human Agency Engine modules. They remain available for development/history, but the **production HORIZON service uses `app.horizon_api:app`** and intentionally does not mount legacy settlement, delegation, market, allocation or execution routes.

## Zero-cost GitHub-only runtime

Until a permanent server is available, HORIZON can run directly from this public GitHub repository through `.github/workflows/horizon-live.yml`.

When `ENGINE_URL` and `ENGINE_API_KEY` are absent, the workflow automatically uses **GitHub-only fallback mode**:

- one scheduled collection cycle runs every hour at minute 23;
- the previous SQLite state is restored from the latest Actions artifact;
- Alembic migrations are applied before collection;
- the updated state is uploaded as `horizon-github-state`;
- the predecessor artifact is deleted only after the new state is safely uploaded;
- only public world-intelligence data belongs in this fallback state.

This provides recurring collection and short-term continuity at zero infrastructure cost, but it is not an always-on API and GitHub scheduling is not guaranteed to be exact.

When a permanent HORIZON endpoint is later configured, the same workflow automatically switches back to remote-watchdog mode. No architecture rewrite is required.

See `docs/GITHUB_ONLY_HORIZON.md` for the runtime and privacy contract.

## Production on Hostinger

Production is a four-service Docker Compose stack:

1. PostgreSQL 17
2. dedicated HORIZON FastAPI API
3. permanent live collector
4. historical corpus worker

The database is private to the Docker network. The API binds to VPS loopback by default and should be exposed through a TLS reverse proxy.

Automatic deployment is CI-gated in `.github/workflows/ci.yml`:

`push main -> compile -> migrations -> Compose validation -> full pytest -> deploy same github.sha to Hostinger`

The separate `Redeploy HORIZON to Hostinger` workflow is manual-only.

Full setup, required GitHub secrets/variables and reverse-proxy guidance:

`docs/HOSTINGER_HORIZON.md`

## Required deployment secrets

Store these in GitHub Actions secrets, never in the repository:

- `HOSTINGER_API_KEY`
- `HORIZON_POSTGRES_PASSWORD`
- `HORIZON_API_KEY`
- `HORIZON_TOKEN_ENCRYPTION_KEY`

The required GitHub Actions variable is:

- `HOSTINGER_VM_ID`

Optional provider credentials and collector/corpus-worker overrides are documented in `.env.hostinger.example` and `docs/HOSTINGER_HORIZON.md`.

If `HOSTINGER_VM_ID` is absent, tests still run and the production deploy job is skipped cleanly.

## Local development

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Run migrations:

```bash
alembic upgrade head
```

Run the dedicated HORIZON API:

```bash
uvicorn app.horizon_api:app --reload
```

Then open:

- `http://127.0.0.1:8000/health`
- `http://127.0.0.1:8000/ready`
- `http://127.0.0.1:8000/docs`

Protected endpoints require the configured `X-API-Key` outside the development `change-me` configuration.

## Validation

The repository CI runs:

```bash
python -m compileall -q app scripts migrations
alembic upgrade head
docker compose -f docker-compose.hostinger.yml config
pytest -q
```

A production merge is not considered deployable until all four checks pass.

## Current calibration boundary

HORIZON has historically calibratable trigger/outcome mechanisms for regional extreme heat and extreme cold using official Météo-France archives and historical RTE load outcomes. Those mechanisms are useful calibration laboratories, not the scope of the product.

Broader domains are being expanded by adding independent factual/operational sources and timestamped outcome streams rather than merely adding more news feeds. The goal is to measure whether multi-domain convergence actually improves precision and useful lead time.

## Web cockpit

HORIZON now ships its own responsive web interface from the same FastAPI/Hostinger deployment.

- `/` redirects to `/ui/`
- `/ui/` is the HORIZON predictive cockpit
- `/v1/horizon/world/briefing` powers the unified world view
- `/docs` remains the technical API documentation

The cockpit groups weather, natural hazards, social/collective behavior, economy/labor, supply/fuel, energy, geopolitics, public health, cyber/technology, regulation and financial stress on the same epistemic surface. Confirmed events, emerging hypotheses and forecasts are visually separated. Diagnostic scores are never rendered as calibrated probabilities.

The web assets are copied into the existing HORIZON Docker image; no Node build, Vercel deployment or additional paid hosting layer is required.

The Hostinger Compose stack also publishes the ÉVIDENCE public dashboard through its dedicated Nginx service:

- `/` — live forecast dashboard backed by the generated `evidence-live.json` snapshot;
- `/cameras/` — WORLD EYE catalog of public live cameras across six world regions;
- each camera keeps a direct link to its external broadcaster if the embedded player is unavailable.

The camera feeds are an observational surface only. They are not ingested as forecast evidence and never alter a model probability automatically.
