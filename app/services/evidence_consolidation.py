from __future__ import annotations

from datetime import datetime, timezone
from math import exp
from typing import Any


SOURCE_FAMILY_META: dict[str, dict[str, Any]] = {
    "official_primary": {"label": "Source officielle primaire", "trust": 0.97, "category": "fact"},
    "official_statistical": {"label": "Statistique officielle", "trust": 0.94, "category": "fact"},
    "official_operational": {"label": "Flux opérationnel officiel", "trust": 0.92, "category": "fact"},
    "scientific": {"label": "Source scientifique", "trust": 0.90, "category": "research"},
    "human_forecast": {"label": "Consensus de prévisionneurs", "trust": 0.84, "category": "consensus"},
    "prediction_market": {"label": "Marché prédictif", "trust": 0.78, "category": "consensus"},
    "model_forecast": {"label": "Modèle de prévision", "trust": 0.74, "category": "model"},
    "news_global": {"label": "Détection médias mondiale", "trust": 0.58, "category": "detection"},
    "media_attention": {"label": "Attention médiatique", "trust": 0.52, "category": "detection"},
    "social_signal": {"label": "Signal social", "trust": 0.48, "category": "detection"},
}

SOURCE_KEY_HINTS: tuple[tuple[str, str], ...] = (
    ("meteofrance", "official_primary"),
    ("meteo-france", "official_primary"),
    ("vigicrues", "official_primary"),
    ("gdacs", "official_primary"),
    ("rte", "official_statistical"),
    ("sncf", "official_operational"),
    ("fuel", "official_operational"),
    ("windy", "model_forecast"),
    ("gdelt", "news_global"),
    ("metaculus", "human_forecast"),
    ("polymarket", "prediction_market"),
)

MODEL_PRIOR_PERCENT = round((1.0 / (1.0 + exp(1.10))) * 100, 1)


def _clamp(value: Any, low: float = 0.0, high: float = 1.0) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(low, min(high, numeric))


def _source_family(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return "unknown"
    if raw in SOURCE_FAMILY_META:
        return raw
    for hint, family in SOURCE_KEY_HINTS:
        if hint in raw:
            return family
    return raw


def _source_meta(family: str) -> dict[str, Any]:
    meta = SOURCE_FAMILY_META.get(family)
    if meta:
        return dict(meta)
    return {"label": family.replace("_", " ").title(), "trust": 0.55, "category": "other"}


def _freshness_score(drivers: list[dict[str, Any]]) -> float:
    now = datetime.now(timezone.utc)
    ages: list[float] = []
    for driver in drivers:
        raw = driver.get("last_observed_at") or driver.get("first_observed_at")
        if not raw or not isinstance(raw, str):
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ages.append(max(0.0, (now - dt.astimezone(timezone.utc)).total_seconds() / 3600.0))
    if not ages:
        return 0.5
    age = min(ages)
    if age <= 1:
        return 1.0
    if age <= 6:
        return 0.92
    if age <= 24:
        return 0.78
    if age <= 72:
        return 0.62
    if age <= 168:
        return 0.45
    return 0.30


def _level(score: float) -> str:
    if score >= 0.78:
        return "très solide"
    if score >= 0.62:
        return "solide"
    if score >= 0.46:
        return "modérée"
    return "fragile"


class EvidenceConsolidator:
    """Explain how a forecast is consolidated without pretending diagnostics are probabilities.

    Inspired by Future Engine's clear source/confidence breakdown, but keeps Évidence's
    epistemic contract: source quality, freshness and causal support are diagnostic inputs;
    only the forecast model emits a probability estimate.
    """

    VERSION = "evidence-consolidation-v1"

    def consolidate(self, forecast: dict[str, Any]) -> dict[str, Any]:
        probability = dict(forecast.get("probability") or {})
        components = dict(forecast.get("model_components") or {})
        drivers = list(forecast.get("drivers") or [])

        raw_sources: list[str] = []
        for driver in drivers:
            raw_sources.extend(str(item) for item in (driver.get("source_classes") or []) if item)
        families = sorted({_source_family(item) for item in raw_sources if item})
        metas = [{"key": family, **_source_meta(family)} for family in families]

        source_diversity = max(int(components.get("source_diversity") or 0), len(families))
        diversity_score = _clamp(source_diversity / 4.0)
        if metas:
            source_quality = sum(float(item["trust"]) for item in metas) / len(metas)
        else:
            source_quality = _clamp(components.get("source_reliability") or components.get("corroboration") or 0.5)
        freshness = _freshness_score(drivers)
        pattern = _clamp(components.get("pattern_confidence") or 0.5)
        graph = _clamp(components.get("graph_dependency_support") or 0.5)
        confirmed = bool(components.get("precursor_confirmed"))

        score = _clamp(
            0.25 * source_quality
            + 0.19 * diversity_score
            + 0.16 * freshness
            + 0.21 * pattern
            + 0.13 * graph
            + (0.06 if confirmed else 0.0)
        )

        dimensions = [
            {"key": "source_quality", "label": "Qualité des sources", "score": round(source_quality * 100)},
            {"key": "source_diversity", "label": "Diversité des familles", "score": round(diversity_score * 100)},
            {"key": "freshness", "label": "Fraîcheur des signaux", "score": round(freshness * 100)},
            {"key": "pattern", "label": "Pattern historique / comportemental", "score": round(pattern * 100)},
            {"key": "graph", "label": "Support du graphe de dépendances", "score": round(graph * 100)},
        ]

        strengths: list[str] = []
        weaknesses: list[str] = []
        if confirmed:
            strengths.append("Le précurseur principal est confirmé par HORIZON.")
        else:
            weaknesses.append("Le précurseur principal reste un signal émergent non confirmé.")
        if source_diversity >= 3:
            strengths.append(f"{source_diversity} familles de sources contribuent au scénario.")
        elif source_diversity <= 1:
            weaknesses.append("La diversité de sources est encore faible.")
        if source_quality >= 0.85:
            strengths.append("La qualité moyenne des sources est élevée.")
        if graph >= 0.70:
            strengths.append("Le graphe HORIZON fournit un support amont cohérent.")
        elif graph < 0.45:
            weaknesses.append("Le support du graphe causal reste faible.")
        if pattern >= 0.70:
            strengths.append("Le mécanisme projeté est soutenu par un pattern fort.")
        elif pattern < 0.45:
            weaknesses.append("Le pattern utilisé reste peu soutenu.")
        if freshness < 0.50:
            weaknesses.append("Les signaux les plus récents vieillissent et doivent être reconfirmés.")

        estimate = float(probability.get("percent") or 0.0)
        interval = list(probability.get("interval_percent") or [])
        non_materialization = max(0.0, 100.0 - estimate)

        external = forecast.get("consensus_reference")
        if isinstance(external, dict) and external.get("authorized") and external.get("percent") is not None:
            reference_percent = float(external["percent"])
            reference_type = str(external.get("type") or "authorized_external_consensus")
            reference_label = str(external.get("label") or "Consensus externe autorisé")
            external_available = True
        else:
            reference_percent = MODEL_PRIOR_PERCENT
            reference_type = "internal_model_prior"
            reference_label = "Prior interne du modèle"
            external_available = False

        delta = round(estimate - reference_percent, 1)
        if delta >= 15:
            divergence_label = "fortement au-dessus de la référence"
        elif delta <= -15:
            divergence_label = "fortement sous la référence"
        elif abs(delta) >= 7:
            divergence_label = "écart notable"
        else:
            divergence_label = "proche de la référence"

        return {
            "engine": self.VERSION,
            "score": round(score * 100),
            "score_is_probability": False,
            "level": _level(score),
            "source_family_count": source_diversity,
            "source_families": metas,
            "dimensions": dimensions,
            "strengths": strengths[:5],
            "weaknesses": weaknesses[:5],
            "probability_case": {
                "estimate_percent": round(estimate),
                "interval_percent": interval,
                "calibration_status": probability.get("calibration_status"),
                "explanation": "La probabilité est produite par le modèle Évidence. Les scores de consolidation ci-dessus expliquent la solidité des entrées mais ne sont pas eux-mêmes des probabilités.",
            },
            "scenario_competition": {
                "kind": "binary_window_outcome",
                "mutually_exclusive": True,
                "outcomes": [
                    {"label": str(forecast.get("headline") or forecast.get("outcome") or "Matérialisation du scénario"), "percent": round(estimate)},
                    {"label": "Pas de matérialisation dans la fenêtre déclarée", "percent": round(non_materialization)},
                ],
            },
            "divergence": {
                "reference_type": reference_type,
                "reference_label": reference_label,
                "reference_percent": round(reference_percent, 1),
                "forecast_percent": round(estimate, 1),
                "delta_points": delta,
                "label": divergence_label,
                "external_consensus_available": external_available,
            },
        }
