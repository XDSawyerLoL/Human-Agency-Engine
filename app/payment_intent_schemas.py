from pydantic import BaseModel, Field


class PaymentIntentPreview(BaseModel):
    settlement_permit_id: str = Field(..., min_length=8, max_length=64)
    audience: str = Field(..., min_length=8, max_length=128)


class PaymentIntentIssue(PaymentIntentPreview):
    expires_in_seconds: int = Field(600, ge=60, le=1800)
    confirm: str


class PaymentIntentVerify(BaseModel):
    token: str = Field(..., min_length=32)
    audience: str = Field(..., min_length=8, max_length=128)


class PaymentIntentConsume(BaseModel):
    token: str = Field(..., min_length=32)
    audience: str = Field(..., min_length=8, max_length=128)
    request_id: str = Field(..., min_length=12, max_length=128)


class PaymentIntentRevoke(BaseModel):
    confirm: str
