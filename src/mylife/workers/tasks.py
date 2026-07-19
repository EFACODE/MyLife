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
    from mylife.identity.consent import ConsentService

    connector = registry.get(source)
    client = redis.from_url(get_settings().redis_url)  # type: ignore[no-untyped-call]
    bus = RedisStreamPublisher(client)
    factory = get_session_factory()
    with factory() as session:
        # Enforce consent: the worker fails closed if the user has not consented
        # to this source.
        result = ConnectorRunner(session, bus).sync(
            connector,
            FetchContext(user_id=uuid.UUID(user_id), correlation_id=new_correlation_id()),
            consent=ConsentService(session, bus),
        )
    return {
        "source": result.source,
        "raw_ingested": result.raw_ingested,
        "events_created": result.events_created,
        "skipped_duplicates": result.skipped_duplicates,
    }


@celery_app.task(name="mylife.extract_document_text")  # type: ignore[untyped-decorator]  # Celery decorator is untyped
def extract_document_text(user_id: str, document_id: str) -> dict[str, object]:
    """Extract a document's text into the derived store (T6.2)."""
    import redis

    from mylife.core.config import get_settings
    from mylife.core.context import new_correlation_id
    from mylife.core.events import RedisStreamPublisher
    from mylife.core.events.envelope import utcnow
    from mylife.db.base import get_session_factory
    from mylife.knowledge import ExtractionService, FilesystemBlobStore

    settings = get_settings()
    client = redis.from_url(settings.redis_url)  # type: ignore[no-untyped-call]
    bus = RedisStreamPublisher(client)
    blob_store = FilesystemBlobStore(settings.blob_store_path)
    factory = get_session_factory()
    with factory() as session:
        result = ExtractionService(session, bus, blob_store).extract_document(
            uuid.UUID(user_id),
            uuid.UUID(document_id),
            now=utcnow(),
            correlation_id=new_correlation_id(),
        )
    return {
        "document_id": str(result.document_id),
        "method": result.method,
        "extractor_version": result.extractor_version,
        "char_count": result.char_count,
    }


@celery_app.task(name="mylife.run_weekly_insights")  # type: ignore[untyped-decorator]  # Celery decorator is untyped
def run_weekly_insights(user_id: str) -> dict[str, object]:
    """Evaluate the governed alert rules for a user (T7.3)."""
    import redis

    from mylife.assistant.alerts import AlertsService
    from mylife.core.config import get_settings
    from mylife.core.context import new_correlation_id
    from mylife.core.events import RedisStreamPublisher
    from mylife.core.events.envelope import utcnow
    from mylife.db.base import get_session_factory

    client = redis.from_url(get_settings().redis_url)  # type: ignore[no-untyped-call]
    bus = RedisStreamPublisher(client)
    factory = get_session_factory()
    with factory() as session:
        insights = AlertsService(session, bus).run(
            uuid.UUID(user_id), now=utcnow(), correlation_id=new_correlation_id()
        )
    return {"alerts": len(insights)}
