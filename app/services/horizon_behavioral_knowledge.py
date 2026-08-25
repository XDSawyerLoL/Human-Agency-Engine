from __future__ import annotations

from datetime import datetime, timezone
from html import unescape
import math
import os
import re
from typing import Any
from urllib.parse import quote_plus
from xml.etree import ElementTree

import httpx

from ..horizon_behavioral_knowledge_schemas import (
    BehavioralKnowledgePackRequest,
    BehavioralKnowledgeSearchRequest,
)


SOURCE_CATALOG = [
    {
        "key": "openalex",
        "name": "OpenAlex",
        "kind": "scholarly_graph",
        "coverage": "Hundreds of millions of scholarly works, datasets, theses, books and citation links.",
        "runtime_adapter": True,
        "automated_fulltext_ingestion": False,
        "notes": "Search metadata and abstracts first; ingest full text only when licence and access permit it.",
    },
    {
        "key": "pubmed",
        "name": "PubMed / NCBI Entrez",
        "kind": "biomedical_behavioral_literature",
        "coverage": "Biomedical, health, neuroscience and behavioral research indexed by NCBI.",
        "runtime_adapter": True,
        "automated_fulltext_ingestion": False,
        "notes": "PubMed metadata/abstract adapter; PMC full text should be handled separately by licence.",
    },
    {
        "key": "osf",
        "name": "Open Science Framework",
        "kind": "open_science_repository",
        "coverage": "Projects, registrations, preprints, study materials and public research files.",
        "runtime_adapter": False,
        "automated_fulltext_ingestion": False,
        "notes": "Catalogued for the next ingestion adapter. Public project files require per-resource licence checks.",
    },
    {
        "key": "wvs",
        "name": "World Values Survey",
        "kind": "cross_national_survey_archive",
        "coverage": "Cross-national values and attitudes, including longitudinal material spanning 1981-2022.",
        "runtime_adapter": False,
        "automated_fulltext_ingestion": False,
        "notes": "Use official downloads under WVS terms; do not silently redistribute licensed raw datasets.",
    },
    {
        "key": "ess",
        "name": "European Social Survey",
        "kind": "cross_national_survey_archive",
        "coverage": "Repeated European survey data on attitudes, beliefs, behavior and social context since 2002.",
        "runtime_adapter": False,
        "automated_fulltext_ingestion": False,
        "notes": "Use official portal and preserve ESS licensing/version/citation requirements.",
    },
]


MECHANISM_QUERIES = {
    "incentive": [
        "behavioral economics incentives decision making loss aversion prospect theory",
        "cost benefit friction choice architecture human behavior",
    ],
    "habit": [
        "habit formation behavioral automaticity inertia repeated behavior",
        "status quo bias default effect behavioral persistence",
    ],
    "social": [
        "social norms conformity peer influence collective behavior",
        "social contagion diffusion network behavior adoption",
    ],
    "stress": [
        "stress threat risk perception protective behavior coping",
        "scarcity urgency decision making behavior uncertainty",
    ],
    "intention_action": [
        "theory planned behavior intention action gap perceived behavioral control",
        "COM-B capability opportunity motivation behavior intervention",
    ],
    "collective_dynamics": [
        "crowd behavior pedestrian dynamics collective motion social influence",
        "queue behavior crowd density pedestrian flow public space",
    ],
}


def _clean_text(value: str | None) -> str | None:
    if not value:
        return None
    text = unescape(re.sub(r"\s+", " ", value)).strip()
    return text or None


def _openalex_abstract(inverted_index: dict[str, list[int]] | None) -> str | None:
    if not inverted_index:
        return None
    positioned: list[tuple[int, str]] = []
    for token, positions in inverted_index.items():
        for position in positions:
            positioned.append((position, token))
    positioned.sort(key=lambda item: item[0])
    return _clean_text(" ".join(token for _, token in positioned))


def _citation_signal(cited_by_count: int | None) -> float:
    if not cited_by_count or cited_by_count <= 0:
        return 0.0
    return min(1.0, math.log10(cited_by_count + 1) / 4.0)


class BehavioralKnowledgeService:
    ENGINE_VERSION = "horizon-behavioral-knowledge-v0.1"

    def __init__(self, *, timeout_seconds: float = 15.0):
        self.timeout_seconds = timeout_seconds

    def source_catalog(self) -> dict[str, Any]:
        return {
            "engine": self.ENGINE_VERSION,
            "sources": SOURCE_CATALOG,
            "principles": {
                "metadata_is_not_behavioral_truth": True,
                "citation_count_is_not_replication_quality": True,
                "fulltext_requires_licence_check": True,
                "survey_microdata_requires_source_terms": True,
                "hindsight_leakage_must_be_blocked_for_backtests": True,
            },
        }

    def search(self, request: BehavioralKnowledgeSearchRequest) -> dict[str, Any]:
        results: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []
        for source in request.sources:
            try:
                if source == "openalex":
                    results.extend(self._search_openalex(request))
                elif source == "pubmed":
                    results.extend(self._search_pubmed(request))
            except Exception as exc:  # external sources must not take HORIZON down
                errors.append({"source": source, "error": str(exc)[:300]})

        results.sort(
            key=lambda row: (
                row.get("evidence_signal", 0.0),
                row.get("publication_year") or 0,
            ),
            reverse=True,
        )
        return {
            "engine": self.ENGINE_VERSION,
            "query": request.query,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "results": results,
            "errors": errors,
            "semantics": {
                "evidence_signal_is_scientific_validity_probability": False,
                "search_result_is_supported_behavioral_rule": False,
                "human_review_or_empirical_extraction_required": True,
            },
        }

    def build_pack(self, request: BehavioralKnowledgePackRequest) -> dict[str, Any]:
        query_plan: list[dict[str, str]] = []
        for mechanism, queries in MECHANISM_QUERIES.items():
            for query in queries:
                query_plan.append(
                    {
                        "mechanism": mechanism,
                        "query": f"{request.scenario} {request.population} {query}",
                    }
                )

        packs = []
        for item in query_plan:
            search_request = BehavioralKnowledgeSearchRequest(
                query=item["query"],
                sources=["openalex", "pubmed"],
                limit_per_source=request.limit_per_query,
                publication_year_from=request.publication_year_from,
            )
            result = self.search(search_request)
            packs.append(
                {
                    "mechanism": item["mechanism"],
                    "query": item["query"],
                    "results": result["results"],
                    "errors": result["errors"],
                }
            )

        return {
            "engine": self.ENGINE_VERSION,
            "scenario": request.scenario,
            "population": request.population,
            "query_plan": query_plan,
            "mechanism_packs": packs,
            "next_step": (
                "Extract effect directions, populations, contexts, outcomes and uncertainty into a versioned "
                "behavioral evidence corpus before changing Human Dynamics coefficients."
            ),
            "semantics": {
                "automatically_changes_prediction_weights": False,
                "retrieval_is_training": False,
                "retrieval_is_calibration": False,
            },
        }

    def _search_openalex(self, request: BehavioralKnowledgeSearchRequest) -> list[dict[str, Any]]:
        params: dict[str, str | int] = {
            "search": request.query,
            "per_page": request.limit_per_source,
            "sort": "cited_by_count:desc",
            "select": (
                "id,doi,display_name,publication_year,publication_date,type,cited_by_count,"
                "open_access,abstract_inverted_index,primary_location,topics,is_retracted"
            ),
        }
        filters = []
        if request.publication_year_from:
            filters.append(f"from_publication_date:{request.publication_year_from}-01-01")
        if request.publication_year_to:
            filters.append(f"to_publication_date:{request.publication_year_to}-12-31")
        if request.open_access_only:
            filters.append("open_access.is_oa:true")
        if filters:
            params["filter"] = ",".join(filters)
        api_key = os.getenv("OPENALEX_API_KEY", "").strip()
        if api_key:
            params["api_key"] = api_key

        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = client.get("https://api.openalex.org/works", params=params)
            response.raise_for_status()
            payload = response.json()

        rows = []
        for item in payload.get("results") or []:
            if item.get("is_retracted"):
                continue
            location = item.get("primary_location") or {}
            source = location.get("source") or {}
            open_access = item.get("open_access") or {}
            topics = [
                topic.get("display_name")
                for topic in (item.get("topics") or [])[:8]
                if topic.get("display_name")
            ]
            cited_by_count = int(item.get("cited_by_count") or 0)
            rows.append(
                {
                    "source": "openalex",
                    "record_id": item.get("id"),
                    "title": item.get("display_name"),
                    "publication_year": item.get("publication_year"),
                    "publication_date": item.get("publication_date"),
                    "work_type": item.get("type"),
                    "doi": item.get("doi"),
                    "venue": source.get("display_name"),
                    "cited_by_count": cited_by_count,
                    "open_access": bool(open_access.get("is_oa")),
                    "open_access_url": open_access.get("oa_url"),
                    "abstract": _openalex_abstract(item.get("abstract_inverted_index")),
                    "topics": topics,
                    "evidence_signal": round(
                        0.55 * _citation_signal(cited_by_count)
                        + 0.25 * (1.0 if open_access.get("is_oa") else 0.0)
                        + 0.20 * (1.0 if item.get("abstract_inverted_index") else 0.0),
                        4,
                    ),
                    "evidence_signal_is_quality_probability": False,
                }
            )
        return rows

    def _search_pubmed(self, request: BehavioralKnowledgeSearchRequest) -> list[dict[str, Any]]:
        query = request.query
        if request.publication_year_from or request.publication_year_to:
            start = request.publication_year_from or 1800
            end = request.publication_year_to or datetime.now(timezone.utc).year
            query = f"({query}) AND ({start}:{end}[pdat])"

        base = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
        common = {
            "db": "pubmed",
            "retmode": "json",
            "tool": "horizon-human-dynamics",
        }
        email = os.getenv("NCBI_EMAIL", "").strip()
        api_key = os.getenv("NCBI_API_KEY", "").strip()
        if email:
            common["email"] = email
        if api_key:
            common["api_key"] = api_key

        with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
            search_response = client.get(
                f"{base}/esearch.fcgi",
                params={
                    **common,
                    "term": query,
                    "retmax": request.limit_per_source,
                    "sort": "relevance",
                },
            )
            search_response.raise_for_status()
            ids = search_response.json().get("esearchresult", {}).get("idlist", [])
            if not ids:
                return []
            fetch_params = {
                "db": "pubmed",
                "id": ",".join(ids),
                "retmode": "xml",
                "tool": "horizon-human-dynamics",
            }
            if email:
                fetch_params["email"] = email
            if api_key:
                fetch_params["api_key"] = api_key
            fetch_response = client.get(f"{base}/efetch.fcgi", params=fetch_params)
            fetch_response.raise_for_status()

        root = ElementTree.fromstring(fetch_response.text)
        rows = []
        for article in root.findall(".//PubmedArticle"):
            citation = article.find("MedlineCitation")
            if citation is None:
                continue
            pmid = citation.findtext("PMID")
            article_node = citation.find("Article")
            if article_node is None:
                continue
            title_node = article_node.find("ArticleTitle")
            title = _clean_text("".join(title_node.itertext())) if title_node is not None else None
            abstract_parts = []
            for node in article_node.findall("Abstract/AbstractText"):
                label = node.attrib.get("Label")
                body = _clean_text("".join(node.itertext()))
                if body:
                    abstract_parts.append(f"{label}: {body}" if label else body)
            journal_title = article_node.findtext("Journal/Title")
            year_text = (
                article_node.findtext("Journal/JournalIssue/PubDate/Year")
                or article_node.findtext("Journal/JournalIssue/PubDate/MedlineDate")
                or ""
            )
            year_match = re.search(r"(18|19|20|21)\d{2}", year_text)
            year = int(year_match.group(0)) if year_match else None
            publication_types = [
                _clean_text(node.text)
                for node in article_node.findall("PublicationTypeList/PublicationType")
                if _clean_text(node.text)
            ]
            rows.append(
                {
                    "source": "pubmed",
                    "record_id": f"pmid:{pmid}" if pmid else None,
                    "title": title,
                    "publication_year": year,
                    "publication_date": None,
                    "work_type": ", ".join(publication_types[:4]) or "article",
                    "doi": None,
                    "venue": journal_title,
                    "cited_by_count": None,
                    "open_access": None,
                    "open_access_url": None,
                    "abstract": _clean_text(" ".join(abstract_parts)),
                    "topics": [],
                    "evidence_signal": round(0.4 + (0.2 if abstract_parts else 0.0), 4),
                    "evidence_signal_is_quality_probability": False,
                }
            )
        return rows
