# Évidence — Human Signal Engine

Évidence is the problem-and-action layer above HORIZON. HORIZON answers **what is happening, what may happen next, and what evidence supports it**. Évidence asks a different question: **does this repeated evidence point to a human problem that is worth testing, and what is the smallest useful response to build?**

## Invariant

```text
VERIFIED / EMERGING SIGNALS
        ↓
RECURRENCE + SOURCE DIVERSITY + PERSISTENCE
        ↓
PROBLEM SIGNAL
        ↓
UNRESOLVEDNESS HYPOTHESIS
        ↓
SOLUTION / NOVELTY SCAN REQUIRED
        ↓
ACTION OR TOOL EXPERIMENT
        ↓
FALSIFICATION TEST
```

The engine must never skip the two middle checks. A repeated problem in the world does not prove that nobody has solved it, and failure to find a solution in the current news stream does not prove novelty.

## Endpoint

```http
GET /v1/horizon/world/human-signals/opportunities
```

The endpoint reuses the HORIZON world briefing and returns ranked opportunity hypotheses. Ranking is diagnostic only.

Important output fields:

- `signal_strength.diagnostic_score`: ranking signal, **not a probability**.
- `unresolvedness.status`: currently `needs_solution_scan` until existing responses are checked.
- `novelty.status`: currently `not_assessed` until a dedicated external scan exists.
- `candidate_action`: a narrow tool/workflow archetype tied to the observed domain.
- `validation`: a falsifiable test with explicit rejection conditions.
- `evidence`: the underlying HORIZON event/hypothesis references.

## What this version deliberately does not claim

It does not claim that an opportunity is unique, globally unresolved, commercially valuable, or desired by users. Those claims require evidence that does not exist in the HORIZON event stream alone.

## Next layer: Solution Scan

The next major capability should investigate each high-ranking problem signal against independent solution spaces:

1. public services and institutional responses;
2. products and startups;
3. open-source projects and developer ecosystems;
4. academic research and trials;
5. patents where relevant;
6. forums and community workarounds.

The output should distinguish `existing_solution`, `partial_solution`, `fragmented_workaround`, `unclear`, and `credible_gap`. Only after this step may Évidence promote a problem signal into a credible unresolved opportunity.

## Product principle

Évidence should not become another news dashboard. Its useful output is a short queue of **problems worth investigating**, with the evidence for each claim, the reason the signal matters, the proposed intervention, and the observation that would prove the idea wrong.
