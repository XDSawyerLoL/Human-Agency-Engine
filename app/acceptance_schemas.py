from pydantic import BaseModel, Field


class AllocationDecisionCreate(BaseModel):
    allocation_entry_id: str = Field(..., min_length=8, max_length=64)
    confirm: str


class AllocationAcceptanceRevoke(BaseModel):
    confirm: str
