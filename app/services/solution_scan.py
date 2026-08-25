from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import re
from typing import Any, Callable

import httpx


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_GENERIC_TOKENS = {
    "event", "events", "issue", "issues", "problem", "problems", "human", "signal", "signals",
    "change", "changes", "system", "systems", "service", "services",
}

_SOURCE_LABELS = {
    "github": "Open-source / developer projects",
    "openalex": "Academic research",
    "hackernews": "Startup / technology community",
    "gdelt": "Public web & media coverage",
}


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in _TOKEN_RE.findall((value or "").lower())
        if len(token) >= 3 and token not in _GENERIC_TOKENS
    }


def _query_for(opportunity: dict[str, Any]) -> str:
    event_type = str(opportunity.get("event_type") or "").replace("_", " ").strip()
    if event_type:
        return event_type
    statement = str(opportunity.get("problem_statement") or "").strip()
    return " ".join(sorted(_tokens(statement))[:6]) or "unresolved problem"


def _relevance(query: str, title: str, summary: str = "") -> tuple[int, list[str]]:
    query_tokens = _tokens(query)
    if not query_tokens:
        return 0, []
    haystack = f"{title} {summary}".lower()
    hay_tokens = _tokens(haystack)
    matched = sorted(query_tokens & hay_tokens)
    overlap = len(matched) / max(1, len(query_tokens))
    phrase_bonus = 0.18 if query.lower() in haystack else 0.0
    title_tokens = _tokens(title)
    title_overlap = len(query_tokens & title_tokens) / max(1, len(query_tokens))
    score = min(100, round((overlap * 0.67 + title_overlap * 0.15 + phrase_bonus) * 100))
    return score, matched


def _truncate(value: Any, limit: int = 500) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


class SolutionScanService:
    """Free, multi-ecosystem scan for existing work related to an Évidence problem signal.

    This service is an evidence-gathering layer, not a global novelty oracle.
    Search absence is explicitly scoped to the sources that successfully responded.
    """

    ENGINE_VERSION = "evidence-solution-scan-v0.1"

    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        client_factory: Callable[..., httpx.Client] = httpx.Client,
    ):
        self.timeout_seconds = timeout_seconds
        self.client_factory = client_factory

    def _github(self, client: httpx.Client, query: str, limit: int) -> list[dict[str, Any]]:
        response = client.get(
            "https://api.github.com/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc", "per_page": limit},
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "Evidence-Human-Signal-Engine",
            },
        )
        response.raise_for_status()
        rows = []
        for item in (response.json().get("items") or [])[:limit]:
            rows.append({
                "ecosystem": "github",
                "title": item.get("full_name") or item.get("name"),
                "summary": _truncate(item.get("description")),
                "url": item.get("html_url"),
                "published_at": item.get("created_at"),
                "updated_at": item.get("updated_at"),
                "metadata": {
                    "stars": item.get("stargazers_count"),
                    "language": item.get("language"),
                },
            })
        return rows

    def _openalex(self, client: httpx.Client, query: str, limit: int) -> list[dict[str, Any]]:
        response = client.get(
            "https://api.openalex.org/works",
            params={"search": query, "per-page": limit},
            headers={"User-Agent": "Evidence-Human-Signal-Engine"},
        )
        response.raise_for_status()
        rows = []
        for item in (response.json().get("results") or [])[:limit]:
            primary_location = item.get("primary_location") or {}
            source = primary_location.get("source") or {}
            url = item.get("doi") or primary_location.get("landing_page_url") or item.get("id")
            rows.append({
                "ecosystem": "openalex",
                "title": item.get("display_name"),
                "summary": _truncate(
                    " ".join(
                        str(concept.get("display_name") or "")
                        for concept in (item.get("concepts") or [])[:8]
                    )
                ),
                "url": url,
                "published_at": item.get("publication_date") or item.get("publication_year"),
                "metadata": {
                    "cited_by_count": item.get("cited_by_count"),
                    "source": source.get("display_name"),
                    "type": item.get("type"),
                },
            })
        return rows

    def _hackernews(self, client: httpx.Client, query: str, limit: int) -> list[dict[str, Any]]:
        response = client.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": query, "tags": "story", "hitsPerPage": limit},
            headers={"User-Agent": "Evidence-Human-Signal-Engine"},
        )
        response.raise_for_status()
        rows = []
        for item in (response.json().get("hits") or [])[:limit]:
            object_id = item.get("objectID")
            url = item.get("url") or (
                f"https://news.ycombinator.com/item?id={object_id}" if object_id else None
            )
            rows.append({
                "ecosystem": "hackernews",
                "title": item.get("title") or item.get("story_title"),
                "summary": "",
                "url": url,
                "published_at": item.get("created_at"),
                "metadata": {
                    "points": item.get("points"),
                    "comments": item.get("num_comments"),
                    "author": item.get("author"),
                },
            })
        return rows

    def _gdelt(self, client: httpx.Client, query: str, limit: int) -> list[dict[str, Any]]:
        response = client.get(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": query,
                "mode": "artlist",
                "maxrecords": min(limit, 50),
                "format": "json",
                "timespan": "1y",
            },
            headers={"User-Agent": "Evidence-Human-Signal-Engine"},
        )
        response.raise_for_status()
        payload = response.json()
        rows = []
        for item in (payload.get("articles") or [])[:limit]:
            rows.append({
                "ecosystem": "gdelt",
                "title": item.get("title"),
                "summary": _truncate(
                    " ".join(
                        filter(
                            None,
                            [
                                item.get("domain"),
                                item.get("sourcecountry"),
                                item.get("language"),
                            ],
                        )
                    )
                ),
                "url": item.get("url"),
                "published_at": item.get("seendate"),
                "metadata": {
                    "domain": item.get("domain"),
                    "source_country": item.get("sourcecountry"),
                    "language": item.get("language"),
                },
            })
        return rows

    @staticmethod
    def assess(
        query: str,
        source_payloads: list[dict[str, Any]],
    ) -> dict[str, Any]:
        matches: list[dict[str, Any]] = []
        successful_sources = 0

        for source in source_payloads:
            if source.get("status") == "ok":
                successful_sources += 1
            for item in source.get("items") or []:
                score, matched_terms = _relevance(
                    query,
                    str(item.get("title") or ""),
                    str(item.get("summary") or ""),
                )
                matches.append({
                    **item,
                    "relevance_score": score,
                    "relevance_score_is_probability": False,
                    "matched_terms": matched_terms,
                    "is_relevant": score >= 45,
                })

        matches.sort(
            key=lambda item: (
                item["is_relevant"],
                item["relevance_score"],
                item.get("published_at") or "",
            ),
            reverse=True,
        )
        relevant = [item for item in matches if item["is_relevant"]]
        ecosystems = sorted({item["ecosystem"] for item in relevant})

        if successful_sources >= 3 and not relevant:
            gap_status = "candidate_gap_in_scanned_sources"
            explanation = (
                "No sufficiently relevant existing work was found across at least three scanned ecosystems. "
                "This is a candidate gap only within the scanned sources, not proof of global novelty."
            )
        elif len(relevant) >= 8 and len(ecosystems) >= 3:
            gap_status = "substantial_existing_work_found"
            explanation = (
                "Related work appears across several independent ecosystems. The useful opportunity, if any, "
                "is more likely to be a missing integration, workflow or underserved user segment than a blank space."
            )
        elif len(relevant) >= 2:
            gap_status = "related_work_found"
            explanation = (
                "Existing work is visible, but this scan does not establish whether it solves the observed human "
                "friction end-to-end. Compare mechanisms and user outcomes before rejecting the opportunity."
            )
        else:
            gap_status = "underexplored_in_scanned_sources"
            explanation = (
                "Only sparse related work was found. The area is underexplored in the scanned sources, "
                "but broader product, public-service and patent checks are still required."
            )

        return {
            "successful_source_count": successful_sources,
            "relevant_match_count": len(relevant),
            "ecosystems_with_relevant_matches": ecosystems,
            "gap_status": gap_status,
            "explanation": explanation,
            "global_novelty_verified": False,
            "existing_solution_effectiveness_verified": False,
            "matches": matches[:32],
        }

    def _scan_one(
        self,
        source_key: str,
        scanner: Callable[[httpx.Client, str, int], list[dict[str, Any]]],
        query: str,
        limit: int,
    ) -> dict[str, Any]:
        try:
            with self.client_factory(
                timeout=httpx.Timeout(self.timeout_seconds),
                follow_redirects=True,
            ) as client:
                items = scanner(client, query, limit)
            return {
                "source": source_key,
                "label": _SOURCE_LABELS[source_key],
                "status": "ok",
                "result_count": len(items),
                "items": items,
            }
        except Exception as exc:
            return {
                "source": source_key,
                "label": _SOURCE_LABELS[source_key],
                "status": "error",
                "result_count": 0,
                "items": [],
                "error": _truncate(exc, 180),
            }

    def scan(
        self,
        opportunity: dict[str, Any],
        *,
        max_results_per_source: int = 10,
    ) -> dict[str, Any]:
        query = _query_for(opportunity)
        limit = max(3, min(max_results_per_source, 20))
        scanners = (
            ("github", self._github),
            ("openalex", self._openalex),
            ("hackernews", self._hackernews),
            ("gdelt", self._gdelt),
        )
        ordered_payloads: list[dict[str, Any] | None] = [None] * len(scanners)

        with ThreadPoolExecutor(max_workers=len(scanners), thread_name_prefix="evidence-scan") as pool:
            futures = {
                pool.submit(self._scan_one, source_key, scanner, query, limit): index
                for index, (source_key, scanner) in enumerate(scanners)
            }
            for future in as_completed(futures):
                ordered_payloads[futures[future]] = future.result()

        source_payloads = [
            payload
            for payload in ordered_payloads
            if payload is not None
        ]
        assessment = self.assess(query, source_payloads)
        return {
            "engine": self.ENGINE_VERSION,
            "problem_key": opportunity.get("problem_key"),
            "query": query,
            "assessment": {
                key: value
                for key, value in assessment.items()
                if key != "matches"
            },
            "sources": [
                {
                    key: value
                    for key, value in source.items()
                    if key != "items"
                }
                for source in source_payloads
            ],
            "matches": assessment["matches"],
            "critical_semantics": {
                "no_match_means_no_solution_exists": False,
                "search_result_means_solution_is_effective": False,
                "global_novelty_verified": False,
                "relevance_score_is_probability": False,
                "scope_is_limited_to_successfully_scanned_sources": True,
            },
        }
