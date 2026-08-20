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
