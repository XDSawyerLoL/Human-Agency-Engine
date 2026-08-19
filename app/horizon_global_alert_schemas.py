from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


GDACS_EVENT_TYPES = {"EQ", "TC", "FL", "VO", "WF", "DR"}
GDACS_ALERT_LEVELS = {"green", "orange", "red"}

METEOALARM_COUNTRY_TO_ISO2 = {
    "andorra": "AD",
    "austria": "AT",
    "belgium": "BE",
    "bosnia-herzegovina": "BA",
    "bulgaria": "BG",
    "croatia": "HR",
    "cyprus": "CY",
    "czechia": "CZ",
    "denmark": "DK",
    "estonia": "EE",
    "finland": "FI",
    "france": "FR",
    "germany": "DE",
    "greece": "GR",
    "hungary": "HU",
    "iceland": "IS",
    "ireland": "IE",
    "israel": "IL",
    "italy": "IT",
    "latvia": "LV",
    "lithuania": "LT",
    "luxembourg": "LU",
    "malta": "MT",
    "moldova": "MD",
    "montenegro": "ME",
    "netherlands": "NL",
    "republic-of-north-macedonia": "MK",
    "norway": "NO",
    "poland": "PL",
    "portugal": "PT",
    "romania": "RO",
    "serbia": "RS",
    "slovakia": "SK",
    "slovenia": "SI",
    "spain": "ES",
    "sweden": "SE",
    "switzerland": "CH",
    "ukraine": "UA",
    "united-kingdom": "GB",
}

METEOALARM_CORE_COUNTRIES = [
    "france",
    "belgium",
    "germany",
    "luxembourg",
    "netherlands",
    "switzerland",
    "italy",
    "spain",
    "portugal",
    "united-kingdom",
    "ireland",
]


class HorizonGdacsPollRequest(BaseModel):
    event_types: list[str] = Field(
        default_factory=lambda: ["EQ", "TC", "FL", "VO", "WF", "DR"],
        min_length=1,
        max_length=6,
    )
    alert_levels: list[str] = Field(
        default_factory=lambda: ["green", "orange", "red"],
        min_length=1,
        max_length=3,
    )
    lookback_days: int = Field(default=4, ge=1, le=30)
    page_size: int = Field(default=100, ge=1, le=100)
    max_pages: int = Field(default=2, ge=1, le=10)

    @model_validator(mode="after")
    def validate_contract(self):
        self.event_types = list(dict.fromkeys(str(item).upper() for item in self.event_types))
        unsupported_types = sorted(set(self.event_types) - GDACS_EVENT_TYPES)
        if unsupported_types:
            raise ValueError(f"unsupported GDACS event type(s): {', '.join(unsupported_types)}")
        self.alert_levels = list(dict.fromkeys(str(item).lower() for item in self.alert_levels))
        unsupported_levels = sorted(set(self.alert_levels) - GDACS_ALERT_LEVELS)
        if unsupported_levels:
            raise ValueError(f"unsupported GDACS alert level(s): {', '.join(unsupported_levels)}")
        return self


class HorizonMeteoAlarmPollRequest(BaseModel):
    countries: list[str] = Field(default_factory=lambda: list(METEOALARM_CORE_COUNTRIES), max_length=40)
    all_europe: bool = False
    max_entries_per_country: int = Field(default=250, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_countries(self):
        if self.all_europe:
            self.countries = sorted(METEOALARM_COUNTRY_TO_ISO2)
            return self
        normalized = list(dict.fromkeys(str(item).strip().lower() for item in self.countries if str(item).strip()))
        unsupported = sorted(set(normalized) - set(METEOALARM_COUNTRY_TO_ISO2))
        if unsupported:
            raise ValueError(f"unsupported MeteoAlarm country slug(s): {', '.join(unsupported)}")
        self.countries = normalized
        return self


class HorizonGlobalAlertNormalizeRequest(BaseModel):
    max_observations: int = Field(default=500, ge=1, le=5000)
