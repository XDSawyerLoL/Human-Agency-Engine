from pydantic import BaseModel, Field


class SettlementPermitIssue(BaseModel):
    allocation_entry_id: str = Field(..., min_length=8, max_length=64)
    expires_in_seconds: int = Field(900, ge=60, le=1800)
    confirm: str


class SettlementPermitVerify(BaseModel):
    token: str = Field(..., min_length=32)
    audience: str = Field(..., min_length=8, max_length=96)


class SettlementPermitConsume(BaseModel):
    token: str = Field(..., min_length=32)
    audience: str = Field(..., min_length=8, max_length=96)
    request_id: str = Field(..., min_length=12, max_length=128)


class SettlementPermitRevoke(BaseModel):
    confirm: str
