"""account_external_ref

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-23 00:00:01.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("accounts", sa.Column("external_source", sa.String(), nullable=True))
    op.add_column("accounts", sa.Column("external_id", sa.String(), nullable=True))
    op.create_index(
        "ix_accounts_external_ref",
        "accounts",
        ["user_id", "external_source", "external_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_accounts_external_ref", table_name="accounts")
    op.drop_column("accounts", "external_id")
    op.drop_column("accounts", "external_source")
