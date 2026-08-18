from pydantic import BaseModel, Field


class ExecutionReadinessAssess(BaseModel):
    preflight_id: str = Field(..., min_length=8, max_length=64)
