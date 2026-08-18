from pydantic import BaseModel, Field


class SandboxRunnerRegister(BaseModel):
    runner_id: str = Field(..., min_length=3, max_length=96)
    label: str = Field("", max_length=255)
    public_key_b64: str = Field(..., min_length=40, max_length=128)
    confirm: str


class SandboxRunnerRevoke(BaseModel):
    confirm: str


class SandboxEvidence(BaseModel):
    run_id: str = Field(..., min_length=8, max_length=128)
    observed_at_epoch: int = Field(..., ge=1)
    initial_state: dict
    state_after_preflight: dict
    first_result: dict
    state_after_first: dict
    repeat_result: dict
    state_after_repeat: dict
    partial_failure_state_before: dict
    partial_failure_state_after: dict
    state_after_rollback: dict


class SandboxAttestationSubmit(BaseModel):
    adapter_id: str = Field(..., min_length=3, max_length=96)
    version: str = Field(..., min_length=1, max_length=32)
    runner_id: str = Field(..., min_length=3, max_length=96)
    suite_version: str = "hae-adapter-sandbox-v1"
    valid_for_seconds: int = Field(604800, ge=300, le=2592000)
    evidence: SandboxEvidence
    signature_b64: str = Field(..., min_length=40, max_length=256)
