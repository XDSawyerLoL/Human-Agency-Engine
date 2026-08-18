from typing import Literal

from pydantic import BaseModel, Field


class CollectiveMarketOpen(BaseModel):
    cohort_key: str = Field(..., min_length=16, max_length=80)
    expires_in_seconds: int = Field(86400, ge=300, le=604800)
    confirm: str


class CollectiveOfferSubmit(BaseModel):
    offer_id: str = Field(..., min_length=4, max_length=96)
    responder_label: str = Field("", max_length=255)
    public_key_b64: str = Field(..., min_length=40, max_length=128)
    unit_price: float = Field(..., ge=0, le=1000000)
    currency: str = Field(..., min_length=3, max_length=3)
    minimum_collective_quantity: int = Field(1, ge=1, le=1000000)
    maximum_collective_quantity: int = Field(..., ge=1, le=1000000)
    delivery_days: int = Field(..., ge=0, le=365)
    return_window_days: int = Field(0, ge=0, le=365)
    cancellation_allowed: bool = False
    available: bool = True
    features: list[str] = Field(default_factory=list, max_length=50)
    condition: Literal["new", "used", "not_applicable"] = "new"
    commission_per_unit: float = Field(0, ge=0, le=1000000)
    commission_currency: str | None = Field(default=None, min_length=3, max_length=3)
    valid_until_epoch: int = Field(..., ge=1)
    signature_b64: str = Field(..., min_length=40, max_length=256)


class CollectiveOfferEvaluate(BaseModel):
    membership_id: str = Field(..., min_length=8, max_length=64)
    offer_id: str = Field(..., min_length=4, max_length=96)
