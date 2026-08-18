from pydantic import BaseModel, Field


class CollectiveConditionalCommit(BaseModel):
    membership_id: str = Field(..., min_length=8, max_length=64)
    offer_id: str = Field(..., min_length=4, max_length=96)
    confirm: str


class CollectiveConditionalRevoke(BaseModel):
    confirm: str
