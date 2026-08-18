from pydantic import BaseModel, Field


class CollectiveSettlementAssess(BaseModel):
    offer_id: str = Field(..., min_length=4, max_length=96)
