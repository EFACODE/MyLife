"""Notification preference endpoints.

Authenticated, user-scoped access to a user's notification delivery
preferences (which channels are enabled, and the WhatsApp number to use). See
``specs/domain/notifications/outbound-delivery.md`` (T4.8).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.core.events.envelope import utcnow
from mylife.db.base import get_session
from mylife.identity import User
from mylife.notifications import NotificationPreference, NotificationPreferenceService

router = APIRouter(tags=["notifications"])


class SetPreferencesRequest(BaseModel):
    """Request to update the authenticated user's notification preferences."""

    email_enabled: bool = True
    whatsapp_enabled: bool = False
    whatsapp_phone: str | None = None


@router.get("/notifications/preferences", response_model=NotificationPreference)
def get_preferences(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> NotificationPreference:
    """Return the authenticated user's notification preferences (defaults if unset)."""
    return NotificationPreferenceService(session).get(current_user.user_id)


@router.put("/notifications/preferences", response_model=NotificationPreference)
def set_preferences(
    request: SetPreferencesRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> NotificationPreference:
    """Create or update the authenticated user's notification preferences."""
    return NotificationPreferenceService(session).set(
        current_user.user_id,
        email_enabled=request.email_enabled,
        whatsapp_enabled=request.whatsapp_enabled,
        whatsapp_phone=request.whatsapp_phone,
        now=utcnow(),
    )
