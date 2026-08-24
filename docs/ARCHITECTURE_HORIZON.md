# HORIZON — world-intelligence architecture

HORIZON is a domain-agnostic personal anticipation engine. Weather is one evidence domain among many; it is not the product boundary.

## Predictive invariant

`FACT -> SOCIAL SIGNALS -> BEHAVIORAL HYPOTHESIS -> PERSONAL EXPOSURE -> FORECAST -> RESOLUTION -> LEAD TIME`

## Domain contract

Every domain integration should declare:

- trigger/event family
- source class and provenance
- evidence role
- independence family
- provider and retrieval timestamps
- completeness semantics
- point-in-time replay capability
- behavioral mechanism, if any
- material outcome used to resolve forecasts

A source-count increase is never interpreted as a probability increase. Provider failure is operational failure, not negative real-world evidence. Partial outcome coverage cannot authorize a negative label.

## Current world domains

HORIZON is designed to cover, independently of UI or provider:

- weather and climate
- natural hazards
- transport and mobility
- supply chains and fuel
- energy
- media and collective attention
- geopolitics and security
- economy and labor
- public health
- cyber and technology
- regulation and policy
- financial stress
- personal context and exposure

`GET /v1/horizon/world/coverage` exposes the current implementation maturity of those domains so product development cannot silently collapse back into one domain.

## Epistemic boundary

GDELT and other broad discovery systems create hypotheses, not confirmed facts. Repetition inside one source family cannot promote a hypothesis by itself. Downstream Event Graph edges describe plausible dependencies and never assert causality.

Numeric probability emission stays disabled until empirical calibration gates are satisfied with point-in-time, coverage-aware outcome labels.

## Mechanism Registry

HORIZON keeps an explicit mechanism registry separate from broad event discovery.

A behavior pattern is **not** calibration proof. Each mechanism contract declares:

- trigger event types;
- outcome signal types;
- point-in-time trigger replay status;
- point-in-time outcome replay status;
- completeness semantics;
- calibration corpus strategy, when one exists;
- whether the mechanism is historically calibratable, only a behavioral hypothesis, or merely has a candidate archive not wired yet.

The registry is available at:

`GET /v1/horizon/world/mechanisms`

Current historically replayable mechanisms are regional extreme heat → cooling-load pressure and regional extreme cold → heating-load pressure. Transport mode substitution remains a behavioral hypothesis until independent historical disruption and congestion streams are implemented. Fuel/supply precautionary buying now has a coverage-aware historical outcome replay from the official French annual fuel archives (available from 2007). It remains `outcome_replay_only`: HORIZON does not call it calibratable until an independent point-in-time historical trigger replay also exists. Complete negative coverage is only authorized for explicitly requested and verified department scopes.

This registry is intentionally conservative: missing replay capability is represented as missing capability, never inferred from plausibility or source count.

### Fuel supply: replay pair before calibration

HORIZON has two independently sourced historical sides for an experimental fuel mechanism:

- **trigger precursor:** GDELT 1.0 daily Event files, restricted to France, root events, CAMEO `143*` (strike/boycott) and `144*` (physical obstruction/blockade), then filtered by a fixed v1 fuel/refinery metadata vocabulary;
- **outcome:** the French government's annual fuel-price archives, replaying temporary station stockout pressure.

The trigger is intentionally named `fuel_supply_disruption_report_cluster`. It asserts that contemporaneous media reports matching the fixed filter existed; it **does not** assert that the underlying disruption itself was confirmed. Distinct source domains are a clustering criterion, never a truth vote.

Both streams now preserve point-in-time timestamps, but the pair is not automatically admitted into empirical probability calibration. The trigger operationalization was authored after some historical fuel crises were already known, so retrospective exploration can be used to debug and estimate usefulness, but it cannot unlock numeric probabilities. A versioned precommit/holdout boundary is required before this mechanism becomes calibration-eligible.

