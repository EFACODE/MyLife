"""Tests for password hashing and JWT tokens (T2.2)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from mylife.identity.security import (
    TokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

# Token validity is checked against the real clock, so anchor to now.
NOW = datetime.now(UTC)


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("s3cretpw")
    assert hashed != "s3cretpw"
    assert verify_password("s3cretpw", hashed)
    assert not verify_password("wrong", hashed)


def test_verify_rejects_garbage_hash() -> None:
    assert not verify_password("x", "not-a-valid-argon2-hash")


def test_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    token = create_access_token(user_id, now=NOW)

    claims = decode_access_token(token)
    assert claims.sub == user_id
    assert claims.iss == "mylife"


def test_expired_token_rejected() -> None:
    token = create_access_token(uuid.uuid4(), now=NOW - timedelta(days=2))
    with pytest.raises(TokenError):
        decode_access_token(token)


def test_tampered_token_rejected() -> None:
    with pytest.raises(TokenError):
        decode_access_token("garbage.token.value")
