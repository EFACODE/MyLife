"""Password hashing and JWT access tokens.

Argon2 for password hashing (via ``argon2-cffi``) and HS256 JWTs (via ``PyJWT``)
— chosen to avoid the ``cryptography`` Rust binding, and OIDC-upgradeable to
RS256 later. The signing secret comes from settings (never hardcoded). See
``specs/domain/identity/authentication.md`` (T2.2).
"""

import uuid
from datetime import datetime
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from pydantic import BaseModel, ConfigDict

from mylife.core.config import get_settings

_hasher = PasswordHasher()


class TokenError(Exception):
    """Raised when an access token is missing, invalid or expired."""


class TokenClaims(BaseModel):
    """Validated JWT claims."""

    model_config = ConfigDict(frozen=True)

    sub: uuid.UUID
    iss: str
    iat: int
    exp: int


def hash_password(password: str) -> str:
    """Return an Argon2 hash of ``password``."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether ``password`` matches ``password_hash`` (constant-time)."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: uuid.UUID, *, now: datetime) -> str:
    """Return a signed HS256 JWT for ``user_id``."""
    settings = get_settings()
    issued_at = int(now.timestamp())
    payload = {
        "sub": str(user_id),
        "iss": settings.jwt_issuer,
        "iat": issued_at,
        "exp": issued_at + settings.access_token_ttl_seconds,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenClaims:
    """Decode and validate a JWT, or raise :class:`TokenError`."""
    settings = get_settings()
    try:
        decoded: dict[str, Any] = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "iss"]},
        )
        return TokenClaims(
            sub=uuid.UUID(decoded["sub"]),
            iss=decoded["iss"],
            iat=decoded["iat"],
            exp=decoded["exp"],
        )
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise TokenError(str(exc)) from exc
