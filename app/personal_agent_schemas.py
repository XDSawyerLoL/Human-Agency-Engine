from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class PersonalAgentMissionCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=255)
    goal: str = Field(..., min_length=10, max_length=8000)
    task_type: str = Field(..., pattern="^(agency_cycle|connector_sync|software_patch)$")
    autonomy_level: str = Field(
        "prepare",
        pattern="^(observe|prepare|execute_reversible)$",
    )
    required_capabilities: list[str] = Field(default_factory=list, max_length=20)
    task_payload: dict = Field(default_factory=dict)
    trigger_type: str = Field("manual", pattern="^(manual|interval)$")
    interval_seconds: int | None = Field(default=None, ge=60, le=604800)
    max_runs: int | None = Field(default=None, ge=1, le=100000)
    start_immediately: bool = True

    @model_validator(mode="after")
    def validate_schedule_and_autonomy(self):
        if self.trigger_type == "interval" and self.interval_seconds is None:
            raise ValueError("interval_seconds is required for interval missions")
        if self.trigger_type == "manual" and self.interval_seconds is not None:
            raise ValueError("interval_seconds is only valid for interval missions")
        if self.task_type == "software_patch" and self.autonomy_level != "execute_reversible":
            raise ValueError("software_patch missions require autonomy_level=execute_reversible")
        return self


class PersonalAgentMissionControl(BaseModel):
    reason: str = Field("", max_length=1000)


class PersonalAgentRunRequest(BaseModel):
    trigger: str = Field("manual", pattern="^manual$")
