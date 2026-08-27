-- ÉVIDENCE / PROVIDENCE V11 — Supabase persistence mirror
-- Run once in the Supabase SQL editor for the project connected to Hostinger.

create table if not exists public.evidence_runtime_state (
  state_key text primary key,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

create index if not exists evidence_runtime_state_updated_at_idx
  on public.evidence_runtime_state (updated_at desc);

alter table public.evidence_runtime_state enable row level security;

-- No anonymous/browser policy on purpose.
-- Hostinger's Node backend writes with SUPABASE_SECRET_KEY (preferred)
-- or legacy SUPABASE_SERVICE_ROLE_KEY. Those elevated keys bypass RLS.

comment on table public.evidence_runtime_state is
  'Server-side durable mirror for ÉVIDENCE snapshots, causal learning and sports intelligence.';
