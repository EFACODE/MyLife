"""Application settings.

Settings are loaded from environment variables (and an optional ``.env`` file)
via ``pydantic-settings``. All values have sensible local-development defaults
so the application boots with zero configuration; production deployments
override them through the environment.
"""

import secrets
from functools import lru_cache

from pydantic import Field
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
    # without external services; overridden with the Postgres URL from the
    # local docker-compose environment (see Phase 0, T0.2) or a managed
    # database in real deployments.
    database_url: str = "sqlite:///./mylife.sqlite3"

    # Redis, used by later phases (e.g. the event bus, T1.3). Defaults to the
    # local docker-compose Redis instance.
    redis_url: str = "redis://localhost:6379/0"

    # Celery (T0.9). Both the broker and the result backend default to Redis
    # (``redis_url``); override either independently through the environment.
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    # Authentication (T2.2). The JWT signing secret has NO hardcoded value: it
    # defaults to a random per-process value so local dev works without config,
    # but production MUST set MYLIFE_JWT_SECRET (a stable value shared across
    # processes) or tokens won't validate between workers/restarts.
    jwt_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(32))
    jwt_algorithm: str = "HS256"
    access_token_ttl_seconds: int = 3600
    jwt_issuer: str = "mylife"

    # Knowledge document storage (T6.1). Document bytes are stored in object
    # storage; locally that is a directory tree. Production overrides this (or a
    # future S3/GCS adapter) through the environment.
    blob_store_path: str = "./var/blobs"

    # Static SPA serving (T11.1). When set to the built web bundle directory, the
    # API serves the single-page app same-origin (so no CORS is needed). Unset in
    # development/tests (the SPA runs on the Vite dev server).
    static_dir: str | None = None

    @property
    def broker_url(self) -> str:
        """Effective Celery broker URL (falls back to ``redis_url``)."""
        return self.celery_broker_url or self.redis_url

    @property
    def result_backend(self) -> str:
        """Effective Celery result backend URL (falls back to ``redis_url``)."""
        return self.celery_result_backend or self.redis_url


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()
