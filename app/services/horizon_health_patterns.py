from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from ..horizon_models import HorizonBehaviorPattern


PATTERN_KEY = "world-disease-outbreak-response-v1"


class HorizonHealthPatternService:
    def __init__(self, db: Session):
        self.db = db

    def sync(self) -> int:
        row = self.db.query(HorizonBehaviorPattern).filter(
            HorizonBehaviorPattern.pattern_key == PATTERN_KEY
        ).one_or_none()
        if row is None:
            row = HorizonBehaviorPattern(
                pattern_key=PATTERN_KEY,
                name="Official outbreak report → surveillance and local response pressure",
                event_types=["disease_outbreak_signal"],
                required_signal_types=[],
                predicted_response=(
                    "Lorsqu’un foyer sanitaire fait l’objet d’un rapport officiel récent, une hausse de la surveillance, "
                    "du dépistage et des mesures locales de contrôle devient plus plausible dans les jours suivants ; "
                    "si la transmission s’étend, la pression peut ensuite toucher les soins, les déplacements ou les recommandations sanitaires."
                ),
                mechanism_chain=[
                    "foyer sanitaire officiellement documenté",
                    "surveillance et investigation renforcées",
                    "détection de cas ou contacts supplémentaires",
                    "mesures locales de contrôle ou recommandations",
                    "pression potentielle sur soins, mobilité ou comportement public si la transmission progresse",
                ],
                expected_lag_hours_low=12,
                expected_lag_hours_high=336,
                confidence=0.52,
                support_count=0,
                contradiction_count=0,
                provenance={
                    "library_version": "world-health-response-library-v0.1",
                    "status": "provisional_prior",
                    "formal_probability": False,
                    "calibrated_on_horizon_outcomes": False,
                    "evidence": [
                        {
                            "kind": "official_multilateral_reporting",
                            "source": "WHO Disease Outbreak News",
                            "locator": "https://www.who.int/api/hubs/diseaseoutbreaknews",
                        }
                    ],
                    "limitations": [
                        "Un rapport OMS ne signifie pas qu’une propagation internationale va se produire.",
                        "Le scénario porte sur la réponse et la pression aval, pas sur une prédiction automatique de pandémie.",
                    ],
                },
                knowledge_available_at=datetime(2024, 1, 1),
                status="active",
            )
            self.db.add(row)
            self.db.commit()
            self.db.refresh(row)
        return row.id
