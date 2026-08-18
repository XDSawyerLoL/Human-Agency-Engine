# Human Agency Engine

Backend-first implementation of a personal opportunity engine. The system stores a user's declared state and durable intentions, ingests external signals, evaluates opportunities, applies CARE safety gates, and persists explainable counterfactuals.

## Core loop

`SELF -> INTENT -> SIGNAL -> OPPORTUNITY -> CARE -> IMPACT -> LEARNING`

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

OpenAPI: `http://localhost:8000/docs`

## Current real capabilities

- persistent user state
- persistent long-lived intents
- signal ingestion API
- deterministic opportunity engine baseline
- counterfactual output: baseline vs proposed action
- CARE financial safety gate
- PostgreSQL-ready via `DATABASE_URL`
- API key protection
- test coverage for the core opportunity loop

## Next engineering milestones

1. OAuth/read-only connectors (mail/calendar first)
2. signal normalizers and provenance
3. LLM reasoning layer constrained by typed outputs
4. opportunity deduplication + ranking
5. feedback/outcome table for learning
6. scheduled engine worker
7. encrypted personal vault and field-level consent

No commerce ranking or autonomous purchasing is allowed until the loyalty and consent model is implemented.
