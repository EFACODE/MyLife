"""Tests for knowledge-graph consolidation (T6.4)."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from mylife.core.events import InProcessEventBus
from mylife.db.base import Base
from mylife.finance import FinanceService
from mylife.goals import GoalsService
from mylife.health import HealthService
from mylife.knowledge import InMemoryBlobStore, KnowledgeGraphService, KnowledgeService

NOW = datetime(2026, 7, 19, 12, 0, tzinfo=UTC)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        yield db
    engine.dispose()


def _seed_all_domains(session: Session, user: uuid.UUID) -> None:
    bus = InProcessEventBus()
    account = FinanceService(session, bus).create_account(user, "Checking", "BRL", now=NOW)
    FinanceService(session, bus).record_expense(
        user,
        account.account_id,
        4599,
        "BRL",
        "Coffee",
        category="food",
        now=NOW,
        correlation_id="c",
    )
    HealthService(session, bus).record_workout(user, NOW, "run", 42, correlation_id="c")
    GoalsService(session, bus).create_goal(
        user, "Fund", "net_worth", 1000000, "BRL", now=NOW, correlation_id="c"
    )
    KnowledgeService(session, bus, InMemoryBlobStore()).ingest_document(
        user, "statement.pdf", "application/pdf", b"bytes", now=NOW, correlation_id="c"
    )


def test_consolidate_spans_all_domains(session: Session) -> None:
    user = uuid.uuid4()
    _seed_all_domains(session, user)

    service = KnowledgeGraphService(session)
    result = service.consolidate(user)
    assert result.entities > 0

    by_type: dict[str, set[str]] = {}
    for entity in service.entities(user):
        by_type.setdefault(entity.entity_type, set()).add(entity.entity_key)

    assert "food" in by_type.get("category", set())
    assert "run" in by_type.get("activity", set())
    assert "Fund" in by_type.get("goal", set())
    assert "net_worth" in by_type.get("metric", set())
    assert "statement.pdf" in by_type.get("document", set())

    rel_types = {r.rel_type for r in service.relationships(user)}
    assert {"spent_on", "performed", "pursues", "measured_by", "ingested"} <= rel_types


def test_consolidate_is_user_scoped_and_idempotent(session: Session) -> None:
    user = uuid.uuid4()
    other = uuid.uuid4()
    _seed_all_domains(session, user)
    _seed_all_domains(session, other)
    service = KnowledgeGraphService(session)

    first = service.consolidate(user)
    second = service.consolidate(user)  # idempotent — same graph
    assert (first.entities, first.relationships) == (second.entities, second.relationships)

    # Consolidating one user leaves the other's graph untouched.
    service.consolidate(other)
    assert service.consolidate(user).entities == first.entities


def test_neighbors_returns_edges(session: Session) -> None:
    user = uuid.uuid4()
    _seed_all_domains(session, user)
    service = KnowledgeGraphService(session)
    service.consolidate(user)

    goal = next(e for e in service.entities(user) if e.entity_type == "goal")
    neighborhood = service.neighbors(user, goal.entity_id)
    assert neighborhood is not None
    # The goal is measured_by its metric.
    assert any(n.entity_type == "metric" for n in neighborhood.neighbors)
    assert any(edge.rel_type == "measured_by" for edge in neighborhood.edges)


def test_neighbors_foreign_entity_is_none(session: Session) -> None:
    user = uuid.uuid4()
    _seed_all_domains(session, user)
    KnowledgeGraphService(session).consolidate(user)
    assert KnowledgeGraphService(session).neighbors(uuid.uuid4(), uuid.uuid4()) is None
