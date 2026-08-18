from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def make_user(uid: str, **overrides):
    payload = {
        "external_id": uid,
        "timezone": "Europe/Paris",
        "monthly_income": 2000,
        "monthly_fixed_costs": 1200,
        "liquid_cash": 800,
        "minimum_cash_buffer": 150,
    }
    payload.update(overrides)
    response = client.put(f"/v1/users/{uid}", json=payload)
    assert response.status_code == 200


def notifications(uid: str):
    response = client.get(
        f"/v1/users/{uid}/notifications",
        params={"include_suppressed": "true"},
    )
    assert response.status_code == 200
    return response.json()


def test_raw_opportunity_without_effect_model_stays_silent():
    uid = "synthesis-raw-silent-a"
    make_user(uid)

    signal = client.post(
        f"/v1/users/{uid}/signals",
        json={
            "source": "test",
            "type": "deadline",
            "payload": {
                "days_remaining": 5,
                "relevance": 0.9,
                "label": "synthetic deadline",
                "reason": "synthetic timing signal",
            },
        },
    )
    assert signal.status_code == 200

    run = client.post(f"/v1/users/{uid}/engine/run")
    assert run.status_code == 200
    assert any(item["category"] == "timing" for item in run.json())

    candidates = client.get(f"/v1/users/{uid}/candidates")
    assert candidates.status_code == 200
    assert len(candidates.json()) == 1
    candidate = candidates.json()[0]
    assert candidate["status"] == "needs_information"
    assert candidate["decision_status"] == "model_more_before_deciding"
    assert candidate["surfaced_opportunity_id"] is None
    assert notifications(uid) == []


def test_care_blocked_source_cannot_be_resurrected_by_future_gate():
    uid = "synthesis-care-block-b"
    make_user(uid, liquid_cash=100, minimum_cash_buffer=150)

    signal = client.post(
        f"/v1/users/{uid}/signals",
        json={
            "source": "test",
            "type": "recurring_expense",
            "payload": {
                "merchant": "Synthetic Service",
                "monthly_amount": 20,
                "usage_score": 0.1,
            },
        },
    )
    assert signal.status_code == 200

    engine = client.post(f"/v1/users/{uid}/engine/run")
    assert engine.status_code == 200
    raw = next(item for item in engine.json() if item["category"] == "money")
    assert raw["care_status"] == "blocked"

    candidates = client.get(f"/v1/users/{uid}/candidates")
    assert candidates.status_code == 200
    candidate = candidates.json()[0]
    assert candidate["status"] == "rejected"
    assert candidate["decision_status"] == "care_blocked"
    assert candidate["surfaced_opportunity_id"] is None
    assert notifications(uid) == []


def test_repeated_personal_evidence_can_reach_review_but_not_autonomy():
    uid = "synthesis-personal-evidence-c"
    make_user(uid)

    intent = client.post(
        f"/v1/users/{uid}/intents",
        json={
            "kind": "capacity",
            "statement": "increase focus time",
            "priority": 0.9,
        },
    )
    assert intent.status_code == 200

    hypothesis = client.post(
        f"/v1/users/{uid}/world/hypotheses",
        json={
            "name": "increase focus time with reversible focus block",
            "cause_pattern": {
                "intervention": {
                    "type": "reversible_focus_block",
                    "reversible": True,
                    "lock_in_days": 0,
                    "reversal_cost": 0,
                }
            },
            "effect_pattern": {
                "metrics": {
                    "focus_time": {
                        "low": 1,
                        "central": 2,
                        "high": 3,
                        "unit": "hours",
                        "direction": "higher_is_better",
                        "rationale": "bounded effect observed in synthetic personal pilots",
                    }
                }
            },
            "context": {
                "falsifiable_by": "run another reversible focus-time pilot"
            },
            "direction": "positive",
        },
    )
    assert hypothesis.status_code == 200
    hypothesis_id = hypothesis.json()["id"]

    for index in range(3):
        experiment = client.post(
            f"/v1/users/{uid}/experiments",
            json={
                "title": f"focus pilot {index}",
                "hypothesis_id": hypothesis_id,
                "intervention": {
                    "type": "reversible_focus_block",
                    "iteration": index,
                },
                "expected_effects": {
                    "focus_time": {"low": 1, "central": 2, "high": 3}
                },
                "stop_conditions": ["stop if focus time decreases"],
                "rollback_plan": {"action": "return to previous schedule"},
                "reversible": True,
            },
        )
        assert experiment.status_code == 200
        experiment_id = experiment.json()["id"]

        authorize = client.post(
            f"/v1/experiments/{experiment_id}/authorize",
            json={"confirm": f"AUTHORIZE {experiment_id}"},
        )
        assert authorize.status_code == 200
        assert client.post(f"/v1/experiments/{experiment_id}/start").status_code == 200

        observed = client.post(
            f"/v1/experiments/{experiment_id}/observations",
            json={
                "metrics": {"focus_time": 2 + index * 0.1},
                "verdict": "supports",
                "quality": 0.9,
                "notes": "synthetic repeated personal observation",
            },
        )
        assert observed.status_code == 200
        assert client.post(f"/v1/experiments/{experiment_id}/complete").status_code == 200

    hypotheses = client.get(f"/v1/users/{uid}/world/hypotheses")
    learned = next(item for item in hypotheses.json() if item["id"] == hypothesis_id)
    assert learned["claim_level"] == "personal_empirical"
    assert learned["claim_level"] != "causal_supported"

    synthesis = client.post(f"/v1/users/{uid}/synthesis/run")
    assert synthesis.status_code == 200
    body = synthesis.json()
    assert body["ready_for_review"] == 1
    assert body["rejected"] == 0
    assert body["future_run_id"] is not None

    candidates = client.get(
        f"/v1/users/{uid}/candidates",
        params={"status": "ready_for_review"},
    )
    assert candidates.status_code == 200
    assert len(candidates.json()) == 1
    candidate = candidates.json()[0]
    assert candidate["source_type"] == "hypothesis"
    assert candidate["decision_status"] == "candidate_for_reversible_pilot"
    assert candidate["surfaced_opportunity_id"] is not None

    opportunities = client.get(f"/v1/users/{uid}/opportunities")
    assert opportunities.status_code == 200
    surfaced = next(
        item for item in opportunities.json() if item["category"] == "synthesized"
    )
    assert surfaced["care_status"] == "approved"
    assert "not authorization" in surfaced["rationale"]

    all_notifications = notifications(uid)
    assert len(all_notifications) == 1
    assert all_notifications[0]["status"] == "suppressed"
    assert "confidence below proactive threshold" in all_notifications[0]["suppression_reason"]

    second = client.post(f"/v1/users/{uid}/synthesis/run")
    assert second.status_code == 200
    assert second.json()["generated"] == 0
    assert second.json()["evaluated"] == 0


def test_candidate_data_is_exported_and_deletable():
    uid = "synthesis-privacy-d"
    make_user(uid)

    signal = client.post(
        f"/v1/users/{uid}/signals",
        json={
            "source": "test",
            "type": "deadline",
            "payload": {
                "days_remaining": 3,
                "relevance": 0.8,
                "label": "export candidate",
            },
        },
    )
    assert signal.status_code == 200
    assert client.post(f"/v1/users/{uid}/engine/run").status_code == 200

    export = client.get(f"/v1/users/{uid}/export")
    assert export.status_code == 200
    assert export.json()["candidate_interventions"]
    assert export.json()["secrets_included"] is False

    deleted = client.delete(
        f"/v1/users/{uid}",
        params={"confirm": f"DELETE {uid}"},
    )
    assert deleted.status_code == 200
    assert client.get(f"/v1/users/{uid}/candidates").status_code == 404
