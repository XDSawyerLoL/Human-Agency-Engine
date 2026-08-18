from pydantic import BaseModel, Field


class AdapterManifestRegister(BaseModel):
    adapter_id: str = Field(..., min_length=3, max_length=96)
    version: str = Field(..., min_length=1, max_length=32)
    audience: str = Field(..., min_length=1, max_length=255)
    supported_action_types: list[str] = Field(..., min_length=1, max_length=50)
    reversible_only: bool = True
    supports_idempotency: bool = True
    supports_rollback: bool = True
    side_effect_free_preflight: bool = True
    external_dispatch_enabled: bool = False
    confirm: str


class AdapterPreflightRequest(BaseModel):
    dry_run_request_id: str = Field(..., min_length=8, max_length=128)
    adapter_id: str = Field(..., min_length=3, max_length=96)
    version: str = Field(..., min_length=1, max_length=32)
    idempotency_key: str = Field(..., min_length=12, max_length=128)
