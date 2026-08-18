from pydantic import BaseModel, Field


class VaultClaimWrite(BaseModel):
    value: str = Field(..., min_length=1, max_length=512)
    confirm: str


class VaultClaimDelete(BaseModel):
    confirm: str


class DisclosureGrantIssue(BaseModel):
    settlement_permit_id: str = Field(..., min_length=8, max_length=64)
    claim_types: list[str] = Field(..., min_length=1, max_length=8)
    expires_in_seconds: int = Field(600, ge=60, le=1800)
    confirm: str


class DisclosureGrantVerify(BaseModel):
    token: str = Field(..., min_length=32)
    audience: str = Field(..., min_length=8, max_length=96)


class DisclosureGrantConsume(BaseModel):
    token: str = Field(..., min_length=32)
    audience: str = Field(..., min_length=8, max_length=96)
    request_id: str = Field(..., min_length=12, max_length=128)


class DisclosureGrantRevoke(BaseModel):
    confirm: str
