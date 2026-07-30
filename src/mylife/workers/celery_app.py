"""Celery application factory.

The broker and result backend come from application settings (defaulting to
Redis). Tasks live in :mod:`mylife.workers.tasks` and are eagerly imported via
``include`` so they register on import.
"""

from celery import Celery

from mylife.core.config import get_settings


def create_celery() -> Celery:
    """Build and configure the Celery application from settings."""
    settings = get_settings()
    app = Celery(
        "mylife",
        broker=settings.broker_url,
        backend=settings.result_backend,
        include=["mylife.workers.tasks"],
    )
    app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
    )
    return app


celery_app = create_celery()
