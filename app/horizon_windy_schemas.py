from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


FRANCE_WINDY_MODELS = {"aromeFrance", "iconEu", "gfs"}
WINDY_PARAMETERS = {"temp", "dewpoint", "precip", "wind", "windGust", "cape", "ptype", "rh", "pressure"}


class HorizonWindyPollRequest(BaseModel):
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    geography: list[str] = Field(default_factory=lambda: ["FR"], max_length=16)
    models: list[str] = Field(default_factory=lambda: ["aromeFrance", "iconEu", "gfs"], min_length=1, max_length=3)
    parameters: list[str] = Field(
        default_factory=lambda: ["temp", "precip", "wind", "windGust", "rh", "pressure"],
        min_length=1,
        max_length=9,
    )
    horizon_hours: int = Field(default=168, ge=6, le=240)
    heat_watch_threshold_c: float = Field(default=32.0, ge=25.0, le=45.0)
    max_heat_model_spread_c: float = Field(default=5.0, ge=1.0, le=15.0)

    @model_validator(mode="after")
    def validate_contract(self):
        unsupported_models = sorted(set(self.models) - FRANCE_WINDY_MODELS)
        if unsupported_models:
            raise ValueError(f"unsupported Windy model(s) for HORIZON France: {', '.join(unsupported_models)}")
        unsupported_parameters = sorted(set(self.parameters) - WINDY_PARAMETERS)
        if unsupported_parameters:
            raise ValueError(f"unsupported Windy parameter(s): {', '.join(unsupported_parameters)}")
        if len(set(self.models)) != len(self.models):
            raise ValueError("Windy models must be unique")
        if "temp" not in self.parameters:
            raise ValueError("HORIZON Windy consensus currently requires the temp parameter")
        return self
