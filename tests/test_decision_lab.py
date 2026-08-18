from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _user(uid: str):
    response = client.put(
        f"/v1/users/{uid}",
        json={
            "external_id": uid,
            "monthly_income": 2500,
            "monthly_fixed_costs": 1800,
            "liquid_cash": 2000,
            "minimum_cash_buffer": 500,
        },
    )
    assert response.status_code == 200


def test_decision_lab_finds_non_dominated_strong_candidate_without_authorizing_it():
    uid = "decision-lab-a"
    _user(uid)

    created = client.post(
        f"/v1/users/{uid}/future/compare",
        json={
            "horizon_days": 90,
            "objective": "Increase future options",
            "scenarios": [
                {
                    "name": "Pilot A",
                    "intervention": {"type": "pilot", "reversible": True, "lock_in_days": 0},
                    "effects": {
                        "optionality": {
                            "low": 1,
                            "central": 2,
                            "high": 3,
                            "unit": "paths",
                            "direction": "higher_is_better",
                        }
                    },
                    "assumptions": [
                        {"statement": "Pilot completes", "confidence": 0.9, "source": "test"}
                    ],
                    "evidence": {"level": "experimental", "sources": ["synthetic"]},
                },
                {
                    "name": "Pilot B",
                    "intervention": {"type": "pilot", "reversible": True, "lock_in_days": 0},
                    "effects": {
                        "optionality": {
                            "low": 0,
                            "central": 1,
                            "high": 1,
                            "unit": "paths",
                            "direction": "higher_is_better",
                        }
                    },
                    "assumptions": [
                        {"statement": "Pilot completes", "confidence": 0.9, "source": "test"}
                    ],
                    "evidence": {"level": "experimental", "sources": ["synthetic"]},
                },
            ],
        },
    )
    assert created.status_code == 200
    data = created.json()
    run_id = data["run"]["id"]
    first_id = data["scenarios"][1]["id"]
    second_id = data["scenarios"][2]["id"]

    lab = client.get(f"/v1/future/runs/{run_id}/decision-lab")
    assert lab.status_code == 200
    result = lab.json()
    assert result["commitment_policy"]["autonomous_commit_allowed"] is False
    assert result["pareto_frontier_ids"] == [first_id]
    second = next(item for item in result["scenario_analysis"] if item["scenario_id"] == second_id)
    assert first_id in second["dominated_by"]
    assert result["leading_candidate"]["scenario_id"] == first_id


def test_decision_lab_prefers_information_gathering_when_effect_sign_is_uncertain():
    uid = "decision-lab-b"
    _user(uid)

    created = client.post(
        f"/v1/users/{uid}/future/compare",
        json={
            "horizon_days": 30,
            "objective": "Avoid premature commitment",
            "scenarios": [
                {
                    "name": "Uncertain intervention",
                    "intervention": {"type": "unknown_reversibility"},
                    "effects": {
                        "optionality": {
                            "low": -2,
                            "central": 1,
                            "high": 4,
                            "unit": "paths",
                            "direction": "higher_is_better",
                        }
                    },
                    "assumptions": [
                        {
                            "statement": "Demand remains available",
                            "confidence": 0.4,
                            "source": "test",
                            "falsifiable_by": "Check the live demand signal",
                        }
                    ],
                    "evidence": {"level": "observational", "sources": []},
                }
            ],
        },
    )
    assert created.status_code == 200
    run_id = created.json()["run"]["id"]

    lab = client.get(f"/v1/future/runs/{run_id}/decision-lab")
    assert lab.status_code == 200
    result = lab.json()
    scenario = result["scenario_analysis"][0]
    assert scenario["decision_status"] == "gather_information_or_run_pilot"
    assert "optionality" in scenario["sign_uncertain_metrics"]
    types = {item["type"] for item in result["information_actions"]}
    assert "verify_assumption" in types
    assert "check_reversibility" in types
    assert "reduce_sign_uncertainty" in types
    questions = [item["question"] for item in result["information_actions"]]
    assert "Check the live demand signal" in questions
