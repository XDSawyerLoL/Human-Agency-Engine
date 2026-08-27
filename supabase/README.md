# Providence V11.1 — Supabase durable mirror & Sports Track Record

Providence keeps MySQL as the complete relational learning store when it is available. Supabase is the server-side durable mirror for world state and, in V11.1, the immutable pre-match Sports Track Record.

## 1. Create / upgrade the tables

Run `supabase/schema.sql` in the Supabase SQL editor after deploying V11.1, even if the V11 schema had already been executed.

It creates or upgrades:

- `evidence_runtime_state` — latest world snapshot, causal-learning state and Sports Intelligence state;
- `evidence_sports_forecasts` — first published probabilities for future matches, canonical model identity, kickoff, final result, correctness and Brier score.

Both tables are protected by RLS and intentionally have no anonymous/browser write policy.

## 2. Hostinger environment variables

Configure these in the Hostinger Node application environment, never in frontend JavaScript and never in GitHub source:

```text
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_API_KEY=sb_secret_...
```

Providence also accepts `SUPABASE_SECRET_KEY` and, for legacy projects, `SUPABASE_SERVICE_ROLE_KEY`.

No paid sports key is required for the main European live proof loop. Providence uses OpenFootball for current/previous-season schedules and final results on supported leagues, and StatsBomb Open Data for selectable historical backtests. `FOOTBALL_DATA_API_KEY` remains an optional secondary fixture provider.

## 3. What V11.1 persists

For each trackable future match Providence stores the first canonical pre-match forecast only:

- stable `fixture_key`;
- `model_id` of the canonical production model;
- home/draw/away probabilities;
- predicted pick and confidence;
- prediction timestamp and kickoff;
- later: final score, objective outcome, correct/incorrect verdict and multiclass Brier score.

Duplicate inserts use `ignore-duplicates`, so a later page request cannot rewrite the probability after the fact. Matches whose kickoff has already passed are rejected from the registry. Fallback fixtures without a reliable result source can be displayed as exploratory but are excluded from the official Track Record.

## 4. Automatic collection

The Hostinger Node process seeds and resolves the main supported leagues automatically after boot and then once per hour. The calibration corpus therefore continues to grow even when nobody has the Sports page open.

## 5. Runtime verification

After deployment:

- `GET /api/supabase` should report `configured: true` and `connected: true`;
- `GET /api/storage` exposes both primary storage and the Supabase mirror state;
- `evidence_runtime_state` should contain `latest_snapshot` and `causal_learning` after refresh;
- `evidence_sports_forecasts` should begin receiving `pending` future matches, then convert them to `resolved` after results are published;
- `/sports/` displays the live count, live Brier, live top-pick accuracy and recent verdicts separately from the historical StatsBomb backtest.

## Security boundary

The Supabase secret key is server-only and never sent to the browser. The public site only talks to Providence's own `/api/*` endpoints. Never commit the real key to GitHub, logs, screenshots or client-side JavaScript.
