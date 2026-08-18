from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import FutureRun, FutureScenario


class DecisionLab:
    """Inspect a future run before commitment.

    This layer prefers information gathering and reversible pilots when the model is
    uncertain. It does not authorize execution and does not convert confidence into
    a probability of success.
    """

    def __init__(self, db: Session):
        self.db = db

    def analyze(self, run: FutureRun) -> dict:
        scenarios = (
            self.db.query(FutureScenario)
            .filter(FutureScenario.run_id == run.id)
            .order_by(FutureScenario.id.asc())
            .all()
        )
        interventions = [item for item in scenarios if item.scenario_type != "baseline"]
        frontier_ids, dominated_by, incomparable = self._pareto_frontier(interventions)

        analyses = []
        information_actions: list[dict] = []
        for scenario in interventions:
            analysis = self._analyze_scenario(scenario)
            analysis["pareto_frontier"] = scenario.id in frontier_ids
            analysis["dominated_by"] = dominated_by.get(scenario.id, [])
            analyses.append(analysis)
            information_actions.extend(analysis["information_actions"])

        information_actions = self._deduplicate_actions(information_actions)
        leading = self._leading_candidate(analyses)

        return {
            "run_id": run.id,
            "objective": run.objective,
            "horizon_days": run.horizon_days,
            "scenario_analysis": analyses,
            "pareto_frontier_ids": sorted(frontier_ids),
            "incomparable_pairs": incomparable,
            "information_actions": information_actions,
            "leading_candidate": leading,
            "commitment_policy": {
                "autonomous_commit_allowed": False,
                "principle": "prefer information gathering or reversible pilots before irreversible commitment under material uncertainty",
            },
            "interpretation": {
                "confidence_is_probability": False,
                "pareto_frontier_is_recommendation": False,
                "leading_candidate_is_authorization": False,
            },
        }

    def _analyze_scenario(self, scenario: FutureScenario) -> dict:
        reversible = scenario.intervention.get("reversible")
        if reversible is True:
            reversibility = "reversible"
        elif reversible is False:
            reversibility = "irreversible"
        else:
            reversibility = "unknown"

        crossings = []
        for metric, delta in scenario.agency_delta.items():
            low = delta.get("low")
            high = delta.get("high")
            direction = delta.get("direction", "higher_is_better")
            if isinstance(low, (int, float)) and isinstance(high, (int, float)):
                signed_low = low if direction == "higher_is_better" else -high
                signed_high = high if direction == "higher_is_better" else -low
                if signed_low < 0 < signed_high:
                    crossings.append(metric)

        actions: list[dict] = []
        for assumption in scenario.assumptions:
            confidence = float(assumption.get("confidence", 0.0))
            if confidence >= 0.75:
                continue
            falsifiable_by = str(assumption.get("falsifiable_by", "")).strip()
            statement = str(assumption.get("statement", "unknown assumption"))
            actions.append(
                {
                    "type": "verify_assumption",
                    "scenario_id": scenario.id,
                    "question": falsifiable_by or f"Verify: {statement}",
                    "reason": f"assumption confidence is {confidence:.2f}",
                    "priority": "high" if confidence < 0.5 else "medium",
                }
            )

        for unknown in scenario.uncertainty.get("known_unknowns", []):
            actions.append(
                {
                    "type": "resolve_missing_state",
                    "scenario_id": scenario.id,
                    "question": f"Resolve missing state: {unknown}",
                    "reason": "baseline depends on incomplete personal state",
                    "priority": "medium",
                }
            )

        if reversibility == "unknown":
            actions.append(
                {
                    "type": "check_reversibility",
                    "scenario_id": scenario.id,
                    "question": "Determine reversibility, lock-in duration and reversal cost before commitment",
                    "reason": "intervention reversibility is not modeled",
                    "priority": "high" if scenario.robustness in {"fragile_improvement", "tradeoff"} else "medium",
                }
            )

        if crossings:
            actions.append(
                {
                    "type": "reduce_sign_uncertainty",
                    "scenario_id": scenario.id,
                    "question": "Narrow the effect range for: " + ", ".join(sorted(crossings)),
                    "reason": "current bounds include both improvement and harm",
                    "priority": "high",
                }
            )

        status = self._decision_status(scenario, reversibility, crossings)
        return {
            "scenario_id": scenario.id,
            "name": scenario.name,
            "robustness": scenario.robustness,
            "claim_level": scenario.claim_level,
            "confidence": scenario.confidence,
            "reversibility": reversibility,
            "lock_in_days": scenario.intervention.get("lock_in_days"),
            "reversal_cost": scenario.intervention.get("reversal_cost"),
            "sign_uncertain_metrics": crossings,
            "decision_status": status,
            "information_actions": actions,
        }

    def _decision_status(self, scenario: FutureScenario, reversibility: str, crossings: list[str]) -> str:
        if scenario.robustness == "blocked_by_mandate":
            return "do_not_act"
        if scenario.robustness == "likely_worse":
            return "do_not_prefer"
        if scenario.robustness == "insufficient_effect_model":
            return "model_more_before_deciding"
        if crossings or scenario.robustness in {"fragile_improvement", "tradeoff"}:
            return "gather_information_or_run_pilot"
        if scenario.robustness == "robust_improvement":
            if scenario.confidence < 0.55:
                return "verify_before_pilot"
            if reversibility == "irreversible":
                return "seek_stronger_evidence_before_commitment"
            if scenario.confidence < 0.70:
                return "candidate_for_reversible_pilot"
            return "strong_candidate_for_user_review"
        return "insufficient_information"

    def _central_vector(self, scenario: FutureScenario) -> dict[str, float]:
        vector: dict[str, float] = {}
        for metric, delta in scenario.agency_delta.items():
            central = delta.get("central")
            if not isinstance(central, (int, float)):
                continue
            direction = delta.get("direction", "higher_is_better")
            vector[metric] = float(central) if direction == "higher_is_better" else -float(central)
        return vector

    def _pareto_frontier(self, scenarios: list[FutureScenario]) -> tuple[set[int], dict[int, list[int]], list[list[int]]]:
        eligible = [item for item in scenarios if item.robustness != "blocked_by_mandate"]
        vectors = {item.id: self._central_vector(item) for item in eligible}
        frontier = {item.id for item in eligible}
        dominated_by: dict[int, list[int]] = {}
        incomparable: list[list[int]] = []

        for i, left in enumerate(eligible):
            for right in eligible[i + 1 :]:
                lv = vectors[left.id]
                rv = vectors[right.id]
                if not lv or set(lv) != set(rv):
                    incomparable.append([left.id, right.id])
                    continue
                left_dominates = all(lv[k] >= rv[k] for k in lv) and any(lv[k] > rv[k] for k in lv)
                right_dominates = all(rv[k] >= lv[k] for k in lv) and any(rv[k] > lv[k] for k in lv)
                if left_dominates:
                    frontier.discard(right.id)
                    dominated_by.setdefault(right.id, []).append(left.id)
                elif right_dominates:
                    frontier.discard(left.id)
                    dominated_by.setdefault(left.id, []).append(right.id)
        return frontier, dominated_by, incomparable

    def _leading_candidate(self, analyses: list[dict]) -> dict | None:
        candidates = [
            item
            for item in analyses
            if item["pareto_frontier"]
            and item["decision_status"] == "strong_candidate_for_user_review"
        ]
        if len(candidates) != 1:
            return None
        item = candidates[0]
        return {
            "scenario_id": item["scenario_id"],
            "name": item["name"],
            "reason": "single non-dominated robust scenario with stronger evidence/reliability; still requires user review",
        }

    def _deduplicate_actions(self, actions: list[dict]) -> list[dict]:
        seen: set[tuple[str, str]] = set()
        unique = []
        for item in actions:
            key = (item["type"], item["question"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        priority_order = {"high": 0, "medium": 1, "low": 2}
        return sorted(unique, key=lambda item: (priority_order.get(item["priority"], 9), item["type"]))
