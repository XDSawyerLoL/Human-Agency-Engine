from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


_REPOSITORY_PATTERN = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"


class SoftwareAgentBootstrapRequest(BaseModel):
    confirm: str


class SoftwareAgentLaunchRequest(BaseModel):
    preflight_id: str = Field(..., min_length=8, max_length=64)
    idempotency_key: str = Field(..., min_length=12, max_length=128)
    repository: str = Field(..., min_length=3, max_length=255, pattern=_REPOSITORY_PATTERN)
    goal: str = Field(..., min_length=10, max_length=8000)
    quality_commands: list[str] = Field(default_factory=list, max_length=12)
    max_iterations: int | None = Field(default=None, ge=1, le=200)

    @field_validator("quality_commands")
    @classmethod
    def validate_quality_commands(cls, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        for value in values:
            command = value.strip()
            if not command:
                raise ValueError("quality commands must be non-empty")
            if len(command) > 500:
                raise ValueError("quality commands must be at most 500 characters")
            cleaned.append(command)
        return cleaned
