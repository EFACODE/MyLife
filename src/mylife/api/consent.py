"""Consent endpoints.

A user manages their own consent (authenticated via ``get_current_user``). See
``specs/domain/identity/consent.md`` (T2.3).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.api.deps import get_event_bus
from mylife.core.context import get_correlation_id, new_correlation_id
from mylife.core.events import EventBus
from mylife.core.events.envelope import utcnow
from mylife.db.base import get_session
from mylife.identity import User
from mylife.identity.consent import Consent, ConsentService

router = APIRouter(tags=["consent"])


class GrantConsentRequest(BaseModel):
    """Request to grant consent for a scope."""

    scope: str = Field(min_length=1)


@router.post("/consents", response_model=Consent, status_code=201)
def grant_consent(
    request: GrantConsentRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> Consent:
    """Grant consent for a scope for the authenticated user."""
    correlation_id = get_correlation_id() or new_correlation_id()
    return ConsentService(session, bus).grant(
        current_user.user_id, request.scope, now=utcnow(), correlation_id=correlation_id
    )


@router.delete("/consents/{scope}", status_code=204)
def revoke_consent(
    scope: str,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> None:
    """Revoke consent for a scope for the authenticated user."""
    correlation_id = get_correlation_id() or new_correlation_id()
    ConsentService(session, bus).revoke(
        current_user.user_id, scope, now=utcnow(), correlation_id=correlation_id
    )


@router.get("/consents", response_model=list[Consent])
def list_consents(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> list[Consent]:
    """List the authenticated user's consents."""
    return ConsentService(session, bus).list_consents(current_user.user_id)
