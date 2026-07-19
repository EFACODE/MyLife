"""Data-subject rights endpoints — export and delete your account.

See ``specs/domain/identity/data-subject-rights.md`` (T2.5).
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from mylife.api.auth import get_current_user
from mylife.api.deps import get_blob_store
from mylife.db.base import get_session
from mylife.identity import User
from mylife.identity.data_subject import DataSubjectService, ErasureResult, ExportBundle
from mylife.knowledge import BlobStore

router = APIRouter(tags=["data-subject"])


@router.get("/me/export", response_model=ExportBundle)
def export_my_data(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> ExportBundle:
    """Export all of the authenticated user's data."""
    return DataSubjectService(session, blob_store).export(current_user.user_id)


@router.delete("/me", response_model=ErasureResult)
def delete_my_account(
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    blob_store: Annotated[BlobStore, Depends(get_blob_store)],
) -> ErasureResult:
    """Erase the authenticated user's account and all their data."""
    return DataSubjectService(session, blob_store).erase(current_user.user_id)
