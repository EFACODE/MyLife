"""Notification preference endpoints.

Authenticated, user-scoped access to a user's notification delivery
preferences (which channels are enabled) and their registered alert emails
and WhatsApp phone numbers (multiple of each allowed). See
``specs/domain/notifications/outbound-delivery.md`` (T4.8).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.core.events.envelope import utcnow
from mylife.db.base import get_session
from mylife.identity import User
from mylife.notifications import (
    AlertEmail,
    AlertPhone,
    DuplicateAlertEmailError,
    DuplicateAlertPhoneError,
    NotificationPreference,
    NotificationPreferenceService,
    UnknownAlertEmailError,
    UnknownAlertPhoneError,
)

router = APIRouter(tags=["notifications"])


class SetPreferencesRequest(BaseModel):
    """Request to update which notification channels the user has enabled."""

    email_enabled: bool = True
    whatsapp_enabled: bool = False


class AddAlertEmailRequest(BaseModel):
    """Request to register an alert email address."""

    email: str = Field(min_length=3)


class AddAlertPhoneRequest(BaseModel):
    """Request to register an alert WhatsApp phone number."""

    phone: str = Field(min_length=1)


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
    """Create or update the authenticated user's enabled channels."""
    return NotificationPreferenceService(session).set(
        current_user.user_id,
        email_enabled=request.email_enabled,
        whatsapp_enabled=request.whatsapp_enabled,
        now=utcnow(),
    )


@router.post("/notifications/alert-emails", response_model=AlertEmail, status_code=201)
def add_alert_email(
    request: AddAlertEmailRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> AlertEmail:
    """Register an alert email address for the authenticated user."""
    try:
        return NotificationPreferenceService(session).add_alert_email(
            current_user.user_id, request.email, now=utcnow()
        )
    except DuplicateAlertEmailError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/notifications/alert-emails", response_model=list[AlertEmail])
def list_alert_emails(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[AlertEmail]:
    """List the authenticated user's registered alert email addresses."""
    return NotificationPreferenceService(session).list_alert_emails(current_user.user_id)


@router.delete("/notifications/alert-emails/{alert_email_id}", status_code=204)
def delete_alert_email(
    alert_email_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Remove one of the user's registered alert email addresses."""
    try:
        NotificationPreferenceService(session).delete_alert_email(
            current_user.user_id, alert_email_id
        )
    except UnknownAlertEmailError as exc:
        raise HTTPException(status_code=404, detail="alert email not found") from exc


@router.post("/notifications/alert-phones", response_model=AlertPhone, status_code=201)
def add_alert_phone(
    request: AddAlertPhoneRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> AlertPhone:
    """Register an alert WhatsApp phone number for the authenticated user."""
    try:
        return NotificationPreferenceService(session).add_alert_phone(
            current_user.user_id, request.phone, now=utcnow()
        )
    except DuplicateAlertPhoneError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/notifications/alert-phones", response_model=list[AlertPhone])
def list_alert_phones(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[AlertPhone]:
    """List the authenticated user's registered alert WhatsApp phone numbers."""
    return NotificationPreferenceService(session).list_alert_phones(current_user.user_id)


@router.delete("/notifications/alert-phones/{alert_phone_id}", status_code=204)
def delete_alert_phone(
    alert_phone_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> None:
    """Remove one of the user's registered alert WhatsApp phone numbers."""
    try:
        NotificationPreferenceService(session).delete_alert_phone(
            current_user.user_id, alert_phone_id
        )
    except UnknownAlertPhoneError as exc:
        raise HTTPException(status_code=404, detail="alert phone not found") from exc
