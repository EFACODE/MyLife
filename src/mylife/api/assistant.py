"""Assistant query endpoint — retrieval-grounded Q&A (T7.2).

Answers a question only from the authenticated user's own data (grounded, cited
as an insight) or refuses when evidence is insufficient. See
``specs/domain/assistant/grounded-query.md``.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.api.deps import get_event_bus
from mylife.assistant.query import Answer, AssistantQueryService
from mylife.core.context import get_correlation_id, new_correlation_id
from mylife.core.events import EventBus
from mylife.core.events.envelope import utcnow
from mylife.db.base import get_session
from mylife.identity import User

router = APIRouter(tags=["assistant"])


class QueryRequest(BaseModel):
    """A question to answer from the user's own data."""

    question: str = Field(min_length=1)


@router.post("/assistant/query", response_model=Answer)
def query_assistant(
    request: QueryRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Answer:
    """Answer the authenticated user's question, grounded in their data (or refuse)."""
    correlation_id = get_correlation_id() or new_correlation_id()
    return AssistantQueryService(session, bus).answer(
        current_user.user_id, request.question, now=utcnow(), correlation_id=correlation_id
    )
