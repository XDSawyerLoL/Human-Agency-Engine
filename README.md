# Human Agency Engine

Backend for a proactive, user-aligned personal agency system.

The engine does not optimize engagement. Its purpose is to detect useful interventions before the user has to formulate the request, while preserving user control.

## Core loop

`SELF -> INTENT -> SIGNAL -> OPPORTUNITY -> CARE -> OUTCOME -> LEARNING`

## What is real in v0.3

- Persistent users, intentions, signals, opportunities and outcomes
- Read-only Google connector (Gmail metadata/snippets + primary Calendar events)
- OAuth 2.0 with encrypted connector tokens
- Idempotent external-signal ingestion
- Intent matching and proactive gating
- Opportunity engine with counterfactual framing
- CARE checks
- Manual and scheduled cycle runner
- SQLite for local development; PostgreSQL supported through `DATABASE_URL`
- Versioned Alembic schema migrations
- Docker migration-first startup
- Render infrastructure blueprint for Frankfurt

The Google connector intentionally does **not** send email, modify calendar events or purchase anything. It uses read-only scopes and only reads the minimum useful Gmail fields: subject, sender, date, labels and snippet.

## Setup

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env`.

Generate an encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set `TOKEN_ENCRYPTION_KEY`.

For Google integration, create a Google Cloud OAuth Web client, enable Gmail API and Google Calendar API, and set:

```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:8000/v1/connectors/google/callback
```

Run:

```bash
uvicorn app.main:app --reload
```

API docs:

`http://localhost:8000/docs`

## Database migrations

Create or upgrade a database with:

```bash
alembic upgrade head
```

The Docker image runs this automatically before starting the API. CI also upgrades a fresh database before running application tests.

## Connect a Google account

1. Create/update a user.
2. `POST /v1/users/{external_id}/connectors/google/start`
3. Open the returned `authorization_url`.
4. Google redirects to `/v1/connectors/google/callback`.
5. Run a sync with `POST /v1/users/{external_id}/connectors/google/sync`.

The connector requests:

- `gmail.readonly`
- `calendar.readonly`

On Render, `GOOGLE_REDIRECT_URI` is derived automatically from `RENDER_EXTERNAL_HOSTNAME` when no explicit override is set.

## Continuous cycle

A production scheduler can execute:

```bash
python scripts/run_cycle.py
```

The cycle:

1. syncs enabled read-only connectors,
2. ingests only unseen external items,
3. runs the opportunity engine,
4. leaves all resulting actions for human review.

The repository also contains `.github/workflows/agency-cycle.yml`. It triggers `/v1/cycle/run` hourly once these GitHub repository secrets exist:

- `ENGINE_URL` — deployed API base URL, e.g. `https://...onrender.com`
- `ENGINE_API_KEY` — same value as the deployed service's `API_KEY`

If these secrets are absent, the scheduled workflow exits successfully without doing anything.

## Render deployment

`render.yaml` defines the initial live-test infrastructure:

- Docker web service in Frankfurt
- Render Postgres in Frankfurt
- CI-gated auto-deploys
- generated API key
- generated token-encryption key
- database accessible only through Render networking

The Blueprint intentionally uses free web/database plans for the first live validation. Render's free Postgres is not a permanent production datastore and must be upgraded or moved before relying on it long term.

After the Blueprint creates the service:

1. copy the Render `API_KEY` value into the GitHub secret `ENGINE_API_KEY`;
2. set `ENGINE_URL` to the service's HTTPS URL;
3. add `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` to the Render web service when the OAuth client is ready;
4. register the callback shown by the service (`https://<host>/v1/connectors/google/callback`) in Google Cloud.

Never commit OAuth client secrets, API keys or encryption keys.

## Current proactive rules

The first real rules are intentionally conservative:

- A time-sensitive email is surfaced only when it also matches an active intention.
- A calendar event is surfaced only when it is within 14 days and matches an active intention.
- Existing financial and price-drop signal types remain supported.
- Every Google-derived action is read-only and marked CARE-approved only for review.

False positives are more damaging than silence at this stage. Future model-based reasoning should sit behind the same gating and CARE contracts rather than bypassing them.
