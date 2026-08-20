from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./human_agency.db"
    api_key: str = "change-me"

    token_encryption_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    render_external_hostname: str = ""
    google_sync_lookback_days: int = 14
    google_sync_lookahead_days: int = 60
    google_max_gmail_messages: int = 250
    # Opaque credential shown after `Authorization: Basic` by the
    # Météo-France API portal. Never commit the real value.
    meteofrance_application_id: str = ""
    # Windy Point Forecast API key. The free testing key intentionally returns
    # modified/shuffled data and must never be treated as production evidence.
    windy_point_forecast_api_key: str = ""

    # Permanent HORIZON world-intelligence collector. Cadences are deliberately
    # operational schedules, never evidence weights or probabilities.
    horizon_collector_enabled: bool = True
    horizon_collector_tick_seconds: int = 30
    horizon_collector_lease_seconds: int = 900
    horizon_collector_max_sources_per_cycle: int = 10
    horizon_collector_sncf_seconds: int = 300
    horizon_collector_vigicrues_seconds: int = 600
    horizon_collector_meteofrance_seconds: int = 600
    horizon_collector_meteoalarm_seconds: int = 600
    horizon_collector_gdelt_seconds: int = 900
    horizon_collector_gdacs_seconds: int = 900
    horizon_collector_fuel_seconds: int = 900
    horizon_collector_rte_seconds: int = 900
    horizon_collector_windy_seconds: int = 1800
    horizon_collector_synthesis_seconds: int = 900
    horizon_collector_max_active_events: int = 200
    horizon_collector_event_graph_lookback_hours: int = 336
    horizon_collector_meteoalarm_all_europe: bool = False
    horizon_collector_rte_region_codes: str = ""
    horizon_collector_windy_points_json: str = "[]"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def model_post_init(self, __context: Any) -> None:
        if not self.google_redirect_uri:
            self.google_redirect_uri = self.resolved_google_redirect_uri

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+psycopg://", 1)
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url

    @property
    def resolved_google_redirect_uri(self) -> str:
        if self.google_redirect_uri:
            return self.google_redirect_uri
        if self.render_external_hostname:
            return (
                f"https://{self.render_external_hostname}"
                "/v1/connectors/google/callback"
            )
        return "http://localhost:8000/v1/connectors/google/callback"

    def validate_runtime(self) -> None:
        errors: list[str] = []

        if bool(self.google_client_id) != bool(self.google_client_secret):
            errors.append(
                "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be configured together"
            )

        if self.horizon_collector_tick_seconds < 5:
            errors.append("HORIZON_COLLECTOR_TICK_SECONDS must be at least 5")
        if self.horizon_collector_lease_seconds < self.horizon_collector_tick_seconds * 3:
            errors.append("HORIZON_COLLECTOR_LEASE_SECONDS must be at least 3x the collector tick")
        if not 1 <= self.horizon_collector_max_sources_per_cycle <= 10:
            errors.append("HORIZON_COLLECTOR_MAX_SOURCES_PER_CYCLE must be between 1 and 10")
        cadence_values = (
            self.horizon_collector_sncf_seconds,
            self.horizon_collector_vigicrues_seconds,
            self.horizon_collector_meteofrance_seconds,
            self.horizon_collector_meteoalarm_seconds,
            self.horizon_collector_gdelt_seconds,
            self.horizon_collector_gdacs_seconds,
            self.horizon_collector_fuel_seconds,
            self.horizon_collector_rte_seconds,
            self.horizon_collector_windy_seconds,
            self.horizon_collector_synthesis_seconds,
        )
        if any(value < 60 for value in cadence_values):
            errors.append("HORIZON collector source cadences must be at least 60 seconds")

        if self.is_production:
            if self.api_key == "change-me" or len(self.api_key) < 32:
                errors.append("API_KEY must be a non-default secret of at least 32 characters")
            if self.database_url.startswith("sqlite"):
                errors.append("Production requires a persistent non-SQLite DATABASE_URL")
            if not self.token_encryption_key:
                errors.append("TOKEN_ENCRYPTION_KEY is required in production")

        if errors:
            raise RuntimeError("Invalid runtime configuration: " + "; ".join(errors))


settings = Settings()
settings.validate_runtime()
