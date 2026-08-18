from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./human_agency.db"
    api_key: str = "change-me"

    token_encryption_key: str = ""
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/v1/connectors/google/callback"
    google_sync_lookback_days: int = 14
    google_sync_lookahead_days: int = 60
    google_max_gmail_messages: int = 250

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
