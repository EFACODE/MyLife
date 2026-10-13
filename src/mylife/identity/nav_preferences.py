"""Per-user sidebar menu preferences (T10.12).

A current-state row (a UI preference, not a life fact — like
``notification_preferences``): the order of the web console's menu items and
which of them are hidden. Paths are stored opaquely; the web console owns the
item registry and resolves the preference against it. See
``specs/domain/platform/menu-customization.md``.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict
from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, Session, mapped_column
from sqlalchemy.types import JSON

from mylife.core.events.store import _stored_utc
from mylife.db.base import Base


class NavPreferenceRow(Base):
    """A user's menu order and hidden items."""

    __tablename__ = "nav_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    order: Mapped[list[str]] = mapped_column(JSON)
    hidden: Mapped[list[str]] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class NavPreferences(BaseModel):
    """A user's menu preference; empty lists and no ``updated_at`` when never set."""

    model_config = ConfigDict(frozen=True)

    order: list[str]
    hidden: list[str]
    updated_at: datetime | None


def _unique(paths: list[str]) -> list[str]:
    """Drop duplicates, keeping the first occurrence."""
    return list(dict.fromkeys(paths))


def to_nav_preferences(row: NavPreferenceRow) -> NavPreferences:
    """Map a stored row to the read model."""
    return NavPreferences(
        order=list(row.order), hidden=list(row.hidden), updated_at=_stored_utc(row.updated_at)
    )


class NavPreferenceService:
    """Reads and replaces a user's menu preference."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: uuid.UUID) -> NavPreferences:
        """The user's preference, or the empty default."""
        row = self._session.get(NavPreferenceRow, user_id)
        if row is None:
            return NavPreferences(order=[], hidden=[], updated_at=None)
        return to_nav_preferences(row)

    def set(
        self, user_id: uuid.UUID, *, order: list[str], hidden: list[str], now: datetime
    ) -> NavPreferences:
        """Replace the user's preference (duplicates removed, first wins)."""
        row = self._session.get(NavPreferenceRow, user_id)
        if row is None:
            row = NavPreferenceRow(user_id=user_id)
            self._session.add(row)
        row.order = _unique(order)
        row.hidden = _unique(hidden)
        row.updated_at = now
        self._session.commit()
        return to_nav_preferences(row)
