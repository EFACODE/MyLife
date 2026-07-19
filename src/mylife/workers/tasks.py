"""Worker tasks.

A no-op ``ping`` liveness probe plus ``sync_connector``, which runs a registered
connector for a user (T3.4). Publishing from the worker uses the Redis stream so
in-process subscribers in the app react.
"""

import uuid

from mylife.workers.celery_app import celery_app


@celery_app.task(name="mylife.ping")  # type: ignore[untyped-decorator]  # Celery decorator is untyped
def ping() -> str:
    """Return a constant — a liveness probe for the worker pipeline."""
    return "pong"


@celery_app.task(name="mylife.sync_connector")  # type: ignore[untyped-decorator]  # Celery decorator is untyped
def sync_connector(source: str, user_id: str) -> dict[str, object]:
    """Run the connector registered for ``source`` for ``user_id``."""
    import redis

    from mylife.connectors import ConnectorRunner, FetchContext, registry
    from mylife.core.config import get_settings
    from mylife.core.context import new_correlation_id
    from mylife.core.events import RedisStreamPublisher
    from mylife.db.base import get_session_factory

    connector = registry.get(source)
    client = redis.from_url(get_settings().redis_url)  # type: ignore[no-untyped-call]
    bus = RedisStreamPublisher(client)
    factory = get_session_factory()
    with factory() as session:
        result = ConnectorRunner(session, bus).sync(
            connector,
            FetchContext(user_id=uuid.UUID(user_id), correlation_id=new_correlation_id()),
        )
    return {
        "source": result.source,
        "raw_ingested": result.raw_ingested,
        "events_created": result.events_created,
        "skipped_duplicates": result.skipped_duplicates,
    }
