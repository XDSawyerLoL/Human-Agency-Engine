from pydantic import BaseModel, Field


class DelegationIssue(BaseModel):
    candidate_id: int
    capability: str = Field(..., pattern="^(inspect|prepare|execute_reversible)$")
    audience: str = Field(..., min_length=1, max_length=255)
    expires_in_seconds: int = Field(900, ge=60, le=604800)
    max_uses: int = Field(1, ge=1, le=20)
    constraints: dict = Field(default_factory=dict)
    confirm: str
    execute_ack: bool = False


class DelegationVerify(BaseModel):
    token: str
    audience: str | None = None


class DelegationConsume(BaseModel):
    token: str
    audience: str
    request_id: str = Field(..., min_length=8, max_length=128)
    action_fingerprint: str | None = None
    metadata_json: dict = Field(default_factory=dict)


class DelegationRevoke(BaseModel):
    reason: str = "user revoked delegation"


class SigningIdentityRotate(BaseModel):
    confirm: str
