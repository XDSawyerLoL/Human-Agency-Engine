from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..horizon_models import HorizonBehaviorPattern


PATTERNS = (
    {
        "pattern_key": "world-financial-stress-easing-v1",
        "name": "Projected volatility easing → financial conditions stabilization",
        "event_type": "financial_stress_easing",
        "response": "Si la détente projetée de la volatilité se confirme, l’appétit pour le risque et les conditions de financement peuvent se stabiliser progressivement, réduisant la pression immédiate sur les actifs et emprunteurs les plus fragiles.",
        "chain": ["volatilité projetée en baisse", "réduction de la demande de protection", "primes de risque plus stables", "conditions de financement moins tendues", "pression financière immédiate en recul"],
        "lag_low": 24,
        "lag_high": 336,
        "confidence": 0.43,
    },
    {
        "pattern_key": "world-credit-stress-easing-v1",
        "name": "Projected credit-spread easing → refinancing pressure stabilization",
        "event_type": "credit_stress_easing",
        "response": "Une détente projetée et ensuite observée des spreads de crédit peut signaler une stabilisation du coût de financement et réduire le risque de mesures défensives supplémentaires chez les entreprises les plus exposées.",
        "chain": ["spreads projetés en baisse", "prime de crédit moins tendue", "coût marginal de refinancement plus stable", "pression sur trésorerie en recul", "mesures défensives moins urgentes"],
        "lag_low": 48,
        "lag_high": 504,
        "confidence": 0.42,
    },
    {
        "pattern_key": "world-energy-price-relief-v1",
        "name": "Projected oil-price easing → downstream cost relief",
        "event_type": "energy_price_relief",
        "response": "Si la baisse projetée du pétrole se matérialise, une partie de la pression sur les carburants, le fret et certains coûts de production peut s’atténuer dans les semaines suivantes, sans garantir une baisse identique des prix de détail.",
        "chain": ["pétrole projeté en baisse", "coûts d’approvisionnement moins tendus", "pression sur carburants et fret en recul", "coûts sectoriels plus stables", "transmission partielle possible aux prix finaux"],
        "lag_low": 48,
        "lag_high": 504,
        "confidence": 0.45,
    },
    {
        "pattern_key": "world-labor-market-improvement-v1",
        "name": "Projected jobless-claims improvement → hiring pressure stabilization",
        "event_type": "labor_market_improvement",
        "response": "Si l’amélioration projetée des inscriptions au chômage se confirme dans les publications suivantes, le risque d’une dégradation rapide du marché du travail recule et la prudence des ménages exposés peut se stabiliser.",
        "chain": ["inscriptions projetées en baisse", "moins de transitions vers le chômage", "pression sur la recherche d’emploi en recul", "embauches moins défensives", "comportement des ménages plus stable"],
        "lag_low": 72,
        "lag_high": 672,
        "confidence": 0.40,
    },
)


class HorizonStatisticalPatternService:
    def __init__(self, db: Session):
        self.db = db

    def sync(self) -> list[int]:
        ids: list[int] = []
        for spec in PATTERNS:
            row = self.db.query(HorizonBehaviorPattern).filter(
                HorizonBehaviorPattern.pattern_key == spec["pattern_key"]
            ).one_or_none()
            if row is None:
                row = HorizonBehaviorPattern(
                    pattern_key=spec["pattern_key"],
                    name=spec["name"],
                    event_types=[spec["event_type"]],
                    required_signal_types=[],
                    predicted_response=spec["response"],
                    mechanism_chain=spec["chain"],
                    expected_lag_hours_low=spec["lag_low"],
                    expected_lag_hours_high=spec["lag_high"],
                    confidence=spec["confidence"],
                    support_count=0,
                    contradiction_count=0,
                    provenance={
                        "library_version": "forecastapi-statistical-patterns-v0.1",
                        "status": "secondary_model_prior",
                        "formal_probability": False,
                        "calibrated_on_horizon_outcomes": False,
                        "limitations": [
                            "Le précurseur vient d’un modèle de série temporelle secondaire.",
                            "L’intervalle de valeur ForecastAPI n’est pas une probabilité d’événement.",
                            "Le scénario doit être réévalué lorsque les nouvelles valeurs FRED réelles arrivent.",
                        ],
                    },
                    knowledge_available_at=datetime(2026, 8, 19),
                    status="active",
                )
                self.db.add(row)
                self.db.flush()
            ids.append(row.id)
        self.db.commit()
        return ids
