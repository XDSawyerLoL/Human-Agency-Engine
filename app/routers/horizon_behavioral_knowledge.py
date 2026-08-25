from __future__ import annotations

from fastapi import APIRouter

from ..horizon_behavioral_knowledge_schemas import (
    BehavioralKnowledgePackRequest,
    BehavioralKnowledgeSearchRequest,
)
from ..services.horizon_behavioral_knowledge import BehavioralKnowledgeService


router = APIRouter(tags=["HORIZON Behavioral Knowledge"])


@router.get("/horizon/behavioral-knowledge/sources")
def behavioral_knowledge_sources():
    return BehavioralKnowledgeService().source_catalog()


@router.post("/horizon/behavioral-knowledge/search")
def behavioral_knowledge_search(payload: BehavioralKnowledgeSearchRequest):
    return BehavioralKnowledgeService().search(payload)


@router.post("/horizon/behavioral-knowledge/build-pack")
def behavioral_knowledge_build_pack(payload: BehavioralKnowledgePackRequest):
    return BehavioralKnowledgeService().build_pack(payload)
