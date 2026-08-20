# HORIZON on Hostinger VPS

HORIZON is deployed as a dedicated FastAPI service, a permanent world-intelligence collector and PostgreSQL. The production API launches `app.horizon_api:app`, not the historical `app.main:app`, so commerce, delegation, settlement and other non-HORIZON surfaces are not exposed by this deployment.

## Architecture

- `api`: dedicated HORIZON FastAPI container
- `collector`: permanent HORIZON ingestion/synthesis worker
- `db`: PostgreSQL 17 with a persistent Docker volume
- database port: internal Docker network only
- API: binds to `127.0.0.1:8000` by default on the VPS
- schema upgrades: Alembic runs before Uvicorn starts
- collector startup: waits for the API readiness check, so migrations are complete before collection begins
- liveness: `GET /health`
- readiness: `GET /ready` verifies the database
- collector observability: `GET /v1/horizon/collector/status`
- deployment: GitHub Actions runs only after the repository CI succeeds on `main`

The collector is the primary live engine. The old 15-minute GitHub radar has been reduced to an hourly watchdog. It may request a due cycle, but PostgreSQL lease ownership keeps it in standby while the Hostinger worker is healthy.

## Collector behavior

The collector keeps persistent state for each source:

- next due time
- last attempt
- last successful observation
- consecutive failures
- bounded exponential retry backoff
- last result/error

Collection cadence is source-specific. Default production values are intentionally more frequent for transport/flood alerts and less aggressive for Windy. Cadence is an operational scheduling choice and is never treated as evidence strength or probability.

A database lease allows one active collector leader. If another worker or the GitHub watchdog tries to collect while the lease is valid, it returns `standby`. If the leader disappears, the lease expires and another worker can resume due work.

Every non-idle collection cycle is written to an immutable operational ledger with due sources, source outcomes, post-processing result and duration. This provides the audit trail needed to distinguish provider failure from absence of evidence.

The synthesis cadence also runs the internal predictive pipeline: Human Response Library sync, GDELT emerging-event clustering, provisional reconciliation, media-attention refresh, warning refresh, materialization scan, expiry scan, personal reevaluation, convergence snapshots and Event Graph refresh. Numeric forecast probabilities remain disabled.

## Hostinger prerequisite

Use a Hostinger VPS with the Docker template / Docker Manager. The normal Web/Cloud hosting product is not the target for this Python service.

## GitHub Actions configuration

Repository → Settings → Secrets and variables → Actions.

### Secrets

- `HOSTINGER_API_KEY`: generated in Hostinger hPanel API settings
- `HORIZON_POSTGRES_PASSWORD`: long URL-safe random password; hex is a simple safe choice
- `HORIZON_API_KEY`: random secret of at least 32 characters
- `HORIZON_TOKEN_ENCRYPTION_KEY`: application encryption secret
- `METEOFRANCE_APPLICATION_ID`: optional until that provider is enabled in production
- `WINDY_POINT_FORECAST_API_KEY`: optional until Windy production evidence is enabled
- `HORIZON_COLLECTOR_WINDY_POINTS_JSON`: optional JSON array of Windy observation points

Never commit any of these values.

### Variables

Required for deployment:

- `HOSTINGER_VM_ID`: Hostinger VPS numeric virtual-machine ID
- `HORIZON_BIND_ADDRESS`: normally `127.0.0.1`
- `HORIZON_PORT`: normally `8000`

Optional collector overrides:

- `HORIZON_COLLECTOR_ENABLED`
- `HORIZON_COLLECTOR_TICK_SECONDS`
- `HORIZON_COLLECTOR_LEASE_SECONDS`
- `HORIZON_COLLECTOR_SNCF_SECONDS`
- `HORIZON_COLLECTOR_VIGICRUES_SECONDS`
- `HORIZON_COLLECTOR_METEOFRANCE_SECONDS`
- `HORIZON_COLLECTOR_METEOALARM_SECONDS`
- `HORIZON_COLLECTOR_GDELT_SECONDS`
- `HORIZON_COLLECTOR_GDACS_SECONDS`
- `HORIZON_COLLECTOR_FUEL_SECONDS`
- `HORIZON_COLLECTOR_RTE_SECONDS`
- `HORIZON_COLLECTOR_WINDY_SECONDS`
- `HORIZON_COLLECTOR_SYNTHESIS_SECONDS`
- `HORIZON_COLLECTOR_METEOALARM_ALL_EUROPE`
- `HORIZON_COLLECTOR_RTE_REGION_CODES`

Empty optional variables fall back to the defaults in `docker-compose.hostinger.yml`.

The deploy job is skipped while `HOSTINGER_VM_ID` is absent. This lets the repository merge deployment support before the VPS credentials are configured.

## Deployment flow

1. A change is merged into `main`.
2. The existing `CI` workflow compiles Python, validates all Alembic migrations, validates the Hostinger Compose file and runs the complete test suite.
3. Only if CI succeeds, `Deploy HORIZON to Hostinger` checks out that exact validated commit.
4. `hostinger/deploy-action@v1` sends `docker-compose.hostinger.yml` and the configured environment variables to the VPS.
5. PostgreSQL starts and becomes healthy.
6. The API container applies migrations and starts only after PostgreSQL is healthy.
7. `/ready` must return HTTP 200 before the API container becomes healthy.
8. The collector starts and begins source-specific due scheduling.

A manual `workflow_dispatch` is also available for an intentional redeploy.

## First public endpoint

The safe default is loopback-only. Put a reverse proxy in front of HORIZON and route a dedicated hostname such as `horizon.example.com` to `http://127.0.0.1:8000`.

Hostinger Docker Manager supports reverse-proxy setups such as Traefik. If the VPS already runs other applications, reuse its existing reverse proxy instead of competing for ports 80/443.

DNS:

1. Create an A record for the chosen HORIZON hostname pointing to the VPS public IP.
2. Configure the reverse proxy with TLS/Let's Encrypt.
3. Proxy to `127.0.0.1:8000`.
4. Verify `https://<hostname>/health` and `https://<hostname>/ready`.

For a temporary direct-IP test only, set `HORIZON_BIND_ADDRESS=0.0.0.0` and restrict the VPS firewall to trusted IPs. Return to loopback once the reverse proxy is configured.

## Security invariants

- PostgreSQL has no host port mapping.
- Protected HORIZON endpoints retain the `X-API-Key` check.
- `/health` and `/ready` reveal only service/database availability.
- the dedicated production app must not expose settlement, delegation, market, allocation or execution endpoints.
- provider credentials and database credentials live only in secret stores.
- source failures are isolated and retained as operational failures; they are not converted into negative real-world evidence.
- do not enable numeric forecast probabilities merely because the service is deployed; HORIZON calibration readiness gates remain authoritative.

## Data durability

`horizon_postgres_data` is a named Docker volume. Container replacement therefore does not erase PostgreSQL data. VPS snapshots/backups are still required; the Docker volume is persistence, not a backup strategy.

Before any major schema or infrastructure migration, create a VPS/database backup. A later production-hardening step should add scheduled `pg_dump` exports to storage outside the VPS.

## Local validation of the production compose file

With safe test secrets present in the shell:

```bash
HORIZON_POSTGRES_PASSWORD=test0123456789abcdef0123456789abcdef \
HORIZON_API_KEY=test-api-key-0123456789abcdef0123456789abcdef \
HORIZON_TOKEN_ENCRYPTION_KEY=test-encryption-key \
docker compose -f docker-compose.hostinger.yml config
```

Do not paste production values into terminals, issues, pull requests or chat messages.
