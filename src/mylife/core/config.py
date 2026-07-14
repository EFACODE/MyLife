"""Application settings.

Settings are loaded from environment variables (and an optional ``.env`` file)
via ``pydantic-settings``. All values have sensible local-development defaults
so the application boots with zero configuration; production deployments
override them through the environment.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the My Life application."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="MYLIFE_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application metadata
    app_name: str = "My Life"
    environment: str = "local"
    debug: bool = False

    # Persistence. Defaults to an in-process SQLite database so the app runs
    # without external services; overridden with a Postgres URL in real
    # deployments (see Phase 0, T0.2).
    database_url: str = "sqlite:///./mylife.sqlite3"


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
