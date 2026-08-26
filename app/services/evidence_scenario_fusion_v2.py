from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import re
from typing import Any


PUBLIC_SCENARIOS_FR: dict[str, dict[str, Any]] = {
    "rail_transport_disruption": {
        "headline": "Perturbation ferroviaire : risque de congestion des alternatives et d’allongement des trajets dans les prochaines heures.",
        "chain": ["capacité ferroviaire réduite", "report vers les alternatives", "pression sur les capacités de substitution", "congestion ou saturation", "allongement observable des trajets"],
        "watch": "congestion, saturation des alternatives et temps de trajet",
    },
    "transport_disruption": {
        "headline": "Perturbation de transport : risque de report des voyageurs, de congestion et d’allongement des temps de trajet.",
        "chain": ["capacité de transport réduite", "report modal", "pression sur les alternatives", "congestion", "dégradation des temps de trajet"],
        "watch": "report modal, congestion et temps de trajet",
    },
    "fuel_supply_disruption": {
        "headline": "Tension sur l’approvisionnement en carburant : risque d’achats de précaution, de files d’attente et de ruptures plus visibles.",
        "chain": ["menace d’approvisionnement perçue", "rareté perçue", "achats de précaution", "pression sur les stocks", "ruptures ou indisponibilités visibles"],
        "watch": "files d’attente, achats de précaution et extension des ruptures",
    },
    "supply_disruption": {
        "headline": "Risque d’amplification d’une tension d’approvisionnement par les achats de précaution et la pression sur les stocks.",
        "chain": ["menace sur l’approvisionnement", "rareté perçue", "achats de précaution", "pression sur les stocks", "indisponibilités visibles"],
        "watch": "achats de précaution et pression sur les stocks",
    },
    "critical_goods_disruption": {
        "headline": "Biens essentiels : risque d’achats de précaution et d’aggravation locale des ruptures si la tension se confirme.",
        "chain": ["menace sur un bien essentiel", "rareté perçue", "achats de précaution", "compression des stocks", "ruptures visibles"],
        "watch": "achats de précaution et ruptures locales",
    },
    "extreme_heat": {
        "headline": "Chaleur extrême : risque d’accélération de la demande de refroidissement et de tension sur certains équipements.",
        "chain": ["chaleur extrême", "hausse du besoin de refroidissement", "accélération de la demande", "compression des capacités", "tensions visibles"],
        "watch": "demande et disponibilité des équipements de refroidissement",
    },
    "extreme_heat_region": {
        "headline": "Chaleur extrême régionale : risque de hausse mesurable de la charge électrique liée au refroidissement.",
        "chain": ["chaleur régionale", "usage accru de climatisation", "hausse de la charge électrique"],
        "watch": "charge électrique liée au refroidissement",
    },
    "mass_layoff": {
        "headline": "Licenciement massif : risque de hausse rapide de la recherche d’emploi et de la concurrence sur les postes locaux proches.",
        "chain": ["choc d’emploi", "entrée en recherche d’emploi", "hausse de l’offre locale de compétences", "concurrence accrue", "besoins de reconversion"],
        "watch": "recherche d’emploi et demandes de reconversion",
    },
    "industrial_closure": {
        "headline": "Fermeture industrielle : risque de pression accrue sur le marché du travail local et les dispositifs de reconversion.",
        "chain": ["fermeture industrielle", "recherche d’emploi", "hausse de l’offre locale de travail", "concurrence accrue", "besoins de reconversion"],
        "watch": "recherche d’emploi locale et reconversion",
    },
    "economic_sanctions": {
        "headline": "Sanctions économiques : risque de friction d’approvisionnement et de pression sur les prix ou la disponibilité dans les secteurs exposés.",
        "chain": ["restriction commerciale", "frictions d’importation", "réacheminement", "compression de l’offre", "pression sur prix ou disponibilité"],
        "watch": "flux, coûts, prix et disponibilité",
    },
    "trade_policy_change": {
        "headline": "Changement de politique commerciale : risque de hausse des frictions d’importation et de pression sectorielle sur les prix ou la disponibilité.",
        "chain": ["changement commercial", "frictions d’importation", "substitution des flux", "compression de l’offre", "pression sectorielle"],
        "watch": "imports, coûts, prix et disponibilité",
    },
    "energy_supply_disruption": {
        "headline": "Perturbation d’approvisionnement énergétique : risque de tension en aval sur la disponibilité, les coûts et certains prix.",
        "chain": ["perturbation énergétique", "frictions d’approvisionnement", "substitution des flux", "compression de l’offre", "pression en aval"],
        "watch": "disponibilité énergétique et coûts en aval",
    },
    "major_earthquake": {
        "headline": "Après un séisme important : risque persistant d’après-chocs et de perturbations locales d’accès, de mobilité ou de services.",
        "chain": ["séisme principal", "séquence d’après-chocs", "inspection et restrictions", "capacités locales réduites", "retards de remise en service"],
        "watch": "après-chocs, restrictions d’accès et continuité des services",
    },
    "disease_outbreak_signal": {
        "headline": "Foyer sanitaire documenté : risque de renforcement de la surveillance, du dépistage et des mesures locales si de nouveaux cas apparaissent.",
        "chain": ["foyer officiellement documenté", "investigation renforcée", "détection de cas ou contacts", "mesures locales", "pression sanitaire ou comportementale si la transmission progresse"],
        "watch": "nouveaux cas, extension géographique et mesures sanitaires",
    },
    "financial_stress": {
        "headline": "Stress financier : risque de durcissement des conditions de financement et de comportement plus défensif sur les actifs fragiles.",
        "chain": ["stress financier", "réduction du risque", "hausse des primes", "financement plus sélectif", "pression sur acteurs fragiles"],
        "watch": "spreads, volatilité et conditions de financement",
    },
    "credit_stress": {
        "headline": "Tension du crédit : risque de refinancement plus coûteux et de mesures défensives chez les entreprises les plus exposées.",
        "chain": ["hausse des spreads", "refinancement plus coûteux", "financement plus sélectif", "mesures défensives", "pression sur investissement ou emploi"],
        "watch": "spreads, refinancement et conditions de crédit",
    },
    "energy_price_spike": {
        "headline": "Pétrole en hausse : risque de transmission aux carburants, au fret et à certains coûts de production dans les semaines suivantes.",
        "chain": ["hausse du brut", "coûts d’approvisionnement", "pression sur carburants et fret", "coûts sectoriels", "transmission partielle aux prix"],
        "watch": "pétrole, carburants, fret et prix en aval",
    },
    "labor_market_softening": {
        "headline": "Marché du travail US : risque de ralentissement des embauches et de comportements plus prudents si la dégradation se confirme.",
        "chain": ["hausse des inscriptions au chômage", "recherche d’emploi accrue", "embauches plus sélectives", "prudence des ménages", "ralentissement cyclique"],
        "watch": "inscriptions au chômage, embauches et consommation",
    },
    "financial_stress_easing": {
        "headline": "Détente financière projetée : risque de stress immédiat en recul si la baisse de volatilité se confirme dans les données réelles.",
        "chain": ["volatilité projetée en baisse", "demande de protection moindre", "primes plus stables", "financement moins tendu", "pression immédiate en recul"],
        "watch": "confirmation réelle de la baisse de volatilité et des primes de risque",
    },
    "credit_stress_easing": {
        "headline": "Détente du crédit projetée : risque de pression de refinancement en recul si les spreads réels suivent la trajectoire.",
        "chain": ["spreads projetés en baisse", "prime de crédit moins tendue", "coût marginal plus stable", "pression de trésorerie en recul", "mesures défensives moins urgentes"],
        "watch": "spreads réels et coût de refinancement",
    },
    "energy_price_relief": {
        "headline": "Pétrole projeté en baisse : possibilité d’un allègement progressif des pressions sur carburants, fret et coûts en aval.",
        "chain": ["pétrole projeté en baisse", "coûts d’approvisionnement moins tendus", "pression sur fret en recul", "coûts sectoriels plus stables", "transmission partielle"],
        "watch": "confirmation du pétrole réel, carburants et fret",
    },
    "labor_market_improvement": {
        "headline": "Marché du travail US projeté en amélioration : risque de dégradation rapide en recul si les prochaines publications confirment la trajectoire.",
        "chain": ["inscriptions projetées en baisse", "moins de transitions vers le chômage", "pression de recherche en recul", "embauches moins défensives", "ménages plus stables"],
        "watch": "prochaines inscriptions au chômage et rythme des embauches",
    },
}

EVENT_SCOPED_BY_LABEL = {
    "major_earthquake",
    "disease_outbreak_signal",
    "wildfire_emergency",
    "severe_storm_emergency",
    "volcanic_emergency",
    "flood_emergency",
    "drought_emergency",
    "landslide_emergency",
    "cryosphere_disruption",
    "air_quality_hazard",
    "severe_winter_hazard",
    "temperature_extreme",
    "water_quality_anomaly",
    "natural_hazard_event",
    "large_disaster_activation",
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
    return f"relative:{window.get('low_hours')}:{window.get('high_hours')}"


def _first_driver_label(forecast: dict[str, Any]) -> str:
    for driver in forecast.get("drivers") or []:
        if isinstance(driver, dict) and str(driver.get("label") or "").strip():
            return str(driver.get("label")).strip()
    return ""


def _geography_scope(forecast: dict[str, Any]) -> str:
    explicit = [_normalise_text(item) for item in (forecast.get("geography") or []) if _normalise_text(item)]
    non_global = [item for item in explicit if item not in {"global", "world", "monde", "*"}]
    if non_global:
        return "geo:" + "|".join(sorted(set(non_global))[:4])

    event_type = str(forecast.get("event_type") or "")
    label = _first_driver_label(forecast)
    if event_type == "fuel_supply_disruption":
        match = re.search(r"d[ée]partement\s+([0-9]{2,3}|2[ab])\b", label, flags=re.IGNORECASE)
        if match:
            return "fr-dept:" + match.group(1).lower()
    if event_type == "major_earthquake" and label:
        parts = re.split(r"\s+[—–-]\s+", label, maxsplit=1)
        place = parts[-1] if len(parts) > 1 else label
        return "quake:" + _normalise_text(place)
    if event_type in EVENT_SCOPED_BY_LABEL and label:
        return "event:" + _normalise_text(label)
    return "global"


def _group_key(forecast: dict[str, Any]) -> str:
    domain = str(forecast.get("domain") or "")
    event_type = str(forecast.get("event_type") or "")
    outcome = _normalise_text(forecast.get("outcome") or forecast.get("headline"))
    return f"{domain}|{event_type}|{_geography_scope(forecast)}|{outcome}|{_time_bucket(forecast)}"


def _stable_key(group_key: str) -> str:
    return sha256(f"evidence-fused-v2|{group_key}".encode("utf-8")).hexdigest()[:24]


def _driver_key(driver: dict[str, Any]) -> str:
    return json.dumps({"type": driver.get("type"), "label": driver.get("label"), "event_type": driver.get("event_type"), "source_classes": sorted(str(item) for item in (driver.get("source_classes") or []) if item)}, ensure_ascii=False, sort_keys=True)


def _evidence_key(item: dict[str, Any]) -> str:
    return json.dumps({"kind": item.get("kind"), "title": item.get("title"), "source_classes": sorted(str(x) for x in (item.get("source_classes") or []) if x), "observed_at": item.get("observed_at")}, ensure_ascii=False, sort_keys=True)


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
    return (float(probability.get("estimate") or 0.0), float(probability.get("evidence_quality") or 0.0))


def _publicize(forecast: dict[str, Any], raw_count: int) -> dict[str, Any]:
    result = deepcopy(forecast)
    public = PUBLIC_SCENARIOS_FR.get(str(result.get("event_type") or ""))
    if not public:
        return result
    raw_outcome = str(result.get("outcome") or result.get("headline") or "")
    headline = str(public["headline"])
    watch = str(public["watch"])
    window = str((result.get("time_window") or {}).get("human") or "la fenêtre déclarée")
    sources = sorted({str(source) for driver in result.get("drivers") or [] for source in (driver.get("source_classes") or []) if source})
    source_text = ", ".join(sources[:3]) if sources else "les sources HORIZON"
    scope = _geography_scope(result)
    if raw_count > 1:
        why = f"HORIZON a regroupé {raw_count} observations compatibles dans le même périmètre ({scope}). Les observations proviennent de {source_text}. Les doublons documentent la consolidation mais ne multiplient pas la probabilité."
    else:
        why = f"HORIZON observe un précurseur distinct dans le périmètre {scope} via {source_text}. Évidence projette la conséquence attendue sans confondre l’observation actuelle avec le résultat futur."
    result["headline"] = headline
    result["outcome"] = headline
    result["why_now"] = why
    result["causal_chain"] = list(public["chain"])
    result["watch_next"] = [watch, "confirmation indépendante d’une étape intermédiaire", "matérialisation observable du résultat projeté"]
    result["probability_up_if"] = [f"des observations indépendantes confirment : {watch}", "une nouvelle famille de sources indépendante soutient le même mécanisme", "le graphe HORIZON ajoute un précurseur amont cohérent"]
    result["probability_down_if"] = ["les indicateurs intermédiaires attendus restent absents", "des observations indépendantes montrent que la pression se résorbe", f"la fenêtre expire sans matérialisation observable du scénario : {headline}"]
    result["falsification"] = f"Le scénario est considéré comme raté si aucun signal observable correspondant à « {headline} » n’apparaît dans {window}, ou si des observations indépendantes contredisent la trajectoire avant l’échéance."
    result["public_language"] = "fr"
    result["raw_model_outcome_retained_in_public"] = False
    result["raw_model_outcome_hash"] = sha256(raw_outcome.encode("utf-8")).hexdigest()[:12] if raw_outcome else None
    return result


def _diversified_selection(fused: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit), 30))
    if len(fused) <= limit:
        return sorted(fused, key=_score, reverse=True)

    by_type: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in sorted(fused, key=_score, reverse=True):
        by_type[str(item.get("event_type") or "other")].append(item)

    type_order = sorted(by_type, key=lambda key: _score(by_type[key][0]), reverse=True)
    max_per_type = 5 if limit >= 12 else max(2, (limit + 2) // 3)
    selected: list[dict[str, Any]] = []
    taken: dict[str, int] = defaultdict(int)

    progress = True
    while progress and len(selected) < limit:
        progress = False
        for event_type in type_order:
            if len(selected) >= limit:
                break
            if taken[event_type] >= max_per_type:
                continue
            bucket = by_type[event_type]
            if taken[event_type] < len(bucket):
                selected.append(bucket[taken[event_type]])
                taken[event_type] += 1
                progress = True

    return sorted(selected, key=_score, reverse=True)


class EvidenceScenarioFusion:
    """Fuse true duplicates while preserving geographically distinct world scenarios."""

    VERSION = "evidence-scenario-fusion-v2-world-eye"

    def fuse(self, forecasts: list[dict[str, Any]], *, limit: int = 10) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for forecast in forecasts:
            groups.setdefault(_group_key(forecast), []).append(forecast)

        fused: list[dict[str, Any]] = []
        for key, group in groups.items():
            ordered = sorted(group, key=_score, reverse=True)
            representative = deepcopy(ordered[0])
            all_drivers = [driver for item in ordered for driver in (item.get("drivers") or []) if isinstance(driver, dict)]
            all_evidence = [evidence for item in ordered for evidence in (item.get("evidence") or []) if isinstance(evidence, dict)]
            representative["drivers"] = _unique_dicts(all_drivers, _driver_key, 16)
            representative["evidence"] = _unique_dicts(all_evidence, _evidence_key, 16)
            representative["scenario_key"] = _stable_key(key)

            supporting_event_ids = sorted({int(item["event_id"]) for item in ordered if item.get("event_id") is not None})
            supporting_candidate_ids = sorted({int(item["candidate_id"]) for item in ordered if item.get("candidate_id") is not None})
            source_keys = sorted({str(source) for driver in representative["drivers"] for source in (driver.get("source_classes") or []) if source})
            representative["fusion"] = {
                "engine": self.VERSION,
                "raw_forecast_count": len(ordered),
                "supporting_event_ids": supporting_event_ids,
                "supporting_candidate_ids": supporting_candidate_ids,
                "source_keys": source_keys,
                "duplicate_probability_inflation_prevented": True,
                "probability_merge_method": "strongest_representative_not_recomputed",
                "probability_recomputed_after_fusion": False,
                "geography_aware_grouping": True,
                "group_geography_scope": _geography_scope(representative),
                "group_time_bucket": _time_bucket(representative),
            }
            components = dict(representative.get("model_components") or {})
            components["source_diversity"] = max(int(components.get("source_diversity") or 0), len(source_keys))
            components["fusion_raw_forecast_count"] = len(ordered)
            components["fusion_changes_probability"] = False
            representative["model_components"] = components
            fused.append(_publicize(representative, len(ordered)))

        return _diversified_selection(fused, limit)
