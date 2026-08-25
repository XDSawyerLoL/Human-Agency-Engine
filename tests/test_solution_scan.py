from app.services.solution_scan import SolutionScanService


def _source(source: str, items=None, status: str = "ok"):
    return {
        "source": source,
        "status": status,
        "items": items or [],
    }


def _item(ecosystem: str, title: str, summary: str = ""):
    return {
        "ecosystem": ecosystem,
        "title": title,
        "summary": summary,
        "url": f"https://example.test/{ecosystem}",
        "published_at": "2026-08-20",
        "metadata": {},
    }


def test_solution_scan_can_only_claim_candidate_gap_in_scanned_sources():
    result = SolutionScanService.assess(
        "rail transport disruption",
        [
            _source("github"),
            _source("openalex"),
            _source("hackernews"),
            _source("gdelt", status="error"),
        ],
    )

    assert result["successful_source_count"] == 3
    assert result["coverage_sufficient_for_gap_assessment"] is True
    assert result["relevant_match_count"] == 0
    assert result["gap_status"] == "candidate_gap_in_scanned_sources"
    assert result["global_novelty_verified"] is False
    assert result["existing_solution_effectiveness_verified"] is False


def test_solution_scan_refuses_gap_claim_when_source_coverage_is_too_low():
    result = SolutionScanService.assess(
        "rail transport disruption",
        [
            _source("github"),
            _source("openalex", status="error"),
            _source("hackernews", status="error"),
            _source("gdelt"),
        ],
    )

    assert result["successful_source_count"] == 2
    assert result["coverage_sufficient_for_gap_assessment"] is False
    assert result["gap_status"] == "insufficient_source_coverage"
    assert result["global_novelty_verified"] is False


def test_solution_scan_detects_related_work_without_calling_it_effective():
    result = SolutionScanService.assess(
        "rail transport disruption",
        [
            _source(
                "github",
                [_item("github", "Rail transport disruption monitoring toolkit")],
            ),
            _source(
                "openalex",
                [_item("openalex", "Rail transport disruption and passenger recovery")],
            ),
            _source("hackernews"),
        ],
    )

    assert result["gap_status"] == "related_work_found"
    assert result["relevant_match_count"] == 2
    assert result["existing_solution_effectiveness_verified"] is False
    assert all(
        match["relevance_score_is_probability"] is False
        for match in result["matches"]
    )


def test_solution_scan_marks_dense_multi_ecosystem_work_as_substantial():
    query = "power grid disruption"
    payloads = []
    for ecosystem in ("github", "openalex", "hackernews"):
        payloads.append(
            _source(
                ecosystem,
                [
                    _item(ecosystem, f"Power grid disruption response {index}")
                    for index in range(3)
                ],
            )
        )

    result = SolutionScanService.assess(query, payloads)

    assert result["relevant_match_count"] == 9
    assert len(result["ecosystems_with_relevant_matches"]) == 3
    assert result["gap_status"] == "substantial_existing_work_found"
    assert result["global_novelty_verified"] is False
