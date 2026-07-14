"""Tests for application settings."""

from mylife.core.config import Settings


def test_settings_have_local_defaults() -> None:
    settings = Settings()

    assert settings.app_name == "My Life"
    assert settings.environment == "local"
    assert settings.database_url.startswith("sqlite")


def test_settings_read_from_env(monkeypatch) -> None:
    monkeypatch.setenv("MYLIFE_ENVIRONMENT", "production")
    monkeypatch.setenv("MYLIFE_DATABASE_URL", "postgresql://u:p@localhost/db")

    settings = Settings()

    assert settings.environment == "production"
    assert settings.database_url == "postgresql://u:p@localhost/db"
