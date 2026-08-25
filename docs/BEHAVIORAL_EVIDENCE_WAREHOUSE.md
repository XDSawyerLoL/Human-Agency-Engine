# HORIZON Behavioral Evidence Warehouse

Version: `horizon-behavioral-evidence-warehouse-v1.0`

## Purpose

The Behavioral Evidence Warehouse is the persistence and quality-control layer between HORIZON's scientific retrieval system and the Human Dynamics Engine.

Its job is not to collect a large pile of papers. Its job is to turn auditable research records into structured behavioral evidence that can later be used for empirical calibration.

The pipeline is deliberately gated:

```text
scientific discovery
        ↓
versioned document metadata
        ↓
structured effect extraction
        ↓
candidate evidence
        ↓
review / rejection
        ↓
accepted evidence
        ↓
calibration pack
        ↓
held-out calibration / backtesting
        ↓
only then: learned Human Dynamics parameters
```

A discovered paper never changes a prediction by itself.

## Persistent entities

### Ingestion runs

Every harvest has a permanent run record containing:

- query and sources;
- request snapshot;
- number of references seen, created and updated;
- source errors;
- start/completion timestamps;
- result summary.

This creates provenance for corpus growth.

### Behavioral documents

Documents are deduplicated by `(source, source_record_id)` and receive stable HORIZON document keys.

Stored information includes:

- source identifier and DOI where available;
- title, year, publication type and venue;
- open-access state and canonical source URL;
- topics;
- a discovery-ranking signal;
- whether an abstract was available;
- a metadata snapshot and fingerprint;
- ingestion count and evidence status;
- first/last seen timestamps.

V1 intentionally does **not** persist abstract text from the search adapters. It stores metadata and source links. Full-text storage requires an explicit licensing-aware ingestion path.

Citation counts and discovery signals are never treated as scientific validity probabilities.

### Behavioral effects

A document only becomes useful to behavioral calibration when one or more effects are extracted into a structured record.

An effect records:

- HORIZON mechanism (`incentive`, `habit`, `social`, `stress`, `intention_action`, `collective_dynamics`, or `other`);
- behavioral construct;
- population;
- context;
- exposure/intervention;
- behavioral outcome;
- direction and optional effect size;
- effect-size metric;
- uncertainty bounds;
- sample size;
- study design;
- replication state;
- preregistration and peer-review flags;
- country/context information;
- time horizon;
- evidence summary and source locator;
- extraction method/version/confidence;
- quality diagnostic;
- review status and audit data.

## Quality score

V1 computes an engineering quality diagnostic from:

- study design;
- replication status;
- sample size;
- preregistration;
- peer review;
- presence of a typed effect size;
- extraction confidence.

This score is useful for ranking and calibration eligibility. It is **not** the probability that an effect is true.

The quality formula is deliberately explicit and replaceable. Future versions should learn or validate weighting rules against replication and out-of-sample performance rather than treating the initial weights as scientific constants.

## Review gate

New effects begin as `candidate`.

Only `accepted` effects are eligible for calibration export. `rejected` effects remain in the warehouse for auditability and cannot enter a calibration pack.

This prevents:

- a search result from silently becoming a behavioral law;
- an extraction error from immediately modifying predictions;
- a highly cited but weak study from being promoted automatically;
- an LLM extraction from bypassing evidence review.

## Calibration pack

`POST /v1/horizon/behavioral-warehouse/calibration-pack`

A calibration pack selects accepted effects above a configurable quality threshold and summarizes them by mechanism.

It exposes:

- accepted effects;
- independent document count;
- mean quality score;
- evidence-direction index;
- replicated-effect count;
- randomized-experiment count;
- effect-size metric types;
- whether effects are directly poolable under one metric;
- whether a mechanism has enough independent evidence to become learning-eligible.

A pack is **training-eligible input**, not a trained model. It does not automatically change Human Dynamics coefficients.

Effect sizes with incompatible metrics must not be naively averaged. Metric-specific transformation or hierarchical/meta-analytic modeling is required.

## API

### Read status

```text
GET /v1/horizon/behavioral-warehouse/status
```

Returns document/effect counts, indexed sources and the current learning gates.

### Harvest a topic

```text
POST /v1/horizon/behavioral-warehouse/harvest
```

Protected by HORIZON API key. Searches OpenAlex/PubMed through the Behavioral Knowledge layer and persists deduplicated document metadata.

### Bootstrap the broad corpus

```text
POST /v1/horizon/behavioral-warehouse/bootstrap
```

Runs mechanism-specific query families across incentive, habit, social influence, stress/threat, intention-action and collective dynamics.

### Browse documents

```text
GET /v1/horizon/behavioral-warehouse/documents
```

Supports source, year and evidence-status filters.

### Add an extracted effect

```text
POST /v1/horizon/behavioral-warehouse/effects
```

Protected by API key. Effect insertion is idempotent through a stable effect key.

### Review an effect

```text
POST /v1/horizon/behavioral-warehouse/effects/{effect_key}/review
```

Protected by API key. Moves evidence to `accepted`, `rejected` or back to `candidate` with reviewer and notes.

### Browse effects

```text
GET /v1/horizon/behavioral-warehouse/effects
```

Supports mechanism, status and minimum-quality filters.

## Database migration

Alembic revision:

```text
20260825_0040
```

Creates:

- `horizon_behavioral_ingestion_runs`
- `horizon_behavioral_documents`
- `horizon_behavioral_effects`

The migration follows HORIZON calibration corpus revision `20260820_0039`.

## Cockpit

The Behavioral Library now exposes an Evidence Warehouse panel with:

- persistent document count;
- extracted-effect count;
- accepted-effect count;
- effects awaiting review;
- `Indexer ce sujet` for the current search;
- `Construire le corpus de base` for the transverse bootstrap.

This gives a visible distinction between **retrieval** and **validated evidence**.

## Next stage: Evidence Extractor

V1 provides persistence and review gates. The next major component should extract candidate effects automatically while preserving source location and uncertainty.

Recommended extraction sequence:

1. identify study type and population;
2. find exposure/intervention and behavioral outcome;
3. recover effect direction and typed effect size when stated;
4. recover uncertainty bounds and sample size;
5. detect preregistration/replication claims only from explicit source evidence;
6. attach exact source locator;
7. assign extraction confidence;
8. leave the effect as `candidate` until review.

LLM-assisted extraction should be schema-constrained and source-grounded. It must never invent missing effect sizes.

## Learning stage

Once the warehouse contains enough reviewed evidence, HORIZON should fit mechanism parameters with two separate evidence channels:

```text
reviewed scientific priors
        +
HORIZON historical/prospective outcome episodes
        ↓
hierarchical / domain-aware parameter fit
        ↓
held-out evaluation
        ↓
Brier score · log loss · calibration error · timing error
        ↓
promotion only if thresholds improve out-of-sample
```

Scientific evidence should act as an informed prior or transfer signal; real prospective HORIZON outcomes must remain the final calibration test.

## Epistemic rules

The warehouse enforces these semantics:

- a document is not a behavioral rule;
- citation count is not replication quality;
- an extracted effect is not accepted evidence;
- an accepted effect is not automatically causal outside its study design/context;
- a quality score is not a truth probability;
- a calibration pack is not a trained model;
- heterogeneous populations and cultures must not be silently collapsed;
- all backtests must use evidence available before the forecast cutoff.
