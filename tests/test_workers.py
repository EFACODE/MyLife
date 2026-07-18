"""Tests for the Celery worker scaffolding.

``apply()`` runs the task synchronously in-process, so these tests need no
running broker or worker.
"""

from mylife.workers.celery_app import celery_app
from mylife.workers.tasks import ping


def test_celery_app_configured() -> None:
    assert celery_app.main == "mylife"
    assert celery_app.conf.timezone == "UTC"
    assert celery_app.conf.task_serializer == "json"


def test_ping_task_runs() -> None:
    result = ping.apply()

    assert result.successful()
    assert result.get() == "pong"


def test_ping_task_registered() -> None:
    assert "mylife.ping" in celery_app.tasks
