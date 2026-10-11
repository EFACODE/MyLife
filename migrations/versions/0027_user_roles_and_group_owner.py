"""user roles and group owner

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-11 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("role", sa.String(), nullable=False, server_default="member"))
    op.add_column("households", sa.Column("owner_user_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("households", "owner_user_id")
    op.drop_column("users", "role")
