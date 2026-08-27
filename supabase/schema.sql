-- ÉVIDENCE / PROVIDENCE V11.1 — Supabase persistence
-- Run once in the Supabase SQL editor for the project connected to Hostinger.

create table if not exists public.evidence_runtime_state (
  state_key text primary key,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists evidence_runtime_state_updated_at_idx
  on public.evidence_runtime_state (updated_at desc);

alter table public.evidence_runtime_state enable row level security;

create table if not exists public.evidence_sports_forecasts (
  fixture_key text primary key,
  country text not null,
  league text not null,
  external_id text,
  model_id text,
  kickoff_at timestamptz,
  kickoff_date date,
  home_team text not null,
  away_team text not null,
  source text,
  p_home double precision not null,
  p_draw double precision not null,
  p_away double precision not null,
  model_pick text not null,
  model_confidence double precision not null,
  predicted_at timestamptz not null default now(),
  status text not null default 'pending' check (status in ('pending','resolved','cancelled')),
  outcome text check (outcome is null or outcome in ('home','draw','away')),
  home_score integer,
  away_score integer,
  correct boolean,
  brier double precision,
  resolved_at timestamptz
);

-- Idempotent upgrade when the V11.1 table already existed before model identity was added.
alter table public.evidence_sports_forecasts add column if not exists model_id text;

create index if not exists evidence_sports_forecasts_status_idx on public.evidence_sports_forecasts (status, kickoff_date);
create index if not exists evidence_sports_forecasts_league_idx on public.evidence_sports_forecasts (country, league, predicted_at desc);
create index if not exists evidence_sports_forecasts_model_idx on public.evidence_sports_forecasts (model_id, predicted_at desc);
create index if not exists evidence_sports_forecasts_resolved_idx on public.evidence_sports_forecasts (resolved_at desc) where status='resolved';

alter table public.evidence_sports_forecasts enable row level security;

-- No anonymous/browser policies on purpose. Hostinger writes with the server secret key.
-- fixture_key is the primary key and inserts use ignore-duplicates: the first pre-match
-- probability from the canonical production model is immutable. Result resolution updates
-- only the outcome fields and never the original p_home / p_draw / p_away values.

comment on table public.evidence_runtime_state is
  'Server-side durable mirror for ÉVIDENCE snapshots, causal learning and sports intelligence.';
comment on table public.evidence_sports_forecasts is
  'Frozen canonical pre-match Providence probabilities and later objective match resolutions for live sports calibration.';
