import pytest

from app.config import Settings


def test_production_rejects_unsafe_defaults():
    settings = Settings(
        app_env="production",
        database_url="sqlite:///./unsafe.db",
        api_key="change-me",
        token_encryption_key="",
    )
    with pytest.raises(RuntimeError) as exc:
        settings.validate_runtime()
    message = str(exc.value)
    assert "API_KEY" in message
    assert "non-SQLite" in message
    assert "TOKEN_ENCRYPTION_KEY" in message


def test_production_accepts_hardened_runtime_config():
    settings = Settings(
        app_env="production",
        database_url="postgresql+psycopg://user:pass@db.example/human_agency",
        api_key="a" * 48,
        token_encryption_key="opaque-encryption-key",
    )
    settings.validate_runtime()


def test_generic_postgres_url_is_normalized_to_psycopg3():
    settings = Settings(database_url="postgresql://user:pass@db.example/human_agency")
    assert settings.sqlalchemy_database_url.startswith("postgresql+psycopg://")


def test_render_hostname_derives_google_callback_url():
    settings = Settings(
        google_redirect_uri="",
        render_external_hostname="human-agency-engine.onrender.com",
    )
    assert settings.google_redirect_uri == (
        "https://human-agency-engine.onrender.com/v1/connectors/google/callback"
    )
