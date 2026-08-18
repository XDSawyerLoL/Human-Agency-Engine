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

## Connect a Google account

1. Create/update a user.
2. `POST /v1/users/{external_id}/connectors/google/start`
3. Open the returned `authorization_url`.
4. Google redirects to `/v1/connectors/google/callback`.
5. Run a sync with `POST /v1/users/{external_id}/connectors/google/sync`.

The connector requests:

- `gmail.readonly`
- `calendar.readonly`

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

## Current proactive rules

The first real rules are intentionally conservative:

- A time-sensitive email is surfaced only when it also matches an active intention.
- A calendar event is surfaced only when it is within 14 days and matches an active intention.
- Existing financial and price-drop signal types remain supported.
- Every Google-derived action is read-only and marked CARE-approved only for review.

False positives are more damaging than silence at this stage. Future model-based reasoning should sit behind the same gating and CARE contracts rather than bypassing them.
