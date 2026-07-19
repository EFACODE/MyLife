"""Authentication endpoints and the current-user dependency.

``POST /auth/login`` (OAuth2 password flow) issues a JWT; ``get_current_user``
resolves a bearer token to a ``User``; ``GET /auth/me`` returns it. See
``specs/domain/identity/authentication.md`` (T2.2).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from mylife.api.deps import get_event_bus
from mylife.core.config import get_settings
from mylife.core.events import EventBus
from mylife.core.events.envelope import utcnow
from mylife.db.base import get_session
from mylife.identity import IdentityService, User
from mylife.identity.security import TokenError, create_access_token, decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

router = APIRouter(tags=["auth"])

_UNAUTHENTICATED = {"WWW-Authenticate": "Bearer"}


class TokenResponse(BaseModel):
    """An issued access token."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


@router.post("/auth/login", response_model=TokenResponse)
def login(
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> TokenResponse:
    """Exchange email+password for an access token."""
    user = IdentityService(session, bus).authenticate(form.username, form.password)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid credentials", headers=_UNAUTHENTICATED)
    token = create_access_token(user.user_id, now=utcnow())
    return TokenResponse(access_token=token, expires_in=get_settings().access_token_ttl_seconds)


def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    session: Annotated[Session, Depends(get_session)],
    bus: Annotated[EventBus, Depends(get_event_bus)],
) -> User:
    """Resolve the bearer token to the authenticated user (401 otherwise)."""
    try:
        claims = decode_access_token(token)
    except TokenError:
        raise HTTPException(
            status_code=401, detail="invalid token", headers=_UNAUTHENTICATED
        ) from None
    user = IdentityService(session, bus).get_user(claims.sub)
    if user is None:
        raise HTTPException(status_code=401, detail="unknown user", headers=_UNAUTHENTICATED)
    return user


@router.get("/auth/me", response_model=User)
def read_me(current_user: Annotated[User, Depends(get_current_user)]) -> User:
    """Return the authenticated user."""
    return current_user
