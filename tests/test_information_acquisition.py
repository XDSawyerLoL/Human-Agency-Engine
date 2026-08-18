from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def make_user(uid: str, complete: bool = True):
    payload = {
        "external_id": uid,
        "timezone": "Europe/Paris",
        "minimum_cash_buffer": 150,
    }
    if complete:
        payload.update(
            {
                "monthly_income": 2200,
                "monthly_fixed_costs": 1400,
                "liquid_cash": 900,
            }
        )
    response = client.put(f"/v1/users/{uid}", json=payload)
    assert response.status_code == 200


def add_temporal_fact(uid: str):
    response = client.post(
        f"/v1/users/{uid}/state/facts",
        json={
            "domain": "metric",
            "key": "baseline_capacity",
            "value": {
                "amount": 1,
                "unit": "unit",
                "direction": "higher_is_better",
            },
            "source": "test",
            "confidence": 0.9,
            "sensitivity": "standard",
        },
    )
    assert response.status_code == 200


def create_under_modeled_candidate(uid: str):
    signal = client.post(
        f"/v1/users/{uid}/signals",
        json={
            "source": "test",
            "type": "deadline",
            "payload": {
                "days_remaining": 5,
                "relevance": 0.9,
                "label": "synthetic decision window",
                "reason": "synthetic time-sensitive option",
            },
        },
    )
    assert signal.status_code == 200
    engine = client.post(f"/v1/users/{uid}/engine/run")
    assert engine.status_code == 200
    candidates = client.get(f"/v1/users/{uid}/candidates")
    assert candidates.status_code == 200
    candidate = candidates.json()[0]
    assert candidate["status"] == "needs_information"
    return candidate


def open_needs(uid: str):
    response = client.get(
        f"/v1/users/{uid}/information/needs",
        params={"status": "open"},
    )
    assert response.status_code == 200
    return response.json()


def resolve_need(uid: str, need: dict, value: dict, confidence: float = 0.9):
    response = client.put(
        f"/v1/users/{uid}/information/needs/{need['id']}/resolve",
        json={
            "value": value,
            "source": "user",
            "provenance": {"test": True},
            "confidence": confidence,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_epistemic_loop_can_gather_then_re_simulate_before_review():
    uid = "information-loop-a"
    make_user(uid, complete=True)
    add_temporal_fact(uid)

    mandate = client.put(
        f"/v1/users/{uid}/mandate",
        json={
            "mission": "Increase options without unnecessary interruptions.",
            "principles": ["user control"],
            "constraints": {},
            "autonomy": {"default": "suggest"},
            "notification_policy": {
                "max_questions_per_day": 1,
                "min_confidence": 0.72,
            },
        },
    )
    assert mandate.status_code == 200

    candidate = create_under_modeled_candidate(uid)

    materialized = client.post(f"/v1/users/{uid}/information/materialize")
    assert materialized.status_code == 200
    assert materialized.json()["needs_created"] >= 2

    first_needs = open_needs(uid)
    first_types = {item["need_type"] for item in first_needs}
    assert "verify_assumption" in first_types
    assert "check_reversibility" in first_types

    questions = client.post(
        f"/v1/users/{uid}/information/next-questions",
        params={"requested": 5},
    )
    assert questions.status_code == 200
    assert len(questions.json()) == 1
    no_more_questions = client.post(
        f"/v1/users/{uid}/information/next-questions",
        params={"requested": 5},
    )
    assert no_more_questions.status_code == 200
    assert no_more_questions.json() == []

    for need in first_needs:
        if need["need_type"] == "check_reversibility":
            resolve_need(
                uid,
                need,
                {
                    "reversible": True,
                    "lock_in_days": 0,
                    "reversal_cost": 0,
                },
            )
        else:
            resolve_need(uid, need, {"verified": True})

    requeued = client.get(f"/v1/users/{uid}/candidates")
    candidate_after_first_resolution = next(
        item for item in requeued.json() if item["id"] == candidate["id"]
    )
    assert candidate_after_first_resolution["status"] == "generated"

    second_pass = client.post(f"/v1/users/{uid}/synthesis/run")
    assert second_pass.status_code == 200
    assert second_pass.json()["needs_information"] == 1

    second_needs = open_needs(uid)
    current_candidate_needs = [
        item for item in second_needs if item["candidate_id"] == candidate["id"]
    ]
    assert len(current_candidate_needs) == 1
    assert current_candidate_needs[0]["need_type"] == "model_effects"

    resolve_need(
        uid,
        current_candidate_needs[0],
        {
            "effects": {
                "option_value": {
                    "low": 0,
                    "central": 1,
                    "high": 1,
                    "unit": "option",
                    "direction": "higher_is_better",
                    "rationale": "bounded synthetic effect after explicit verification",
                }
            }
        },
    )

    third_pass = client.post(f"/v1/users/{uid}/synthesis/run")
    assert third_pass.status_code == 200
    assert third_pass.json()["ready_for_review"] == 1

    final_candidates = client.get(f"/v1/users/{uid}/candidates")
    final_candidate = next(
        item for item in final_candidates.json() if item["id"] == candidate["id"]
    )
    assert final_candidate["status"] == "ready_for_review"
    assert final_candidate["decision_status"] == "candidate_for_reversible_pilot"
    assert final_candidate["surfaced_opportunity_id"] is not None


def test_known_state_is_auto_resolved_before_bothering_user():
    uid = "information-auto-state-b"
    make_user(uid, complete=False)
    add_temporal_fact(uid)
    create_under_modeled_candidate(uid)

    materialized = client.post(f"/v1/users/{uid}/information/materialize")
    assert materialized.status_code == 200
    financial = [
        item
        for item in open_needs(uid)
        if item["need_type"] == "resolve_missing_state"
        and any(field in item["question"] for field in ("monthly_income", "monthly_fixed_costs", "liquid_cash"))
    ]
    assert len(financial) == 3

    updated = client.put(
        f"/v1/users/{uid}",
        json={
            "external_id": uid,
            "timezone": "Europe/Paris",
            "monthly_income": 2100,
            "monthly_fixed_costs": 1300,
            "liquid_cash": 700,
            "minimum_cash_buffer": 150,
        },
    )
    assert updated.status_code == 200

    rematerialized = client.post(f"/v1/users/{uid}/information/materialize")
    assert rematerialized.status_code == 200
    assert rematerialized.json()["auto_resolved"] >= 3

    all_needs = client.get(f"/v1/users/{uid}/information/needs")
    assert all_needs.status_code == 200
    resolved_financial = [
        item
        for item in all_needs.json()
        if item["need_type"] == "resolve_missing_state"
        and any(field in item["question"] for field in ("monthly_income", "monthly_fixed_costs", "liquid_cash"))
    ]
    assert all(item["status"] == "resolved" for item in resolved_financial)
    assert all(item["resolution_source"] == "self_graph" for item in resolved_financial)
    assert all(item["ask_count"] == 0 for item in resolved_financial)


def test_sensitive_missing_state_rejects_unverified_inference():
    uid = "information-sensitive-c"
    make_user(uid, complete=False)
    add_temporal_fact(uid)
    create_under_modeled_candidate(uid)
    assert client.post(f"/v1/users/{uid}/information/materialize").status_code == 200

    financial_need = next(
        item
        for item in open_needs(uid)
        if item["need_type"] == "resolve_missing_state" and "monthly_income" in item["question"]
    )
    assert financial_need["sensitivity"] == "sensitive"

    rejected = client.put(
        f"/v1/users/{uid}/information/needs/{financial_need['id']}/resolve",
        json={
            "value": {"field": "monthly_income", "value": 9999},
            "source": "inference",
            "provenance": {"model": "synthetic"},
            "confidence": 0.99,
        },
    )
    assert rejected.status_code == 400

    still_open = client.get(
        f"/v1/users/{uid}/information/needs",
        params={"status": "open"},
    )
    assert still_open.status_code == 200
    assert any(item["id"] == financial_need["id"] for item in still_open.json())
