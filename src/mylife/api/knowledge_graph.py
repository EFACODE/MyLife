"""Knowledge-graph endpoints.

Authenticated, user-scoped consolidation and exploration of the cross-domain
entity/relationship graph. See ``specs/domain/knowledge/knowledge-graph.md`` (T6.4).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.db.base import get_session
from mylife.identity import User
from mylife.knowledge import ConsolidationResult, KnowledgeGraphService
from mylife.timeline import EntityRecord, Neighborhood, RelationshipRecord

router = APIRouter(tags=["knowledge-graph"])


@router.post("/knowledge-graph/consolidate", response_model=ConsolidationResult)
def consolidate(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ConsolidationResult:
    """Rebuild the authenticated user's cross-domain knowledge graph."""
    return KnowledgeGraphService(session).consolidate(current_user.user_id)


@router.get("/knowledge-graph/entities", response_model=list[EntityRecord])
def list_entities(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[EntityRecord]:
    """List the authenticated user's consolidated entities."""
    return KnowledgeGraphService(session).entities(current_user.user_id)


@router.get("/knowledge-graph/relationships", response_model=list[RelationshipRecord])
def list_relationships(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[RelationshipRecord]:
    """List the authenticated user's consolidated relationships."""
    return KnowledgeGraphService(session).relationships(current_user.user_id)


@router.get("/knowledge-graph/entities/{entity_id}/neighbors", response_model=Neighborhood)
def entity_neighbors(
    entity_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> Neighborhood:
    """Return an entity's one-hop neighborhood."""
    neighborhood = KnowledgeGraphService(session).neighbors(current_user.user_id, entity_id)
    if neighborhood is None:
        raise HTTPException(status_code=404, detail="entity not found")
    return neighborhood
