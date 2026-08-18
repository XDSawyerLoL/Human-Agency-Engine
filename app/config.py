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

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

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
