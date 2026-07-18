"""Worker tasks.

Phase 0 ships a single no-op ``ping`` task that proves the worker wiring is
sound end to end. Connector sync and ingestion tasks are added in later phases.
"""

from mylife.workers.celery_app import celery_app


@celery_app.task(name="mylife.ping")  # type: ignore[untyped-decorator]  # Celery decorator is untyped
def ping() -> str:
    """Return a constant — a liveness probe for the worker pipeline."""
    return "pong"
