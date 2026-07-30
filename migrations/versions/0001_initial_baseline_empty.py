"""initial baseline (empty)

Establishes the Alembic version baseline. No schema yet — domain models and
their tables arrive from T1.2 onward.

Revision ID: 0001
Revises:
Create Date: 2026-07-18

"""

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401  (kept for consistency across migrations)
from alembic import op  # noqa: F401  (kept for consistency across migrations)

# revision identifiers, used by Alembic.
revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""


def downgrade() -> None:
    """Downgrade schema."""
