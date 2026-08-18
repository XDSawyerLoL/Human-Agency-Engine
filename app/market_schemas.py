from typing import Literal

from pydantic import BaseModel, Field


class PrivateIntentDisclosure(BaseModel):
    category: str = Field(..., min_length=2, max_length=96)
    budget_max: float = Field(..., gt=0, le=1000000)
    currency: str = Field(..., min_length=3, max_length=3)
    country: str = Field(..., min_length=2, max_length=2)
    quantity: int = Field(1, ge=1, le=1000)
    size: str | None = Field(default=None, max_length=64)
    required_features: list[str] = Field(default_factory=list, max_length=20)
    desired_within_days: int | None = Field(default=None, ge=0, le=365)
    condition: Literal["new", "used", "any"] = "any"


class FiduciaryRankingPolicy(BaseModel):
    price_weight: float = Field(0.5, ge=0, le=1)
    delivery_weight: float = Field(0.2, ge=0, le=1)
    reversibility_weight: float = Field(0.3, ge=0, le=1)


class PrivateIntentOpen(BaseModel):
    candidate_id: int
    request_type: Literal["product", "service"] = "product"
    disclosure: PrivateIntentDisclosure
    ranking_policy: FiduciaryRankingPolicy = Field(default_factory=FiduciaryRankingPolicy)
    expires_in_seconds: int = Field(86400, ge=300, le=604800)
    confirm: str


class PrivateIntentRevoke(BaseModel):
    confirm: str


class MarketOfferSubmit(BaseModel):
    offer_id: str = Field(..., min_length=4, max_length=96)
    responder_label: str = Field("", max_length=255)
    public_key_b64: str = Field(..., min_length=40, max_length=128)
    price_total: float = Field(..., ge=0, le=1000000)
    currency: str = Field(..., min_length=3, max_length=3)
    delivery_days: int = Field(..., ge=0, le=365)
    return_window_days: int = Field(0, ge=0, le=365)
    cancellation_allowed: bool = False
    available: bool = True
    quantity_available: int = Field(1, ge=0, le=1000000)
    features: list[str] = Field(default_factory=list, max_length=50)
    condition: Literal["new", "used", "not_applicable"] = "new"
    commission_amount: float = Field(0, ge=0, le=1000000)
    commission_currency: str | None = Field(default=None, min_length=3, max_length=3)
    signature_b64: str = Field(..., min_length=40, max_length=256)
