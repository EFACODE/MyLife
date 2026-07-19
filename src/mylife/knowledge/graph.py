"""Knowledge-graph consolidation (T6.4).

Consolidates the user's entities and relationships across **every** domain into
one graph, reusing the T3.3 projection machinery with a richer, cross-domain
extractor. This extractor lives in the Knowledge context (which may depend on all
domains); Timeline's extractor stays generic. Consolidation is explicit and
user-scoped: it rebuilds the caller's subgraph from their event stream. See
``specs/domain/knowledge/knowledge-graph.md``.
"""

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from mylife.core.events import EventStore, LifeEvent
from mylife.finance.models import EXPENSE_CREATED, TRANSACTION_IMPORTED
from mylife.goals.models import GOAL_CREATED
from mylife.health.models import WORKOUT_COMPLETED
from mylife.knowledge.models import DOCUMENT_INGESTED
from mylife.timeline import (
    Entity,
    EntityProjection,
    EntityRecord,
    Extraction,
    Neighborhood,
    RelationshipRecord,
)
from mylife.timeline.entities import _extract as _timeline_extract

_UNBOUNDED = 1_000_000


class _RawPayload(BaseModel):
    """A permissive payload that preserves arbitrary stored fields."""

    model_config = ConfigDict(extra="allow")


class _RawEvent(LifeEvent[_RawPayload]):
    """A rehydrated event whose payload keeps its original fields (for rebuild)."""


def consolidated_extract(event: LifeEvent[Any]) -> Extraction:
    """Derive cross-domain entities/relationships from ``event``.

    Starts from the generic timeline extraction (the ``source`` node, plus
    timeline categories) and adds domain-specific nodes/edges.
    """
    base = _timeline_extract(event)
    entities = list(base.entities)
    relationships = list(base.relationships)
    source = Entity("source", event.source)
    payload = event.payload.model_dump(mode="json")

    def _add(entity: Entity, rel_type: str, *, from_entity: Entity = source) -> None:
        entities.append(entity)
        relationships.append((from_entity, entity, rel_type))

    if event.event_type in (EXPENSE_CREATED, TRANSACTION_IMPORTED):
        category = payload.get("category")
        if isinstance(category, str) and category:
            _add(Entity("category", category), "spent_on")
    elif event.event_type == WORKOUT_COMPLETED:
        activity = payload.get("activity")
        if isinstance(activity, str) and activity:
            _add(Entity("activity", activity), "performed")
    elif event.event_type == GOAL_CREATED:
        title = payload.get("title")
        metric = payload.get("metric")
        if isinstance(title, str) and title:
            goal_entity = Entity("goal", title)
            _add(goal_entity, "pursues")
            if isinstance(metric, str) and metric:
                _add(Entity("metric", metric), "measured_by", from_entity=goal_entity)
    elif event.event_type == DOCUMENT_INGESTED:
        filename = payload.get("filename")
        if isinstance(filename, str) and filename:
            _add(Entity("document", filename), "ingested")

    return Extraction(entities, relationships)


class ConsolidationResult(BaseModel):
    """Counts from a knowledge-graph consolidation."""

    model_config = ConfigDict(frozen=True)

    entities: int
    relationships: int


class KnowledgeGraphService:
    """Consolidates and reads a user's cross-domain knowledge graph."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._projection = EntityProjection(session, extract=consolidated_extract)

    def consolidate(self, user_id: uuid.UUID) -> ConsolidationResult:
        """Rebuild the user's graph from their events and return the counts."""
        events = EventStore(self._session).read_stream(user_id, limit=_UNBOUNDED)
        self._projection.rebuild_for_user(
            user_id, [stored.rehydrate(_RawEvent) for stored in events]
        )
        self._session.commit()
        return ConsolidationResult(
            entities=len(self._projection.list_entities(user_id)),
            relationships=len(self._projection.list_relationships(user_id)),
        )

    def entities(self, user_id: uuid.UUID) -> list[EntityRecord]:
        """Return the user's consolidated entities."""
        return self._projection.list_entities(user_id)

    def relationships(self, user_id: uuid.UUID) -> list[RelationshipRecord]:
        """Return the user's consolidated relationships."""
        return self._projection.list_relationships(user_id)

    def neighbors(self, user_id: uuid.UUID, entity_id: uuid.UUID) -> Neighborhood | None:
        """Return an entity's one-hop neighborhood (or ``None`` if not theirs)."""
        return self._projection.neighbors(user_id, entity_id)
