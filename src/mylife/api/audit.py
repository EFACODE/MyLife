"""Audit endpoint — a user's own security trail.

See ``specs/domain/identity/audit-log.md`` (T2.4).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.db.base import get_session
from mylife.identity import User
from mylife.identity.audit import AuditEntry, AuditService

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=list[AuditEntry])
def read_audit(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[AuditEntry]:
    """Return the authenticated user's audit entries (newest first)."""
    return AuditService(session).list_for_subject(current_user.user_id)
