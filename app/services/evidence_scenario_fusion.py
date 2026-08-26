from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Any


PUBLIC_SCENARIOS_FR: dict[str, dict[str, Any]] = {
    "rail_transport_disruption": {
        "headline": "Perturbation ferroviaire : risque de congestion des alternatives et d’allongement des trajets dans les prochaines heures.",
        "chain": [
            "capacité ferroviaire réduite",
            "report des voyageurs vers d’autres itinéraires ou modes",
            "pression sur les réseaux alternatifs",
            "congestion routière ou saturation des services de substitution",
            "allongement observable des temps de trajet",
        ],
        "watch": "congestion routière, saturation des alternatives et allongement mesurable des temps de trajet",
    },
    "transport_disruption": {
        "headline": "Perturbation de transport : risque de report des voyageurs, de congestion et d’allongement des temps de trajet.",
        "chain": [
            "capacité de transport réduite",
            "report vers des itinéraires ou modes alternatifs",
            "pression sur les capacités de substitution",
            "congestion ou saturation",
            "dégradation observable des temps de trajet",
        ],
        "watch": "report modal, congestion et dégradation des temps de trajet",
    },
    "fuel_supply_disruption": {
        "headline": "Tension sur l’approvisionnement en carburant : risque d’achats de précaution, de files d’attente et de ruptures plus visibles.",
        "chain": [
            "menace d’approvisionnement perçue",
            "rareté perçue et apprentissage social",
            "accélération des achats de précaution",
            "pression sur les files et les stocks",
            "ruptures ou indisponibilités visibles",
        ],
        "watch": "files d’attente, accélération des achats et extension des ruptures",
    },
    "supply_disruption": {
        "headline": "Risque d’amplification d’une tension d’approvisionnement par les achats de précaution et la pression sur les stocks.",
        "chain": [
            "menace sur l’approvisionnement",
            "hausse de la rareté perçue",
            "achats de précaution",
            "pression sur les stocks",
            "indisponibilités visibles",
        ],
        "watch": "achats de précaution, files d’attente et pression sur les stocks",
    },
    "critical_goods_disruption": {
        "headline": "Biens essentiels : risque d’achats de précaution et d’aggravation locale des ruptures si la tension se confirme.",
        "chain": [
            "menace sur un bien essentiel",
            "rareté perçue",
            "achats de précaution",
            "compression des stocks",
            "ruptures visibles",
        ],
        "watch": "achats de précaution et ruptures locales",
    },
    "extreme_heat": {
        "headline": "Chaleur extrême : risque d’accélération de la demande de refroidissement et de tension sur certains équipements.",
        "chain": [
            "perception d’un risque de chaleur",
            "hausse des recherches de refroidissement",
            "accélération des achats",
            "compression des stocks",
            "tensions visibles sur les équipements de refroidissement",
        ],
        "watch": "recherches, achats et disponibilité des équipements de refroidissement",
    },
    "extreme_heat_region": {
        "headline": "Chaleur extrême régionale : risque de hausse mesurable de la charge électrique liée au refroidissement.",
        "chain": [
            "exposition régionale à une chaleur extrême",
            "hausse de l’usage de climatisation et de refroidissement",
            "pression sur la charge électrique de l’après-midi",
        ],
        "watch": "hausse de charge électrique cohérente avec l’usage de refroidissement",
    },
    "mass_layoff": {
        "headline": "Licenciement massif : risque de hausse rapide de la recherche d’emploi et de la concurrence sur les postes locaux proches.",
        "chain": [
            "choc d’emploi rendu public",
            "entrée des salariés concernés en recherche d’emploi",
            "hausse de l’offre locale de compétences similaires",
            "concurrence accrue sur les postes proches",
            "hausse de la demande d’accompagnement et de reconversion",
        ],
        "watch": "recherche d’emploi, candidatures locales et demandes de reconversion",
    },
    "industrial_closure": {
        "headline": "Fermeture industrielle : risque de pression accrue sur le marché du travail local et les dispositifs de reconversion.",
        "chain": [
            "fermeture industrielle crédible",
            "recherche d’emploi des salariés touchés",
            "hausse de l’offre locale de travail",
            "concurrence accrue sur les postes proches",
            "hausse des besoins de placement et de reconversion",
        ],
        "watch": "recherche d’emploi locale et demandes de reconversion",
    },
    "economic_sanctions": {
        "headline": "Sanctions économiques : risque de friction d’approvisionnement et de pression sur les prix ou la disponibilité dans les secteurs exposés.",
        "chain": [
            "restriction commerciale crédible",
            "frictions d’importation ou de règlement",
            "réacheminement ou substitution des approvisionnements",
            "compression de l’offre accessible ou des marges",
            "pression visible sur les prix ou la disponibilité",
        ],
        "watch": "coûts de réacheminement, disponibilité et prix des secteurs exposés",
    },
    "trade_policy_change": {
        "headline": "Changement de politique commerciale : risque de hausse des frictions d’importation et de pression sectorielle sur les prix ou la disponibilité.",
        "chain": [
            "changement commercial crédible",
            "hausse des frictions d’importation",
            "substitution ou réacheminement des flux",
            "compression de l’offre ou des marges",
            "pression sur les prix ou la disponibilité",
        ],
        "watch": "flux d’importation, coûts, prix et disponibilité",
    },
    "energy_supply_disruption": {
        "headline": "Perturbation d’approvisionnement énergétique : risque de tension en aval sur la disponibilité, les coûts et certains prix.",
        "chain": [
            "perturbation énergétique crédible",
            "frictions d’approvisionnement",
            "réallocation ou substitution des flux",
            "compression de l’offre disponible",
            "pression visible sur les coûts ou les prix",
        ],
        "watch": "disponibilité énergétique, coûts de substitution et prix en aval",
    },
}


def _normalise_text(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return re.sub(r"[^a-z0-9à-ÿ]+", " ", text).strip()


def _time_bucket(forecast: dict[str, Any]) -> str:
    window = forecast.get("time_window") or {}
    if window.get("kind") == "absolute_after_confirmed_precursor":
        raw = str(window.get("start_at") or "")
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            return raw[:10] or "absolute"
    low = window.get("low_hours")
    high = window.get("high_hours")
    return f"relative:{low}:{high}"


def _group_key(forecast: dict[str, Any]) -> str:
    domain = str(forecast.get("domain") or "")
    event_type = str(forecast.get("event_type") or "")
    outcome = _normalise_text(forecast.get("outcome") or forecast.get("headline"))
    return f"{domain}|{event_type}|{outcome}|{_time_bucket(forecast)}"


def _stable_key(group_key: str) -> str:
    return sha256(f"evidence-fused|{group_key}".encode("utf-8")).hexdigest()[:24]


def _driver_key(driver: dict[str, Any]) -> str:
    return json.dumps(
        {
            "type": driver.get("type"),
            "label": driver.get("label"),
            "event_type": driver.get("event_type"),
            "source_classes": sorted(str(item) for item in (driver.get("source_classes") or []) if item),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _evidence_key(item: dict[str, Any]) -> str:
    return json.dumps(
        {
            "kind": item.get("kind"),
            "title": item.get("title"),
            "source_classes": sorted(str(x) for x in (item.get("source_classes") or []) if x),
            "observed_at": item.get("observed_at"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _unique_dicts(items: list[dict[str, Any]], key_fn, limit: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        key = key_fn(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(deepcopy(item))
        if len(out) >= limit:
            break
    return out


def _score(forecast: dict[str, Any]) -> tuple[float, float]:
    probability = forecast.get("probability") or {}
    return (
        float(probability.get("estimate") or 0.0),
        float(probability.get("evidence_quality") or 0.0),
    )


def _publicize(forecast: dict[str, Any], raw_count: int) -> dict[str, Any]:
    result = deepcopy(forecast)
    event_type = str(result.get("event_type") or "")
    public = PUBLIC_SCENARIOS_FR.get(event_type)
    if not public:
        return result

    raw_outcome = str(result.get("outcome") or result.get("headline") or "")
    headline = str(public["headline"])
    chain = list(public["chain"])
    watch = str(public["watch"])
    window = str((result.get("time_window") or {}).get("human") or "la fenêtre déclarée")
    sources = sorted({
        str(source)
        for driver in result.get("drivers") or []
        for source in (driver.get("source_classes") or [])
        if source
    })
    source_text = ", ".join(sources[:3]) if sources else "les sources HORIZON"
    if raw_count > 1:
        why = (
            f"HORIZON a regroupé {raw_count} alertes ou événements compatibles avec le même mécanisme prédictif. "
            f"Les observations proviennent actuellement de {source_text}. Le nombre de doublons ne multiplie pas la probabilité : "
            "Évidence conserve une estimation représentative et utilise la répétition surtout pour documenter la consolidation."
        )
    else:
        why = (
            f"HORIZON observe un précurseur compatible avec ce mécanisme via {source_text}. "
            "Évidence projette la conséquence attendue dans la fenêtre déclarée, tout en conservant l’incertitude du modèle."
        )

    result["headline"] = headline
    result["outcome"] = headline
    result["why_now"] = why
    result["causal_chain"] = chain
    result["watch_next"] = [watch, "confirmation indépendante d’une étape intermédiaire", "matérialisation observable du résultat projeté"]
    result["probability_up_if"] = [
        f"des observations indépendantes confirment : {watch}",
        "une nouvelle famille de sources indépendante soutient le même mécanisme",
        "le graphe HORIZON ajoute un précurseur amont cohérent",
    ]
    result["probability_down_if"] = [
        "les indicateurs intermédiaires attendus restent absents",
        "des observations indépendantes montrent que la pression se résorbe",
        f"la fenêtre expire sans matérialisation observable du scénario : {headline}",
    ]
    result["falsification"] = (
        f"Le scénario est considéré comme raté si aucun signal observable correspondant à « {headline} » n’apparaît dans {window}, "
        "ou si des observations indépendantes contredisent la trajectoire avant l’échéance."
    )
    result["public_language"] = "fr"
    result["raw_model_outcome_retained_in_public"] = False
    result["raw_model_outcome_hash"] = sha256(raw_outcome.encode("utf-8")).hexdigest()[:12] if raw_outcome else None
    return result


class EvidenceScenarioFusion:
    """Collapse duplicate event-level forecasts into public scenario hypotheses.

    Repeated alerts from the same provider must not mechanically inflate probability.
    The strongest forecast is kept as the probability representative; support rows are
    merged for explanation/consolidation only. This is deliberately more conservative
    than weighted averaging of duplicate probabilities.
    """

    VERSION = "evidence-scenario-fusion-v1"

    def fuse(self, forecasts: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for forecast in forecasts:
            groups.setdefault(_group_key(forecast), []).append(forecast)

        fused: list[dict[str, Any]] = []
        for key, group in groups.items():
            ordered = sorted(group, key=_score, reverse=True)
            representative = deepcopy(ordered[0])
            all_drivers = [driver for item in ordered for driver in (item.get("drivers") or []) if isinstance(driver, dict)]
            all_evidence = [e for item in ordered for e in (item.get("evidence") or []) if isinstance(e, dict)]
            representative["drivers"] = _unique_dicts(all_drivers, _driver_key, 16)
            representative["evidence"] = _unique_dicts(all_evidence, _evidence_key, 16)
            representative["scenario_key"] = _stable_key(key)

            supporting_event_ids = sorted({int(item["event_id"]) for item in ordered if item.get("event_id") is not None})
            supporting_candidate_ids = sorted({int(item["candidate_id"]) for item in ordered if item.get("candidate_id") is not None})
            source_keys = sorted({
                str(source)
                for driver in representative["drivers"]
                for source in (driver.get("source_classes") or [])
                if source
            })
            representative["fusion"] = {
                "engine": self.VERSION,
                "raw_forecast_count": len(ordered),
                "supporting_event_ids": supporting_event_ids,
                "supporting_candidate_ids": supporting_candidate_ids,
                "source_keys": source_keys,
                "duplicate_probability_inflation_prevented": True,
                "probability_merge_method": "strongest_representative_not_recomputed",
                "probability_recomputed_after_fusion": False,
                "geography_aware_grouping": False,
                "group_time_bucket": _time_bucket(representative),
            }
            components = dict(representative.get("model_components") or {})
            components["source_diversity"] = max(int(components.get("source_diversity") or 0), len(source_keys))
            components["fusion_raw_forecast_count"] = len(ordered)
            components["fusion_changes_probability"] = False
            representative["model_components"] = components
            fused.append(_publicize(representative, len(ordered)))

        fused.sort(key=_score, reverse=True)
        return fused[: max(1, min(int(limit), 30))]
