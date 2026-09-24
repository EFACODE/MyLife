"""Third-party credential vault (T4.9).

Encrypts a per-user, per-provider secret (e.g. an Open Finance aggregator API
key) at rest, so a connector can recover it in plaintext to call the external
API without ever storing it unencrypted. Distinct from ``CredentialRow``
(T2.2, an Argon2 *hash* the platform never reads back) — a third-party secret
must round-trip. See ``specs/domain/identity/third-party-credentials.md``.
"""

import uuid
from datetime import datetime

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from mylife.core.events.store import _stored_utc
from mylife.db.base import Base


class ThirdPartyCredentialRow(Base):
    """One encrypted secret per ``(user_id, provider)``."""

    __tablename__ = "third_party_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String, primary_key=True)
    secret_ciphertext: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class CredentialVault:
    """Stores/reads/removes encrypted third-party secrets for a user."""

    def __init__(self, session: Session, encryption_key: str) -> None:
        self._session = session
        self._fernet = Fernet(encryption_key.encode())

    def store(self, user_id: uuid.UUID, provider: str, secret: str, *, now: datetime) -> None:
        """Encrypt and upsert ``secret`` for ``(user_id, provider)``."""
        ciphertext = self._fernet.encrypt(secret.encode()).decode()
        row = self._session.get(ThirdPartyCredentialRow, (user_id, provider))
        if row is None:
            self._session.add(
                ThirdPartyCredentialRow(
                    user_id=user_id,
                    provider=provider,
                    secret_ciphertext=ciphertext,
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            row.secret_ciphertext = ciphertext
            row.updated_at = now
        self._session.commit()

    def get(self, user_id: uuid.UUID, provider: str) -> str | None:
        """Return the decrypted secret for ``(user_id, provider)``, or ``None``."""
        row = self._session.get(ThirdPartyCredentialRow, (user_id, provider))
        if row is None:
            return None
        try:
            return self._fernet.decrypt(row.secret_ciphertext.encode()).decode()
        except InvalidToken:
            return None

    def delete(self, user_id: uuid.UUID, provider: str) -> None:
        """Remove the stored secret for ``(user_id, provider)``; a no-op if absent."""
        row = self._session.get(ThirdPartyCredentialRow, (user_id, provider))
        if row is not None:
            self._session.delete(row)
            self._session.commit()

    def updated_at(self, user_id: uuid.UUID, provider: str) -> datetime | None:
        """Return when the credential was last stored, or ``None`` if absent."""
        row = self._session.get(ThirdPartyCredentialRow, (user_id, provider))
        return _stored_utc(row.updated_at) if row is not None else None
