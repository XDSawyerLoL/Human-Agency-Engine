from __future__ import annotations

from datetime import datetime
from statistics import mean

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..future_schemas import FutureCompareRequest, FutureScenarioInput
from ..models import (
    ForecastOutcome,
    FutureRun,
    FutureScenario,
    Intent,
    PersonalMandate,
    StateFact,
    User,
)

ENGINE_VERSION = "future-v0.1"

EVIDENCE_CAP = {
    "none": 0.35,
    "observational": 0.55,
    "personal_repeated": 0.70,
    "quasi_experimental": 0.82,
    "experimental": 0.92,
}


def _now() -> datetime:
    return datetime.utcnow()


def _serialize_fact(fact: StateFact) -> dict:
    return {
        "id": fact.id,
        "domain": fact.domain,
        "key": fact.key,
        "value": fact.value,
        "source": fact.source,
        "confidence": fact.confidence,
        "sensitivity": fact.sensitivity,
        "observed_at": fact.observed_at.isoformat(),
        "expires_at": fact.expires_at.isoformat() if fact.expires_at else None,
    }


def _signed(value: float, direction: str) -> float:
    return value if direction == "higher_is_better" else -value


class FutureEngine:
    """Scenario comparison engine.

    It deliberately does not output event probabilities. Numeric confidence is an
    input/evidence reliability index used for gating and audit, not P(outcome).
    """

    def __init__(self, db: Session):
        self.db = db

    def compare(self, user: User, payload: FutureCompareRequest) -> tuple[FutureRun, list[FutureScenario]]:
        state_snapshot, state_confidences = self._state_snapshot(user)
        intent_snapshot = self._intent_snapshot(user)
        mandate_snapshot = self._mandate_snapshot(user)

        run = FutureRun(
            user_id=user.id,
            horizon_days=payload.horizon_days,
            objective=payload.objective,
            state_snapshot=state_snapshot,
            intent_snapshot=intent_snapshot,
            mandate_snapshot=mandate_snapshot,
            engine_version=ENGINE_VERSION,
        )
        self.db.add(run)
        self.db.flush()

        baseline_metrics = self._baseline_metrics(user, payload.horizon_days, state_snapshot)
        baseline_confidence = min(0.75, mean(state_confidences)) if state_confidences else 0.40
        baseline = FutureScenario(
            run_id=run.id,
            name="Do nothing / current trajectory",
            scenario_type="baseline",
            intervention={},
            assumptions=[],
            projected_metrics=baseline_metrics,
            uncertainty={
                "interval_semantics": "mechanical baseline; not a probability forecast",
                "confidence_semantics": "input reliability index, not event probability",
                "known_unknowns": self._known_unknowns(user, state_snapshot),
            },
            evidence={"level": "none", "sources": [], "notes": "baseline from current known state"},
            agency_delta={},
            confidence=round(baseline_confidence, 4),
            claim_level="projection",
            robustness="baseline",
        )
        self.db.add(baseline)

        scenarios = [baseline]
        for item in payload.scenarios:
            scenario = self._build_scenario(
                user=user,
                run=run,
                input_scenario=item,
                baseline_metrics=baseline_metrics,
                mandate_snapshot=mandate_snapshot,
                known_unknowns=self._known_unknowns(user, state_snapshot),
            )
            self.db.add(scenario)
            scenarios.append(scenario)

        self.db.commit()
        self.db.refresh(run)
        for scenario in scenarios:
            self.db.refresh(scenario)
        return run, scenarios

    def _state_snapshot(self, user: User) -> tuple[dict, list[float]]:
        now = _now()
        facts = (
            self.db.query(StateFact)
            .filter(
                StateFact.user_id == user.id,
                StateFact.superseded == False,  # noqa: E712
                or_(StateFact.expires_at.is_(None), StateFact.expires_at > now),
            )
            .all()
        )
        selected: dict[tuple[str, str], StateFact] = {}
        for fact in facts:
            identity = (fact.domain, fact.key)
            current = selected.get(identity)
            if current is None or (fact.confidence, fact.observed_at) > (current.confidence, current.observed_at):
                selected[identity] = fact

        domains: dict[str, dict] = {}
        confidences: list[float] = []
        for (domain, key), fact in selected.items():
            domains.setdefault(domain, {})[key] = _serialize_fact(fact)
            confidences.append(float(fact.confidence))

        return {
            "user_fields": {
                "country": user.country,
                "currency": user.currency,
                "timezone": user.timezone,
                "monthly_income": user.monthly_income,
                "monthly_fixed_costs": user.monthly_fixed_costs,
                "liquid_cash": user.liquid_cash,
                "minimum_cash_buffer": user.minimum_cash_buffer,
            },
            "facts": domains,
            "captured_at": now.isoformat(),
        }, confidences

    def _intent_snapshot(self, user: User) -> list[dict]:
        intents = (
            self.db.query(Intent)
            .filter(Intent.user_id == user.id, Intent.active == True)  # noqa: E712
            .order_by(Intent.priority.desc())
            .all()
        )
        return [
            {
                "id": item.id,
                "kind": item.kind,
                "statement": item.statement,
                "target": item.target,
                "priority": item.priority,
            }
            for item in intents
        ]

    def _mandate_snapshot(self, user: User) -> dict:
        mandate = (
            self.db.query(PersonalMandate)
            .filter(PersonalMandate.user_id == user.id)
            .one_or_none()
        )
        if not mandate:
            return {}
        return {
            "mission": mandate.mission,
            "principles": mandate.principles,
            "constraints": mandate.constraints,
            "autonomy": mandate.autonomy,
            "version": mandate.version,
        }

    def _baseline_metrics(self, user: User, horizon_days: int, state_snapshot: dict) -> dict:
        metrics: dict[str, dict] = {}

        if (
            user.liquid_cash is not None
            and user.monthly_income is not None
            and user.monthly_fixed_costs is not None
        ):
            months = horizon_days / 30.4375
            central = float(user.liquid_cash) + (
                float(user.monthly_income) - float(user.monthly_fixed_costs)
            ) * months
            metrics["cash_balance"] = {
                "low": round(central, 2),
                "central": round(central, 2),
                "high": round(central, 2),
                "unit": user.currency,
                "direction": "higher_is_better",
                "method": "mechanical_current_run_rate",
                "probabilistic": False,
            }

        metric_facts = state_snapshot.get("facts", {}).get("metric", {})
        for key, record in metric_facts.items():
            value = record.get("value", {})
            amount = value.get("amount")
            if isinstance(amount, (int, float)):
                metrics[key] = {
                    "low": float(amount),
                    "central": float(amount),
                    "high": float(amount),
                    "unit": str(value.get("unit", "")),
                    "direction": str(value.get("direction", "higher_is_better")),
                    "method": "current_state_fact",
                    "probabilistic": False,
                }
        return metrics

    def _build_scenario(
        self,
        user: User,
        run: FutureRun,
        input_scenario: FutureScenarioInput,
        baseline_metrics: dict,
        mandate_snapshot: dict,
        known_unknowns: list[str],
    ) -> FutureScenario:
        assumptions = [item.model_dump() for item in input_scenario.assumptions]
        assumption_confidence = (
            mean(item.confidence for item in input_scenario.assumptions)
            if input_scenario.assumptions
            else 0.35
        )
        evidence = input_scenario.evidence.model_dump()
        evidence_cap = EVIDENCE_CAP[input_scenario.evidence.level]
        confidence = min(assumption_confidence, evidence_cap)

        projected: dict[str, dict] = {}
        agency_delta: dict[str, dict] = {}
        signed_lows: list[float] = []
        signed_centrals: list[float] = []

        for metric, effect in input_scenario.effects.items():
            effect_data = effect.model_dump()
            base = baseline_metrics.get(metric)
            if base:
                low = float(base["central"]) + effect.low
                central = float(base["central"]) + effect.central
                high = float(base["central"]) + effect.high
                relative_only = False
            else:
                low, central, high = effect.low, effect.central, effect.high
                relative_only = True

            projected[metric] = {
                "low": round(low, 4),
                "central": round(central, 4),
                "high": round(high, 4),
                "unit": effect.unit,
                "direction": effect.direction,
                "relative_to_unknown_baseline": relative_only,
                "rationale": effect.rationale,
                "probabilistic": False,
            }
            agency_delta[metric] = {
                "low": effect.low,
                "central": effect.central,
                "high": effect.high,
                "unit": effect.unit,
                "direction": effect.direction,
            }
            signed_lows.append(_signed(effect.low, effect.direction))
            signed_centrals.append(_signed(effect.central, effect.direction))

        violations = self._mandate_violations(
            user=user,
            intervention=input_scenario.intervention,
            projected_metrics=projected,
            mandate_snapshot=mandate_snapshot,
        )
        robustness = self._robustness(signed_lows, signed_centrals, violations)
        claim_level = self._claim_level(input_scenario.evidence.level)

        return FutureScenario(
            run_id=run.id,
            name=input_scenario.name,
            scenario_type="intervention",
            intervention=input_scenario.intervention,
            assumptions=assumptions,
            projected_metrics=projected,
            uncertainty={
                "interval_semantics": "scenario bounds supplied by assumptions/rules; not probability intervals",
                "confidence_semantics": "minimum of assumption reliability and evidence cap; not P(success)",
                "assumption_confidence": round(assumption_confidence, 4),
                "evidence_cap": evidence_cap,
                "known_unknowns": known_unknowns,
                "mandate_violations": violations,
            },
            evidence=evidence,
            agency_delta=agency_delta,
            confidence=round(confidence, 4),
            claim_level=claim_level,
            robustness=robustness,
        )

    def _mandate_violations(
        self,
        user: User,
        intervention: dict,
        projected_metrics: dict,
        mandate_snapshot: dict,
    ) -> list[str]:
        violations: list[str] = []
        constraints = mandate_snapshot.get("constraints", {}) if mandate_snapshot else {}
        action_type = str(intervention.get("type", ""))
        forbidden = set(constraints.get("forbidden_action_types", []))
        if action_type and action_type in forbidden:
            violations.append(f"action type '{action_type}' is forbidden by personal mandate")

        max_cost = constraints.get("max_one_time_cost")
        cost = intervention.get("one_time_cost")
        if isinstance(max_cost, (int, float)) and isinstance(cost, (int, float)) and cost > max_cost:
            violations.append("one-time cost exceeds personal mandate limit")

        cash = projected_metrics.get("cash_balance")
        if cash and float(cash.get("low", 0)) < float(user.minimum_cash_buffer):
            violations.append("conservative cash scenario falls below minimum cash buffer")
        return violations

    def _robustness(self, lows: list[float], centrals: list[float], violations: list[str]) -> str:
        if violations:
            return "blocked_by_mandate"
        if not centrals:
            return "insufficient_effect_model"
        if all(value >= 0 for value in lows) and any(value > 0 for value in centrals):
            return "robust_improvement"
        if all(value >= 0 for value in centrals) and any(value < 0 for value in lows):
            return "fragile_improvement"
        if any(value > 0 for value in centrals) and any(value < 0 for value in centrals):
            return "tradeoff"
        if all(value <= 0 for value in centrals):
            return "likely_worse"
        return "uncertain"

    def _claim_level(self, evidence_level: str) -> str:
        if evidence_level in {"quasi_experimental", "experimental"}:
            return "causal_supported"
        if evidence_level == "personal_repeated":
            return "personal_empirical"
        return "projection"

    def _known_unknowns(self, user: User, state_snapshot: dict) -> list[str]:
        unknowns: list[str] = []
        if user.monthly_income is None:
            unknowns.append("monthly_income")
        if user.monthly_fixed_costs is None:
            unknowns.append("monthly_fixed_costs")
        if user.liquid_cash is None:
            unknowns.append("liquid_cash")
        if not state_snapshot.get("facts"):
            unknowns.append("no temporal state facts")
        return unknowns

    def calibration(self, user: User) -> dict:
        runs = self.db.query(FutureRun).filter(FutureRun.user_id == user.id).all()
        run_ids = [run.id for run in runs]
        if not run_ids:
            return {"runs": 0, "observations": 0, "metrics": {}}

        outcomes = (
            self.db.query(ForecastOutcome)
            .filter(ForecastOutcome.run_id.in_(run_ids))
            .all()
        )
        scenario_ids = [item.scenario_id for item in outcomes if item.scenario_id is not None]
        scenarios = {
            item.id: item
            for item in self.db.query(FutureScenario).filter(FutureScenario.id.in_(scenario_ids)).all()
        } if scenario_ids else {}

        metric_stats: dict[str, dict] = {}
        for outcome in outcomes:
            scenario = scenarios.get(outcome.scenario_id)
            if not scenario:
                continue
            for metric, observed in outcome.observed_metrics.items():
                projected = scenario.projected_metrics.get(metric)
                if not projected:
                    continue
                actual = observed.get("value") if isinstance(observed, dict) else observed
                if not isinstance(actual, (int, float)):
                    continue
                central = projected.get("central")
                low = projected.get("low")
                high = projected.get("high")
                if not all(isinstance(v, (int, float)) for v in (central, low, high)):
                    continue
                stats = metric_stats.setdefault(
                    metric,
                    {
                        "observations": 0,
                        "interval_hits": 0,
                        "absolute_error_sum": 0.0,
                        "unit": projected.get("unit", ""),
                    },
                )
                stats["observations"] += 1
                stats["interval_hits"] += int(low <= actual <= high)
                stats["absolute_error_sum"] += abs(float(actual) - float(central))

        for stats in metric_stats.values():
            n = stats["observations"]
            stats["interval_coverage"] = round(stats["interval_hits"] / n, 4) if n else None
            stats["mean_absolute_error"] = round(stats["absolute_error_sum"] / n, 4) if n else None
            del stats["absolute_error_sum"]

        return {
            "runs": len(runs),
            "observations": len(outcomes),
            "metrics": metric_stats,
            "warning": "coverage is empirical calibration of declared scenario bounds, not proof of causal validity",
        }
