from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


KnowledgeSourceName = Literal[
    "openalex",
    "pubmed",
]


class BehavioralKnowledgeSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=3, max_length=500)
    sources: list[KnowledgeSourceName] = Field(
        default_factory=lambda: ["openalex", "pubmed"],
        min_length=1,
        max_length=2,
    )
    limit_per_source: int = Field(default=12, ge=1, le=50)
    publication_year_from: int | None = Field(default=None, ge=1800, le=2100)
    publication_year_to: int | None = Field(default=None, ge=1800, le=2100)
    open_access_only: bool = False


class BehavioralKnowledgePackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario: str = Field(..., min_length=3, max_length=1200)
    population: str = Field(default="general_population", min_length=1, max_length=240)
    limit_per_query: int = Field(default=8, ge=2, le=25)
    publication_year_from: int | None = Field(default=None, ge=1800, le=2100)
