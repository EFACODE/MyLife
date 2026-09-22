"""bill max_occurrences

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-22 18:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401  (kept for consistency across migrations)
from alembic import op  # noqa: F401  (kept for consistency across migrations)

# revision identifiers, used by Alembic.
revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "bills",
        sa.Column("max_occurrences", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("bills", "max_occurrences")
