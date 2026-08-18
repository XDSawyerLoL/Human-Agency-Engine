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
