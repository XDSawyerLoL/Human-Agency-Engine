from pydantic import BaseModel, Field


class HumanCommitPrepare(BaseModel):
    candidate_id: int
    audience: str = Field(..., min_length=1, max_length=255)
    expires_in_seconds: int = Field(300, ge=60, le=1800)
    rollback_plan: str = Field(..., min_length=8, max_length=4000)
    confirm: str


class HumanCommitConfirm(BaseModel):
    confirm: str


class HumanCommitRevoke(BaseModel):
    reason: str = Field("user revoked human commit", min_length=3, max_length=500)


class DualKeyDryRunRequest(BaseModel):
    delegation_token: str = Field(..., min_length=20)
    human_commit_token: str = Field(..., min_length=20)
    audience: str = Field(..., min_length=1, max_length=255)
    action_fingerprint: str = Field(..., min_length=16, max_length=80)
    request_id: str = Field(..., min_length=8, max_length=128)
