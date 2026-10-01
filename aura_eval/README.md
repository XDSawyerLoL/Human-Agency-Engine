# AURA-Eval v1

AURA-Eval is a mission-level benchmark for measuring what AURA can actually accomplish.

It is intentionally separated from the implementation code. The repository contains the benchmark contract and slot manifest, but **not the concrete holdout prompts, hidden state transitions, expected answers or secret fixtures**. Those must be supplied from an external JSONL corpus when an evaluation run is executed.

## Why the holdout is external

If the exact missions and answers are committed to the same repository that AURA can inspect, the test is not blind. AURA-Eval therefore versions 50 stable evaluation slots while generating or storing concrete instances outside the agent-visible repository.

Each slot measures one or more of:

- mission success
- factual correctness
- evidence quality
- adaptation after a condition change
- recovery after tool failure
- memory continuity
- contradiction handling
- code/test correctness
- human interventions required
- wall-clock latency
- model/tool calls
- input/output tokens
- local energy telemetry when available

## Comparison protocol

AURA and any GPT baseline must receive the same mission instance, the same starting evidence, equivalent tool permissions and the same completion criterion.

Do not infer model equivalence from token count, latency or energy alone. The primary metric is mission success; efficiency metrics are reported alongside it.

Recommended aggregate reporting:

`success_rate, verified_quality, intervention_rate, median_latency_s, model_calls, tool_calls, tokens_in, tokens_out, local_joules, estimated_remote_energy_status`

Remote provider energy must remain `unknown` unless the provider supplies a defensible measurement. Do not manufacture joule estimates from model names.

## Holdout format

The external JSONL should contain exactly one instance for each slot in `manifest.json`.

Minimum fields:

`slot_id, mission, initial_context, perturbations, success_criteria, evaluator`

Optional fields:

`fixtures, allowed_tools, max_steps, expected_artifacts, scoring_notes`

Concrete holdout files must not be committed to this repository.

## Benchmark families

The 50 slots are split across ten families: dialogue continuity, reasoning, evidence research, software engineering, long-memory use, adaptation, tool failure recovery, contradiction handling, autonomous mission pursuit and cross-domain transfer.

AURA-Eval v1 is a verification framework. It does not by itself establish AGI.
