from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _create_user(uid: str):
    response = client.put(
        f"/v1/users/{uid}",
        json={
            "external_id": uid,
            "monthly_income": 2400,
            "monthly_fixed_costs": 1800,
            "liquid_cash": 1200,
            "minimum_cash_buffer": 500,
        },
    )
    assert response.status_code == 200


def test_future_compare_is_bounded_auditable_and_not_probability():
    uid = "future-user-a"
    _create_user(uid)

    mandate = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Increase options while preserving a cash floor.",
            "constraints": {"max_one_time_cost": 600},
            "principles": [],
            "autonomy": {},
            "notification_policy": {},
        },
    )
    assert mandate.status_code == 200

    state = client.post(
        f"/v1/users/{uid}/state/facts",
        json={
            "domain": "metric",
            "key": "optionality",
            "value": {
                "amount": 2,
                "unit": "accessible_paths",
                "direction": "higher_is_better",
            },
            "source": "user",
            "confidence": 0.9,
        },
    )
    assert state.status_code == 200

    response = client.post(
        f"/v1/users/{uid}/future/compare",
        json={
            "horizon_days": 90,
            "objective": "Create more room to choose later.",
            "scenarios": [
                {
                    "name": "Low-cost intervention",
                    "intervention": {"type": "course", "one_time_cost": 300},
                    "effects": {
                        "optionality": {
                            "low": 1,
                            "central": 2,
                            "high": 3,
                            "unit": "accessible_paths",
                            "direction": "higher_is_better",
                            "rationale": "Scenario assumption for test",
                        }
                    },
                    "assumptions": [
                        {
                            "statement": "The intervention is completed.",
                            "confidence": 0.8,
                            "source": "user",
                            "falsifiable_by": "completion record",
                        }
                    ],
                    "evidence": {
                        "level": "observational",
                        "sources": ["synthetic-test-source"],
                        "notes": "Not causal evidence",
                    },
                }
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["interpretation"]["confidence_is_probability"] is False
    assert data["interpretation"]["bounds_are_probability_intervals"] is False
    assert len(data["scenarios"]) == 2

    baseline, scenario = data["scenarios"]
    assert baseline["scenario_type"] == "baseline"
    assert scenario["claim_level"] == "projection"
    assert scenario["confidence"] == 0.55
    assert scenario["robustness"] == "robust_improvement"
    assert scenario["projected_metrics"]["optionality"]["central"] == 4.0


def test_future_scenario_can_be_blocked_by_personal_mandate():
    uid = "future-user-b"
    _create_user(uid)
    client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Protect constraints.",
            "constraints": {"max_one_time_cost": 100},
            "principles": [],
            "autonomy": {},
            "notification_policy": {},
        },
    )

    response = client.post(
        f"/v1/users/{uid}/future/compare",
        json={
            "horizon_days": 30,
            "objective": "Test mandate gating",
            "scenarios": [
                {
                    "name": "Too expensive",
                    "intervention": {"type": "purchase", "one_time_cost": 500},
                    "effects": {
                        "optionality": {
                            "low": 1,
                            "central": 1,
                            "high": 2,
                            "unit": "paths",
                            "direction": "higher_is_better",
                        }
                    },
                    "assumptions": [
                        {"statement": "Synthetic", "confidence": 0.9, "source": "test"}
                    ],
                    "evidence": {"level": "experimental", "sources": []},
                }
            ],
        },
    )
    assert response.status_code == 200
    scenario = response.json()["scenarios"][1]
    assert scenario["robustness"] == "blocked_by_mandate"
    assert "one-time cost exceeds" in " ".join(
        scenario["uncertainty"]["mandate_violations"]
    )


def test_future_calibration_uses_observed_outcome_without_claiming_causality():
    uid = "future-user-c"
    _create_user(uid)
    response = client.post(
        f"/v1/users/{uid}/future/compare",
        json={
            "horizon_days": 60,
            "objective": "Calibration",
            "scenarios": [
                {
                    "name": "Bounded change",
                    "intervention": {"type": "synthetic"},
                    "effects": {
                        "cash_balance": {
                            "low": 100,
                            "central": 200,
                            "high": 300,
                            "unit": "EUR",
                            "direction": "higher_is_better",
                        }
                    },
                    "assumptions": [
                        {"statement": "Synthetic", "confidence": 0.7, "source": "test"}
                    ],
                    "evidence": {"level": "none", "sources": []},
                }
            ],
        },
    )
    assert response.status_code == 200
    data = response.json()
    run_id = data["run"]["id"]
    scenario = data["scenarios"][1]
    scenario_id = scenario["id"]
    projected = scenario["projected_metrics"]["cash_balance"]
    actual = projected["central"] + 50

    recorded = client.post(
        f"/v1/future/runs/{run_id}/outcomes",
        json={
            "scenario_id": scenario_id,
            "observed_metrics": {"cash_balance": actual},
            "observation_window": {"days": 60},
            "notes": "synthetic observation",
        },
    )
    assert recorded.status_code == 200

    calibration = client.get(f"/v1/users/{uid}/future/calibration")
    assert calibration.status_code == 200
    stats = calibration.json()["metrics"]["cash_balance"]
    assert stats["observations"] == 1
    assert stats["interval_coverage"] == 1.0
    assert stats["mean_absolute_error"] == 50.0


def test_invalid_effect_bounds_are_rejected():
    uid = "future-user-d"
    _create_user(uid)
    response = client.post(
        f"/v1/users/{uid}/future/compare",
        json={
            "horizon_days": 30,
            "objective": "Reject fake bounds",
            "scenarios": [
                {
                    "name": "Invalid",
                    "effects": {
                        "x": {
                            "low": 10,
                            "central": 5,
                            "high": 1,
                            "unit": "u",
                            "direction": "higher_is_better",
                        }
                    },
                }
            ],
        },
    )
    assert response.status_code == 422
