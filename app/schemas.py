from datetime import datetime

from pydantic import BaseModel, Field


class UserUpsert(BaseModel):
    external_id: str
    country: str = "FR"
    currency: str = "EUR"
    timezone: str = "Europe/Paris"
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


class MandateUpsert(BaseModel):
    mission: str = ""
    principles: list[str] = Field(default_factory=list)
    constraints: dict = Field(default_factory=dict)
    autonomy: dict = Field(default_factory=dict)
    notification_policy: dict = Field(default_factory=dict)


class MandateOut(MandateUpsert):
    version: int
    updated_at: datetime

    model_config = {"from_attributes": True}


class SignalCreate(BaseModel):
    source: str
    type: str
    payload: dict
    observed_at: datetime | None = None


class OutcomeCreate(BaseModel):
    useful: bool | None = None
    accepted: bool | None = None
    executed: bool | None = None
    realized_value: float | None = None
    feedback: str = ""
    metadata_json: dict = Field(default_factory=dict)


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


class NotificationOut(BaseModel):
    id: int
    opportunity_id: int
    channel: str
    title: str
    body: str
    status: str
    suppression_reason: str
    priority: float
    available_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


class ConnectorStatusOut(BaseModel):
    provider: str
    enabled: bool
    scopes: list[str]
    last_synced_at: datetime | None
    last_error: str

    model_config = {"from_attributes": True}
