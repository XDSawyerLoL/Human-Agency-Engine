# HORIZON GitHub-only runtime

This is the zero-cost fallback for periods where no permanent HORIZON server is available.

It is deliberately a **batch collector**, not fake 24/7 hosting.

## Runtime contract

The workflow `.github/workflows/horizon-live.yml` chooses one of two modes:

1. **Remote watchdog** when both `ENGINE_URL` and `ENGINE_API_KEY` exist.
2. **GitHub-only fallback** when they do not.

The fallback runs on GitHub-hosted Actions, restores the latest HORIZON SQLite state artifact, applies Alembic migrations, executes one due collector cycle, uploads the updated state, then deletes the predecessor artifact.

Only one state artifact is intentionally retained at a time.

## What it gives us for free

- recurring live collection while no VPS exists;
- durable-enough short-term state between workflow runs;
- source cadence/backoff state;
- immutable raw public observations;
- GDELT discovery and credential-free official/operational sources;
- synthesis, provisional forecasts, convergence and Event Graph state;
- a real history on which HORIZON can later be evaluated.

## What it does not provide

- an always-on API;
- guaranteed exact execution time;
- permanent database durability;
- a private personal-data store;
- true continuous workers;
- production-grade backup or disaster recovery.

GitHub Actions scheduling can be delayed. This fallback must therefore never interpret workflow timing as evidence timing.

## Privacy boundary

The GitHub-only database is for **public world evidence only**.

Do not put any of the following into this state:

- personal profile/exposure data;
- Gmail, Calendar or other private connector data;
- OAuth tokens;
- private messages;
- passwords or API credentials.

Provider credentials, when eventually needed, belong only in GitHub Actions secrets and must never be persisted into observations.

## State lifecycle

The artifact name is:

`horizon-github-state`

Each successful fallback run:

1. downloads the newest non-expired artifact when one exists;
2. restores `horizon-github.db`;
3. runs `alembic upgrade head`;
4. executes `scripts/horizon_github_cycle.py`;
5. uploads the new DB plus `horizon-github-status.json`;
6. deletes the previous artifact only after the new upload succeeds.

If a run fails before upload, the previous state remains available.

## Migration to a VPS later

Nothing needs to be redesigned.

When a real HORIZON endpoint is configured through `ENGINE_URL` and `ENGINE_API_KEY`, the same workflow automatically switches back to remote-watchdog mode. The Hostinger deployment stack remains available in the repository for that future step.

The GitHub-only artifact should then be treated as a bootstrap/archive source, not as the production database.
