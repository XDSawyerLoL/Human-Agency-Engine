# HORIZON on Hostinger VPS

HORIZON production is a dedicated domain-agnostic personal world-intelligence service. Weather is one evidence domain among many. The production API launches `app.horizon_api:app`, not the historical `app.main:app`, so commerce, delegation, settlement, allocation and execution surfaces are not exposed by this deployment.

## Production architecture

The Hostinger Compose stack contains four long-running services:

1. `db` — PostgreSQL 17 with the persistent `horizon_postgres_data` volume.
2. `api` — dedicated HORIZON FastAPI API. Alembic upgrades run before Uvicorn starts.
3. `collector` — permanent current-world ingestion/synthesis worker with a PostgreSQL leader lease and per-source cadence/backoff.
4. `corpus-worker` — deliberately slower historical evidence worker that resumes calibration corpus slices without delaying live collection.

The database has no host port mapping. The API binds to `127.0.0.1:8000` by default and should normally sit behind a TLS reverse proxy.

Operational endpoints:

- `GET /health` — service capability/liveness summary
- `GET /ready` — database-backed readiness
- `GET /v1/horizon/collector/status` — live collector state
- `GET /v1/horizon/world/coverage` — maturity inventory across weather, hazards, mobility, supply/fuel, energy, media, geopolitics, economy/labor, health, cyber/technology, regulation/policy, financial stress and personal context

Numeric forecast probabilities remain disabled independently of deployment status.

## GitHub -> Hostinger deployment invariant

Automatic production deployment now happens **inside the same `CI` workflow that tested the commit**:

1. a commit lands on `main`;
2. `test` checks out that commit and runs Python compilation, a fresh Alembic upgrade, Hostinger Compose validation and the complete pytest suite;
3. `deploy-hostinger` has `needs: test`, so it cannot run unless that exact test job succeeds;
4. the deploy job checks out `${{ github.sha }}` from the same workflow context;
5. `hostinger/deploy-action@v1` deploys `docker-compose.hostinger.yml` for that same repository SHA.

This avoids a separate `workflow_run` context where the checked-out revision and the action's own GitHub SHA could diverge.

`.github/workflows/deploy-hostinger.yml` is now **manual-only** (`workflow_dispatch`). Use it for an intentional redeploy of the selected revision, not as a second automatic deployment path.

Both deployment paths share the concurrency group `horizon-hostinger-production`, preventing two production deployments from racing each other.

If repository variable `HOSTINGER_VM_ID` is absent, the automatic deploy job is skipped cleanly. CI still runs normally.

## Hostinger prerequisite

Use a Hostinger VPS capable of running Docker/Compose. Normal shared Web/Cloud hosting is not the target for this Python/PostgreSQL worker stack.

Create or identify the VPS first, then obtain its numeric VM ID and a Hostinger API key. Keep credentials out of commits, issues and chat messages.

## GitHub Actions configuration

Open the repository on GitHub, then:

`Settings -> Secrets and variables -> Actions`

### Required GitHub secrets

- `HOSTINGER_API_KEY` — Hostinger API key used by the deploy action
- `HORIZON_POSTGRES_PASSWORD` — long URL-safe random PostgreSQL password
- `HORIZON_API_KEY` — HORIZON API key, at least 32 characters
- `HORIZON_TOKEN_ENCRYPTION_KEY` — application encryption secret required by production runtime validation

### Optional provider secrets

- `METEOFRANCE_APPLICATION_ID`
- `WINDY_POINT_FORECAST_API_KEY`
- `HORIZON_COLLECTOR_WINDY_POINTS_JSON` — one-line JSON array of configured Windy points

A missing optional provider secret must leave that evidence path unavailable; HORIZON must never replace it with fabricated observations.

### Required GitHub variable

- `HOSTINGER_VM_ID` — numeric Hostinger VPS virtual-machine ID

### Useful GitHub variables

The workflow has safe defaults, so these are optional overrides:

- `HORIZON_BIND_ADDRESS` — default `127.0.0.1`
- `HORIZON_PORT` — default `8000`
- `HORIZON_COLLECTOR_ENABLED` — default `true`
- `HORIZON_COLLECTOR_TICK_SECONDS` — default `30`
- `HORIZON_COLLECTOR_LEASE_SECONDS` — default `900`
- `HORIZON_COLLECTOR_MAX_SOURCES_PER_CYCLE` — default `10`
- `HORIZON_COLLECTOR_SNCF_SECONDS` — default `300`
- `HORIZON_COLLECTOR_VIGICRUES_SECONDS` — default `600`
- `HORIZON_COLLECTOR_METEOFRANCE_SECONDS` — default `600`
- `HORIZON_COLLECTOR_METEOALARM_SECONDS` — default `600`
- `HORIZON_COLLECTOR_GDELT_SECONDS` — default `900`
- `HORIZON_COLLECTOR_GDACS_SECONDS` — default `900`
- `HORIZON_COLLECTOR_FUEL_SECONDS` — default `900`
- `HORIZON_COLLECTOR_RTE_SECONDS` — default `900`
- `HORIZON_COLLECTOR_WINDY_SECONDS` — default `1800`
- `HORIZON_COLLECTOR_SYNTHESIS_SECONDS` — default `900`
- `HORIZON_COLLECTOR_MAX_ACTIVE_EVENTS` — default `200`
- `HORIZON_COLLECTOR_EVENT_GRAPH_LOOKBACK_HOURS` — default `336`
- `HORIZON_COLLECTOR_METEOALARM_ALL_EUROPE` — default `false`
- `HORIZON_COLLECTOR_RTE_REGION_CODES` — optional comma-separated region codes
- `HORIZON_CORPUS_WORKER_ENABLED` — default `true`
- `HORIZON_CORPUS_WORKER_INTERVAL_SECONDS` — default `21600`
- `HORIZON_CORPUS_WORKER_LEASE_SECONDS` — default `7200`
- `HORIZON_CORPUS_WORKER_MAX_RUNS_PER_CYCLE` — default `1`
- `HORIZON_CORPUS_WORKER_SLICES_PER_RUN` — default `1`

The same names are documented in `.env.hostinger.example`.

## First deployment

Once the VPS, `HOSTINGER_VM_ID` and the four required secrets exist, no manual code upload is needed.

Merge a green PR into `main`. The `CI` workflow will run. On success, its `deploy-hostinger` job will submit the exact tested SHA to Hostinger. In Hostinger, the stack then starts in dependency order:

`PostgreSQL healthy -> API migrations/start -> /ready healthy -> collector + corpus-worker`

If the deploy job is skipped, check `HOSTINGER_VM_ID` first. If it starts but fails during authentication/deployment, check the Hostinger API key and VPS ID in GitHub settings rather than pasting them into logs or chat.

## Public hostname and TLS

The safe production default is loopback-only. Configure a reverse proxy on the VPS and route a dedicated hostname such as `horizon.example.com` to:

`http://127.0.0.1:8000`

Then:

1. point an A/AAAA record for the hostname to the VPS;
2. terminate TLS with the VPS reverse proxy (for example Traefik, Caddy or Nginx); 
3. proxy to HORIZON on loopback;
4. verify `/health`, `/ready` and `/v1/horizon/world/coverage` over HTTPS.

For a temporary direct-IP test only, `HORIZON_BIND_ADDRESS=0.0.0.0` can expose port 8000, but restrict it with the VPS firewall and return to loopback behind TLS for normal operation.

## Collector and historical-worker semantics

The permanent collector persists, per source:

- next due time
- last attempt and success
- consecutive failures
- bounded retry backoff
- last result/error

A database lease allows only one active live collector leader. Provider errors are operational failures and never become negative world evidence.

The synthesis cadence runs response-library sync, broad GDELT episode discovery, provisional reconciliation, media attention, warning refresh, materialization/expiry, personal reevaluation, convergence snapshots and Event Graph refresh.

The `corpus-worker` has a separate lease and much slower cadence. It resumes bounded historical slices for empirical calibration. Historical acquisition failure is not a prediction miss, and incomplete outcome coverage cannot authorize a negative label.

## Security invariants

- PostgreSQL remains private to the Docker network.
- protected HORIZON endpoints require `X-API-Key`.
- the production app does not mount settlement, delegation, market, allocation or execution endpoints.
- secrets remain in GitHub/Hostinger secret stores.
- broad media discovery creates hypotheses, not confirmed facts.
- source count and convergence diagnostics are not probabilities.
- deployment never enables numeric forecast probabilities.

## Data durability

The named Docker volume provides persistence across container replacement, but it is **not a backup**. Add off-VPS backups before relying on HORIZON operationally. A production-hardening step should schedule encrypted `pg_dump` exports to storage outside the VPS and periodically test restoration.

Before major schema or infrastructure changes, create a VPS/database backup.

## Local production-Compose validation

With non-production test values:

```bash
HORIZON_POSTGRES_PASSWORD=test0123456789abcdef0123456789abcdef \
HORIZON_API_KEY=test-api-key-0123456789abcdef0123456789abcdef \
HORIZON_TOKEN_ENCRYPTION_KEY=test-encryption-key \
docker compose -f docker-compose.hostinger.yml config
```

Never paste real production secrets into terminals, issues, pull requests or chat messages.
