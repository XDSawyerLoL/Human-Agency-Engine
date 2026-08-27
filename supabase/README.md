# Providence V11 — Supabase durable mirror

Providence keeps MySQL as the complete relational learning store when it is available. Supabase is added in V11 as a server-side durable mirror and restart fallback for the latest world snapshot, causal-learning state and last Sports Intelligence analysis.

## 1. Create the table

Run `supabase/schema.sql` once in the Supabase SQL editor.

The table is deliberately protected by RLS and has no anonymous/browser write policy.

## 2. Hostinger environment variables

Configure these in the Hostinger Node application environment, never in frontend JavaScript and never in GitHub source:

```text
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SECRET_KEY=sb_secret_...
```

Legacy projects can use `SUPABASE_SERVICE_ROLE_KEY` instead of `SUPABASE_SECRET_KEY`, but the new server secret key is preferred.

Optional Sports Intelligence provider:

```text
FOOTBALL_DATA_API_KEY=...
```

Without that key, Providence falls back to the free TheSportsDB endpoint for upcoming fixtures when possible. Historical calibration remains based on StatsBomb Open Data.

## 3. Runtime verification

After deployment:

- `GET /api/supabase` should report `configured: true` and `connected: true`.
- `GET /api/storage` exposes both the primary learning-store state and the Supabase mirror state.
- After a world refresh, rows named `latest_snapshot` and `causal_learning` should exist in `evidence_runtime_state`.
- Opening a Sports Intelligence league mirrors `sports_intelligence` as well.

## Security boundary

The Supabase secret key is server-only and never sent to the browser. The public site only talks to Providence's own `/api/*` endpoints.
