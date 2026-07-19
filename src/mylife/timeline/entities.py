"""Entities & relationships projection.

The first projection: a derived, rebuildable registry of entities and the
relationships between them, updated by reacting to the event stream. Derived
data — mutable and distinct from the append-only ``events``/``raw_records``. See
``specs/domain/timeline/entity-projection.md`` (T3.3).
"""

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any, NamedTuple

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime, Integer, String, UniqueConstraint, delete, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from mylife.core.events import InProcessEventBus, LifeEvent
from mylife.core.events.store import _stored_utc
from mylife.db.base import Base

LIFE_EVENT_RECORDED = "timeline.life_event_recorded"


class EntityRow(Base):
    """A governed entity derived from the event stream (mutable projection)."""

    __tablename__ = "entities"
    __table_args__ = (
        UniqueConstraint("user_id", "entity_type", "entity_key", name="uq_entities_user_type_key"),
    )

    entity_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    entity_type: Mapped[str] = mapped_column(String)
    entity_key: Mapped[str] = mapped_column(String)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    occurrences: Mapped[int] = mapped_column(Integer)


class RelationshipRow(Base):
    """A relationship between two entities (mutable projection)."""

    __tablename__ = "relationships"
    __table_args__ = (
        UniqueConstraint(
            "user_id",
            "source_entity_id",
            "target_entity_id",
            "rel_type",
            name="uq_relationships_edge",
        ),
    )

    relationship_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True)
    source_entity_id: Mapped[uuid.UUID] = mapped_column()
    target_entity_id: Mapped[uuid.UUID] = mapped_column()
    rel_type: Mapped[str] = mapped_column(String)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    occurrences: Mapped[int] = mapped_column(Integer)


class EntityRecord(BaseModel):
    """An entity as read back from the projection."""

    model_config = ConfigDict(frozen=True)

    entity_id: uuid.UUID
    user_id: uuid.UUID
    entity_type: str
    entity_key: str
    first_seen_at: datetime
    last_seen_at: datetime
    occurrences: int


class RelationshipRecord(BaseModel):
    """A relationship as read back from the projection."""

    model_config = ConfigDict(frozen=True)

    relationship_id: uuid.UUID
    user_id: uuid.UUID
    source_entity_id: uuid.UUID
    target_entity_id: uuid.UUID
    rel_type: str
    first_seen_at: datetime
    last_seen_at: datetime
    occurrences: int


class _Entity(NamedTuple):
    entity_type: str
    entity_key: str


class _Extraction(NamedTuple):
    entities: list[_Entity]
    relationships: list[tuple[_Entity, _Entity, str]]


def _extract(event: LifeEvent[Any]) -> _Extraction:
    """Derive entities/relationships from an event (deliberately minimal, T3.3)."""
    source = _Entity("source", event.source)
    entities: list[_Entity] = [source]
    relationships: list[tuple[_Entity, _Entity, str]] = []

    if event.event_type == LIFE_EVENT_RECORDED:
        payload = event.payload.model_dump(mode="json")
        category = payload.get("category")
        if isinstance(category, str) and category:
            category_entity = _Entity("category", category)
            entities.append(category_entity)
            relationships.append((source, category_entity, "records"))

    return _Extraction(entities, relationships)


def _to_entity_record(row: EntityRow) -> EntityRecord:
    return EntityRecord(
        entity_id=row.entity_id,
        user_id=row.user_id,
        entity_type=row.entity_type,
        entity_key=row.entity_key,
        first_seen_at=_stored_utc(row.first_seen_at),
        last_seen_at=_stored_utc(row.last_seen_at),
        occurrences=row.occurrences,
    )


def _to_relationship_record(row: RelationshipRow) -> RelationshipRecord:
    return RelationshipRecord(
        relationship_id=row.relationship_id,
        user_id=row.user_id,
        source_entity_id=row.source_entity_id,
        target_entity_id=row.target_entity_id,
        rel_type=row.rel_type,
        first_seen_at=_stored_utc(row.first_seen_at),
        last_seen_at=_stored_utc(row.last_seen_at),
        occurrences=row.occurrences,
    )


class EntityProjection:
    """Applies events to, and reads from, the entities/relationships registry."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def apply(self, event: LifeEvent[Any]) -> None:
        """Upsert the entities and relationships derived from ``event``."""
        occurred_at = event.occurred_at
        extraction = _extract(event)
        ids: dict[_Entity, uuid.UUID] = {}
        for entity in extraction.entities:
            ids[entity] = self._upsert_entity(event.user_id, entity, occurred_at)
        for source, target, rel_type in extraction.relationships:
            self._upsert_relationship(
                event.user_id, ids[source], ids[target], rel_type, occurred_at
            )

    def _upsert_entity(
        self, user_id: uuid.UUID, entity: _Entity, occurred_at: datetime
    ) -> uuid.UUID:
        stmt = select(EntityRow).where(
            EntityRow.user_id == user_id,
            EntityRow.entity_type == entity.entity_type,
            EntityRow.entity_key == entity.entity_key,
        )
        row = self._session.scalars(stmt).one_or_none()
        if row is None:
            row = EntityRow(
                entity_id=uuid.uuid4(),
                user_id=user_id,
                entity_type=entity.entity_type,
                entity_key=entity.entity_key,
                first_seen_at=occurred_at,
                last_seen_at=occurred_at,
                occurrences=1,
            )
            self._session.add(row)
            self._session.flush()
        else:
            row.occurrences += 1
            row.first_seen_at = min(_stored_utc(row.first_seen_at), occurred_at)
            row.last_seen_at = max(_stored_utc(row.last_seen_at), occurred_at)
        return row.entity_id

    def _upsert_relationship(
        self,
        user_id: uuid.UUID,
        source_entity_id: uuid.UUID,
        target_entity_id: uuid.UUID,
        rel_type: str,
        occurred_at: datetime,
    ) -> None:
        stmt = select(RelationshipRow).where(
            RelationshipRow.user_id == user_id,
            RelationshipRow.source_entity_id == source_entity_id,
            RelationshipRow.target_entity_id == target_entity_id,
            RelationshipRow.rel_type == rel_type,
        )
        row = self._session.scalars(stmt).one_or_none()
        if row is None:
            self._session.add(
                RelationshipRow(
                    relationship_id=uuid.uuid4(),
                    user_id=user_id,
                    source_entity_id=source_entity_id,
                    target_entity_id=target_entity_id,
                    rel_type=rel_type,
                    first_seen_at=occurred_at,
                    last_seen_at=occurred_at,
                    occurrences=1,
                )
            )
            self._session.flush()
        else:
            row.occurrences += 1
            row.first_seen_at = min(_stored_utc(row.first_seen_at), occurred_at)
            row.last_seen_at = max(_stored_utc(row.last_seen_at), occurred_at)

    def list_entities(self, user_id: uuid.UUID) -> list[EntityRecord]:
        """Return the user's entities, ordered by type then key."""
        stmt = (
            select(EntityRow)
            .where(EntityRow.user_id == user_id)
            .order_by(EntityRow.entity_type, EntityRow.entity_key)
        )
        return [_to_entity_record(row) for row in self._session.scalars(stmt)]

    def list_relationships(self, user_id: uuid.UUID) -> list[RelationshipRecord]:
        """Return the user's relationships, ordered by type."""
        stmt = (
            select(RelationshipRow)
            .where(RelationshipRow.user_id == user_id)
            .order_by(RelationshipRow.rel_type)
        )
        return [_to_relationship_record(row) for row in self._session.scalars(stmt)]

    def rebuild(self, events: Iterable[LifeEvent[Any]]) -> None:
        """Clear the projection and recompute it from ``events``."""
        self._session.execute(delete(RelationshipRow))
        self._session.execute(delete(EntityRow))
        self._session.flush()
        for event in events:
            self.apply(event)


class EntityProjectionSubscriber:
    """Subscribes the entity projection to the event bus.

    Each published event is applied in its own committed session, decoupled from
    the request/producer transaction.
    """

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def register(self, bus: InProcessEventBus) -> None:
        """Subscribe the projection handler to ``bus``."""
        bus.subscribe(self._handle)

    def _handle(self, event: LifeEvent[Any]) -> None:
        with self._session_factory() as session:
            EntityProjection(session).apply(event)
            session.commit()
