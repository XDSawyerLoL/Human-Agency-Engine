# HORIZON Human Dynamics Engine

## Purpose

The Human Dynamics Engine adds explicit behavioral scenario modeling to HORIZON. It estimates how a population may distribute across competing actions under a stated scenario and time horizon.

It is designed to sit above HORIZON evidence, convergence, Event Graph, cascade and calibration layers. It does not replace them.

Version: `horizon-human-dynamics-v1.0`

## Core model

V1 combines four deliberately different behavioral mechanisms:

1. **Incentive** — perceived benefit, friction, perceived control and evidence salience.
2. **Habit** — inertia, identity alignment, habit strength and friction.
3. **Social** — norm support, network exposure, identity alignment and salience.
4. **Stress** — urgency, threat reduction, perceived control, friction and salience.

Each mechanism independently scores all competing actions. Scores are converted to a probability distribution with softmax. The distributions are then pooled with configurable mechanism weights.

Default weights:

```text
incentive  0.30
habit      0.25
social     0.25
stress     0.20
```

These are engineering priors, not empirically learned coefficients. They must eventually be calibrated by domain and population.

## Evidence updating

New observations can update the action distribution with explicit likelihood ratios:

```json
{
  "signal": "Searches for cancellation instructions spike",
  "reliability": 0.9,
  "likelihood_by_action": {
    "leave": 4.0,
    "accept": 0.6
  }
}
```

A likelihood ratio above `1` supports an action. A value below `1` weakens it. Reliability tempers the update.

This creates an auditable update path instead of letting an LLM silently change its conclusion.

## API

### Predict behavior

`POST /v1/horizon/human-dynamics/predict`

Example request:

```json
{
  "scenario": "A subscription service announces a 20% price increase.",
  "scenario_id": "subscription-price-rise",
  "population": "active_customers",
  "horizon_hours": 168,
  "evidence_quality": 0.72,
  "options": [
    {
      "key": "accept",
      "label": "Keep the subscription",
      "base_rate": 0.55,
      "perceived_benefit": 0.55,
      "friction": 0.25,
      "norm_support": 0.55,
      "identity_alignment": 0.55,
      "habit_strength": 0.80,
      "network_exposure": 0.45,
      "urgency": 0.35,
      "threat_reduction": 0.50,
      "perceived_control": 0.45,
      "evidence_salience": 0.65
    },
    {
      "key": "leave",
      "label": "Cancel the subscription",
      "base_rate": 0.25,
      "perceived_benefit": 0.65,
      "friction": 0.65,
      "norm_support": 0.45,
      "identity_alignment": 0.40,
      "habit_strength": 0.20,
      "network_exposure": 0.50,
      "urgency": 0.55,
      "threat_reduction": 0.70,
      "perceived_control": 0.65,
      "evidence_salience": 0.70
    }
  ],
  "observations": []
}
```

The response contains:

- normalized model probabilities for each action;
- per-mechanism probabilities;
- dominant behavioral drivers;
- model disagreement;
- a heuristic action-timing estimate;
- a plausibility band;
- an explicit model-confidence score;
- the evidence-update trace.

### Compare counterfactual scenarios

`POST /v1/horizon/human-dynamics/compare`

The comparison endpoint runs one baseline and up to eight counterfactual scenarios, then reports probability deltas for shared actions.

It is a **sensitivity analysis**, not proof of a causal effect.

### Inspect semantics

`GET /v1/horizon/human-dynamics/spec`

This endpoint exposes the current mechanisms, calibration status and intended-use boundaries.

## Probability semantics

V1 intentionally distinguishes three concepts:

- **Action probability**: a normalized model estimate produced by the ensemble.
- **Model confidence**: a diagnostic based on evidence quality, entropy, observation reliability and mechanism agreement.
- **Plausibility band**: an engineering uncertainty band around the model estimate.

None of these should currently be described as an empirically validated population frequency or a statistical confidence interval.

All V1 responses therefore expose:

```text
prediction_status = uncalibrated_model_estimate
empirically_calibrated = false
probabilities_are_observed_frequencies = false
```

## Why this architecture

A single LLM prediction can be articulate but poorly calibrated and difficult to audit. The HORIZON design instead keeps behavioral assumptions explicit and separates independent mechanisms that may disagree.

Disagreement is useful information. A population may be pulled toward one action by habit but another by incentives or social pressure. HORIZON preserves that tension rather than hiding it in one generated answer.

## Calibration roadmap

The existing HORIZON historical replay and calibration corpus should be used to move V1 from engineered priors to empirical behavioral forecasting.

Recommended sequence:

1. Define a small set of forecastable behavioral event families with objective outcomes.
2. Extract pre-event feature snapshots without hindsight leakage.
3. Record the action distribution or observable proxy inside a fixed horizon.
4. Fit mechanism coefficients by domain/population while retaining interpretability.
5. Evaluate Brier score, log loss, calibration error and top-action accuracy out of sample.
6. Calibrate timing separately with survival/time-to-event models.
7. Measure robustness under source removal and feature perturbation.
8. Promote a domain from `uncalibrated_model_estimate` only after held-out validation passes explicit thresholds.

## Next research adapters

The Human Dynamics Engine is deliberately model-agnostic. Later adapters can add external behavioral foundation models or agent simulations as additional ensemble members, provided their outputs are normalized, provenance is preserved and their calibration is measured against held-out outcomes.

Potential adapters include:

- cognitive foundation models trained on behavioral experiments;
- synthetic-agent population simulations;
- survival and hazard models for action timing;
- network diffusion / Hawkes-process models for social cascades;
- domain-specific gradient boosting or Bayesian models trained on HORIZON historical episodes.

The target architecture is not "one AI that knows what humans will do". It is a continuously scored ensemble whose forecasts are logged before outcomes, compared with reality, and recalibrated from its own misses.
