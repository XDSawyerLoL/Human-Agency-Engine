from app.services.human_signal_engine import HumanSignalEngine


def test_human_signal_engine_keeps_novelty_and_solution_absence_unverified():
    briefing = {
        "engine": "test-briefing",
        "events": [
            {
                "kind": "confirmed_event",
                "id": 1,
                "event_type": "rail_transport_disruption",
                "title": "Repeated rail disruption",
                "domain": "transport_mobility",
                "domain_label": "Transport & mobility",
                "maturity": "live_multi_source",
                "fact_status": "confirmed_or_derived_event",
                "source": "sncf",
                "observed_at": "2026-08-20T08:00:00+00:00",
                "occurred_at": "2026-08-20T07:00:00+00:00",
            }
        ],
        "hypotheses": [
            {
                "kind": "emerging_hypothesis",
                "id": 2,
                "event_type": "rail_transport_disruption",
                "title": "Rail disruption emerging",
                "domain": "transport_mobility",
                "domain_label": "Transport & mobility",
                "maturity": "live_multi_source",
                "fact_status": "unconfirmed_emerging_event",
                "source_classes": ["world_events", "transport"],
                "corroboration_score": 0.72,
                "first_observed_at": "2026-08-20T09:00:00+00:00",
                "observed_at": "2026-08-24T09:00:00+00:00",
            }
        ],
    }

    result = HumanSignalEngine().analyze(briefing, limit=5)

    assert result["summary"]["opportunities_returned"] == 1
    opportunity = result["opportunities"][0]
    assert opportunity["problem_key"] == "transport_mobility:rail_transport_disruption"
    assert opportunity["signal_strength"]["diagnostic_score_is_probability"] is False
    assert opportunity["unresolvedness"]["solution_absence_verified"] is False
    assert opportunity["novelty"]["globally_unique_claim"] is False
    assert result["critical_semantics"]["human_validation_required_before_build"] is True


def test_human_signal_engine_ranks_stronger_convergent_signal_first():
    briefing = {
        "engine": "test-briefing",
        "events": [
            {
                "kind": "confirmed_event",
                "id": 1,
                "event_type": "power_grid_disruption",
                "title": "Grid disruption",
                "domain": "energy",
                "maturity": "historically_calibratable",
                "source": "rte",
                "observed_at": "2026-08-20T08:00:00+00:00",
                "occurred_at": "2026-08-20T07:00:00+00:00",
            },
            {
                "kind": "confirmed_event",
                "id": 2,
                "event_type": "power_grid_disruption",
                "title": "Grid disruption follow-up",
                "domain": "energy",
                "maturity": "historically_calibratable",
                "source": "independent_operator",
                "observed_at": "2026-08-24T08:00:00+00:00",
                "occurred_at": "2026-08-24T07:00:00+00:00",
            },
            {
                "kind": "confirmed_event",
                "id": 3,
                "event_type": "technology_service_outage",
                "title": "Single service outage",
                "domain": "cyber_technology",
                "maturity": "live_single_source",
                "source": "status_page",
                "observed_at": "2026-08-24T08:00:00+00:00",
                "occurred_at": "2026-08-24T08:00:00+00:00",
            },
        ],
        "hypotheses": [],
    }

    result = HumanSignalEngine().analyze(briefing, limit=5)

    assert result["opportunities"][0]["problem_key"] == "energy:power_grid_disruption"
    assert (
        result["opportunities"][0]["signal_strength"]["diagnostic_score"]
        > result["opportunities"][1]["signal_strength"]["diagnostic_score"]
    )
