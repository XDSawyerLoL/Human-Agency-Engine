from pydantic import BaseModel, Field


class InformationResolution(BaseModel):
    value: dict = Field(default_factory=dict)
    source: str
    provenance: dict = Field(default_factory=dict)
    confidence: float = Field(..., ge=0, le=1)


class InformationWaive(BaseModel):
    reason: str
