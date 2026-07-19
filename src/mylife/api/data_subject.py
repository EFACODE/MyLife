"""Data-subject rights endpoints — export and delete your account.

See ``specs/domain/identity/data-subject-rights.md`` (T2.5).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.db.base import get_session
from mylife.identity import User
from mylife.identity.data_subject import DataSubjectService, ErasureResult, ExportBundle

router = APIRouter(tags=["data-subject"])


@router.get("/me/export", response_model=ExportBundle)
def export_my_data(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ExportBundle:
    """Export all of the authenticated user's data."""
    return DataSubjectService(session).export(current_user.user_id)


@router.delete("/me", response_model=ErasureResult)
def delete_my_account(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ErasureResult:
    """Erase the authenticated user's account and all their data."""
    return DataSubjectService(session).erase(current_user.user_id)
