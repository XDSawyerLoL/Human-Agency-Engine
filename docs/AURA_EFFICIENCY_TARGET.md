# AURA efficiency target v1

## Objective

AURA's efficiency target is **at least 50% less measured energy at constant mission quality**.

This is a system-level objective, not a claim about a single model, token or decoding pass. The comparison must use the same AURA-Eval holdout missions, equivalent tool permissions and the same completion criteria.

## Acceptance gate

The target is considered demonstrated only when all of the following are true on the same holdout run:

1. candidate mission success rate is not lower than the baseline;
2. verified-quality score shows no material degradation;
3. human intervention requirements do not increase;
4. the measured energy scope is explicitly stated;
5. measured energy falls by at least 50% for that same scope;
6. runs with unknown remote-provider energy are not described as end-to-end energy measurements.

If only local CPU/GPU joules are measured, the result must be labeled **local measured energy**. Remote model energy remains unknown unless the provider exposes a defensible measurement.

## Optimization order

AURA should reduce unnecessary cognition before weakening model quality:

- deterministic code and tools before LLM calls when a calculation or lookup is sufficient;
- semantic/result cache for repeated evidence and stable subproblems;
- capability routing so simple missions use smaller models and difficult missions escalate;
- retrieval before generation so models reason over compact evidence rather than repeatedly rediscovering it;
- reuse of HORIZON evidence, memory and previous verified intermediate results;
- parallel independent tool calls when ordering is not required;
- early stopping when mission success criteria are already satisfied;
- quantized local models where benchmark quality is preserved;
- speculative decoding where the selected model/runtime supports it;
- batching for compatible local inference workloads;
- bounded reflection budgets rather than unconditional repeated self-critique.

## Quality invariant

Energy optimization must never be accepted only because output looks similar.

The invariant is:

`same hidden mission -> same-or-better verified outcome -> fewer measured resources`

AURA-Eval is the authority for the mission outcome. Resource telemetry is a secondary axis.

## GPT comparison

AURA is compared to GPT baselines at the **system mission level**, not by parameter count or prose style. A comparison run must record:

- exact baseline identifier and date;
- tool permissions;
- mission success;
- verified quality;
- human interventions;
- latency;
- model calls;
- tool calls;
- input/output tokens;
- measured local joules;
- whether remote-provider energy is known or unknown.

AURA may outperform a stronger raw model on a bounded mission through memory, tools, evidence reuse and persistence. Such a result demonstrates superior performance on that benchmark, not general superiority or AGI.
