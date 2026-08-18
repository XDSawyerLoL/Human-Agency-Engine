from pydantic import BaseModel, Field


class CollectiveAllocationCreate(BaseModel):
    offer_id: str = Field(..., min_length=4, max_length=96)
    confirm: str
