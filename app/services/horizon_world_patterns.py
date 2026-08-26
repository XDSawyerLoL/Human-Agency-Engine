from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..horizon_models import HorizonBehaviorPattern


WORLD_PATTERN_VERSION = "world-pulse-response-library-v0.1"

WORLD_PATTERNS = (
    {
        "pattern_key": "world-financial-stress-risk-off-v1",
        "name": "Financial stress → defensive positioning and tighter financing",
        "event_types": ["financial_stress"],
        "predicted_response": "Une montée inhabituelle du stress financier peut être suivie d’un recul de l’appétit pour le risque, d’un durcissement des conditions de financement et d’une pression accrue sur les actifs et entreprises les plus fragiles.",
        "mechanism_chain": ["hausse de l’incertitude financière", "réduction de l’exposition au risque", "hausse des primes de risque", "durcissement des conditions de financement", "pression visible sur les actifs et emprunteurs fragiles"],
        "expected_lag_hours_low": 6,
        "expected_lag_hours_high": 336,
        "confidence": 0.55,
        "knowledge_available_at": datetime(2019, 1, 1),
        "provenance": {"library_version": WORLD_PATTERN_VERSION, "status": "provisional_prior", "formal_probability": False, "calibrated_on_horizon_outcomes": False, "limitations": ["Un pic de volatilité peut se résorber rapidement.", "Ce mécanisme ne constitue pas une prévision directionnelle d’un indice boursier."]},
    },
    {
        "pattern_key": "world-credit-stress-financing-v1",
        "name": "Credit spread stress → financing pressure",
        "event_types": ["credit_stress"],
        "predicted_response": "Un élargissement rapide des spreads de crédit peut annoncer un financement plus coûteux, davantage de refinancements difficiles et une montée graduelle des mesures défensives des entreprises exposées.",
        "mechanism_chain": ["hausse de la prime de crédit", "coût de refinancement plus élevé", "accès au financement plus sélectif", "réduction d’investissement ou mesures défensives", "pression sur l’emploi ou les défauts des acteurs fragiles"],
        "expected_lag_hours_low": 24,
        "expected_lag_hours_high": 720,
        "confidence": 0.54,
        "knowledge_available_at": datetime(2018, 1, 1),
        "provenance": {"library_version": WORLD_PATTERN_VERSION, "status": "provisional_prior", "formal_probability": False, "calibrated_on_horizon_outcomes": False, "limitations": ["Les spreads peuvent refléter des facteurs techniques temporaires.", "Le modèle ne déduit pas automatiquement une récession ou un défaut."]},
    },
    {
        "pattern_key": "world-energy-price-pass-through-v1",
        "name": "Rapid oil-price rise → transport and inflation pressure",
        "event_types": ["energy_price_spike"],
        "predicted_response": "Une hausse rapide et persistante du pétrole peut être suivie d’une pression sur les carburants, le transport et certains coûts de production, avec un risque de transmission partielle aux prix dans les semaines suivantes.",
        "mechanism_chain": ["hausse rapide du brut", "coûts de raffinage et d’approvisionnement plus élevés", "pression sur les carburants et le fret", "hausse de coûts pour les secteurs énergivores", "transmission partielle aux prix finaux"],
        "expected_lag_hours_low": 24,
        "expected_lag_hours_high": 504,
        "confidence": 0.57,
        "knowledge_available_at": datetime(2020, 1, 1),
        "provenance": {"library_version": WORLD_PATTERN_VERSION, "status": "provisional_prior", "formal_probability": False, "calibrated_on_horizon_outcomes": False, "limitations": ["Taxes, stocks, marges et taux de change modifient fortement la transmission.", "Une hausse ponctuelle du brut ne garantit pas une hausse durable des prix de détail."]},
    },
    {
        "pattern_key": "world-labor-softening-defensive-v1",
        "name": "Labor-market softening → weaker hiring and defensive household behavior",
        "event_types": ["labor_market_softening"],
        "predicted_response": "Une détérioration persistante des inscriptions au chômage peut précéder un ralentissement des embauches, une prudence accrue des ménages concernés et une pression croissante sur certains secteurs sensibles au cycle.",
        "mechanism_chain": ["hausse des pertes ou transitions d’emploi", "recherche d’emploi plus intense", "embauches plus sélectives", "prudence de consommation des ménages exposés", "ralentissement visible dans les secteurs cycliques"],
        "expected_lag_hours_low": 72,
        "expected_lag_hours_high": 1008,
        "confidence": 0.50,
        "knowledge_available_at": datetime(2017, 1, 1),
        "provenance": {"library_version": WORLD_PATTERN_VERSION, "status": "provisional_prior", "formal_probability": False, "calibrated_on_horizon_outcomes": False, "limitations": ["Une publication hebdomadaire isolée est bruitée.", "Le scénario exige une persistance ou une corroboration avant de gagner fortement en probabilité."]},
    },
    {
        "pattern_key": "world-earthquake-aftershock-disruption-v1",
        "name": "Major earthquake → aftershock and recovery disruption",
        "event_types": ["major_earthquake"],
        "predicted_response": "Après un séisme important, de nouvelles secousses et des perturbations locales de mobilité, d’accès ou de services restent plus probables pendant la phase de réponse, avec un risque de dommages additionnels sur les infrastructures déjà fragilisées.",
        "mechanism_chain": ["séisme principal", "séquence d’après-chocs", "inspection et restrictions d’accès", "capacité locale de transport ou de services réduite", "retards de secours et de remise en service"],
        "expected_lag_hours_low": 0,
        "expected_lag_hours_high": 168,
        "confidence": 0.70,
        "knowledge_available_at": datetime(2024, 7, 25),
        "provenance": {"library_version": WORLD_PATTERN_VERSION, "status": "official_mechanism_supported", "formal_probability": False, "calibrated_on_horizon_outcomes": False, "evidence": [{"kind": "official_science", "source": "USGS", "locator": "https://earthquake.usgs.gov/data/oaf/overview.php", "note": "USGS operational aftershock forecasts document elevated aftershock activity following significant earthquakes."}], "limitations": ["Évidence ne prétend pas prévoir l’emplacement et l’heure d’un nouveau séisme principal.", "Les conséquences dépendent de la profondeur, de l’exposition et de la vulnérabilité locale."]},
    },
    {
        "pattern_key": "world-geomagnetic-storm-operations-v1",
        "name": "Geomagnetic storm forecast → navigation and infrastructure precautions",
        "event_types": ["geomagnetic_storm_risk"],
        "predicted_response": "Si la prévision de tempête géomagnétique se maintient, les opérateurs de satellites, de navigation, de radio et de réseaux électriques peuvent renforcer leur surveillance et des perturbations temporaires deviennent plus plausibles aux latitudes exposées.",
        "mechanism_chain": ["activité géomagnétique prévue en hausse", "conditions ionosphériques plus perturbées", "surveillance opérationnelle renforcée", "dégradation possible du GNSS, de la radio ou de certains systèmes", "mesures de mitigation et perturbations observables"],
        "expected_lag_hours_low": 0,
        "expected_lag_hours_high": 72,
        "confidence": 0.58,
        "knowledge_available_at": datetime(2023, 1, 1),
        "provenance": {"library_version": WORLD_PATTERN_VERSION, "status": "provisional_prior", "formal_probability": False, "calibrated_on_horizon_outcomes": False, "evidence": [{"kind": "official_forecast_stream", "source": "NOAA SWPC", "locator": "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"}], "limitations": ["Une prévision Kp n’implique pas automatiquement une panne.", "L’impact dépend de la latitude, du secteur et des mesures de mitigation."]},
    },
    {
        "pattern_key": "world-disaster-activation-logistics-v1",
        "name": "Emergency activation → logistics and humanitarian pressure",
        "event_types": ["flood_emergency", "wildfire_emergency", "severe_storm_emergency", "volcanic_emergency", "drought_emergency", "large_disaster_activation"],
        "predicted_response": "Une activation d’urgence récente peut être suivie d’une hausse des besoins d’évacuation, de cartographie, de logistique et d’assistance, ainsi que de perturbations locales d’accès ou de transport si l’événement continue de s’étendre.",
        "mechanism_chain": ["événement naturel ou humanitaire suffisamment important pour activer une réponse", "zones d’intérêt et dommages à cartographier", "contraintes d’accès ou évacuations", "hausse des besoins logistiques et d’assistance", "pression observable sur mobilité, infrastructures ou secours"],
        "expected_lag_hours_low": 0,
        "expected_lag_hours_high": 120,
        "confidence": 0.56,
        "knowledge_available_at": datetime(2024, 11, 14),
        "provenance": {"library_version": WORLD_PATTERN_VERSION, "status": "provisional_prior", "formal_probability": False, "calibrated_on_horizon_outcomes": False, "evidence": [{"kind": "official_multilateral_stream", "source": "Copernicus EMS", "locator": "https://rapidmapping.emergency.copernicus.eu/backend/dashboard-api/public-activations-info/"}], "limitations": ["Une activation cartographique n’est pas une mesure directe de l’ampleur finale des dégâts.", "Les conséquences locales doivent être confirmées par des observations indépendantes."]},
    },
)


class HorizonWorldPatternService:
    def __init__(self, db: Session):
        self.db = db

    def sync(self) -> list[int]:
        ids: list[int] = []
        for spec in WORLD_PATTERNS:
            row = self.db.query(HorizonBehaviorPattern).filter(
                HorizonBehaviorPattern.pattern_key == spec["pattern_key"]
            ).one_or_none()
            if row is None:
                row = HorizonBehaviorPattern(
                    pattern_key=spec["pattern_key"],
                    name=spec["name"],
                    event_types=spec["event_types"],
                    required_signal_types=[],
                    predicted_response=spec["predicted_response"],
                    mechanism_chain=spec["mechanism_chain"],
                    expected_lag_hours_low=spec["expected_lag_hours_low"],
                    expected_lag_hours_high=spec["expected_lag_hours_high"],
                    confidence=spec["confidence"],
                    support_count=0,
                    contradiction_count=0,
                    provenance=spec["provenance"],
                    knowledge_available_at=spec["knowledge_available_at"],
                    status="active",
                )
                self.db.add(row)
                self.db.flush()
            ids.append(row.id)
        self.db.commit()
        return ids
