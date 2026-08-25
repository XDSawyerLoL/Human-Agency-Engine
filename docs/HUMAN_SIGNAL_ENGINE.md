# Évidence — Human Signal Engine

Évidence is the problem-and-action layer above HORIZON. HORIZON answers **what is happening, what may happen next, and what evidence supports it**. Évidence asks a different question: **does this repeated evidence point to a human problem that is worth testing, what related work already exists, and what is the smallest useful response to build?**

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
SOLUTION SCAN
        ↓
SCOPED GAP ASSESSMENT
        ↓
ACTION OR TOOL EXPERIMENT
        ↓
FALSIFICATION TEST
```

The engine must never collapse these stages into one claim. A repeated problem in the world does not prove that nobody has solved it. A failed search does not prove novelty. A search result does not prove that a solution works.

## Problem Radar endpoint

```http
GET /v1/horizon/world/human-signals/opportunities
```

The endpoint reuses the HORIZON world briefing and returns ranked opportunity hypotheses. Ranking is diagnostic only.

Important output fields:

- `signal_strength.diagnostic_score`: ranking signal, **not a probability**.
- `unresolvedness.status`: `needs_solution_scan` until related work is investigated.
- `novelty.status`: `not_assessed`; the event stream cannot establish novelty.
- `candidate_action`: a narrow tool/workflow archetype tied to the observed domain.
- `validation`: a falsifiable test with explicit rejection conditions.
- `evidence`: the underlying HORIZON event/hypothesis references.

## Solution Scan endpoint

```http
GET /v1/horizon/world/human-signals/solution-scan?problem_key=<domain:event_type>
```

The first Solution Scan implementation queries four independent ecosystems in parallel and degrades gracefully if one source is unavailable:

- GitHub repository search — open-source and developer projects;
- OpenAlex — academic research;
- Hacker News via Algolia — startup and technology community signals;
- GDELT DOC — public web and media coverage.

The scan returns `relevance_score` values for ranking only. They are not probabilities and they do not measure solution quality.

A gap assessment requires at least **three successfully scanned ecosystems**. If fewer than three respond and there is not already strong positive evidence of existing work, the result is `insufficient_source_coverage` and Évidence refuses to infer underexploration.

Current gap statuses:

- `insufficient_source_coverage`: too few independent ecosystems responded for a credible gap assessment;
- `candidate_gap_in_scanned_sources`: at least three ecosystems responded and no sufficiently relevant work was found;
- `underexplored_in_scanned_sources`: related work is sparse despite sufficient source coverage;
- `related_work_found`: multiple relevant traces exist, but end-to-end effectiveness is unknown;
- `substantial_existing_work_found`: related work appears across several ecosystems, suggesting that the useful opportunity is more likely an integration gap, workflow gap or underserved segment than a blank space.

Every response keeps `global_novelty_verified=false` and `existing_solution_effectiveness_verified=false`.

## Current coverage boundary

This scanner is deliberately useful before it is comprehensive. It does **not yet** systematically cover product catalogs, public-service directories, patents, procurement databases or domain-specific professional communities. Those are separate evidence spaces and should be added as adapters rather than simulated from generic web results.

Accordingly, even `candidate_gap_in_scanned_sources` means only what it says: **a candidate gap inside the sources that successfully responded**.

## Product principle

Évidence should not become another news dashboard or an idea generator. Its useful output is a short queue of **problems worth investigating**, the evidence for each claim, the existing work already found, the reason the signal matters, the proposed intervention, and the observation that would prove the idea wrong.
