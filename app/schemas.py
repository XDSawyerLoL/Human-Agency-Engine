from datetime import datetime

from pydantic import BaseModel, Field


class UserUpsert(BaseModel):
    external_id: str
    country: str = "FR"
    currency: str = "EUR"
    monthly_income: float | None = None
    monthly_fixed_costs: float | None = None
    liquid_cash: float | None = None
    minimum_cash_buffer: float = 150.0
    preferences: dict = Field(default_factory=dict)


class IntentCreate(BaseModel):
    kind: str
    statement: str
    target: dict = Field(default_factory=dict)
    priority: float = Field(0.5, ge=0, le=1)


class SignalCreate(BaseModel):
    source: str
    type: str
    payload: dict
    observed_at: datetime | None = None


class OpportunityOut(BaseModel):
    id: int
    category: str
    title: str
    rationale: str
    proposed_action: dict
    baseline: dict
    counterfactual: dict
    expected_value: float
    confidence: float
    care_status: str
    care_reason: str
    status: str

    model_config = {"from_attributes": True}
