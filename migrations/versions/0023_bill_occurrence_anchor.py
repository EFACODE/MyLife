"""bill occurrence anchor

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-22 20:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401  (kept for consistency across migrations)
from alembic import op  # noqa: F401  (kept for consistency across migrations)

# revision identifiers, used by Alembic.
revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("bills", sa.Column("occurrence_anchor_year", sa.Integer(), nullable=True))
    op.add_column("bills", sa.Column("occurrence_anchor_month", sa.Integer(), nullable=True))

    # Backfill existing bills: the anchor defaults to their registration
    # month, matching the occurrence-cap behavior already shipped in 0022.
    bind = op.get_bind()
    bills = sa.table(
        "bills",
        sa.column("bill_id", sa.Uuid()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("occurrence_anchor_year", sa.Integer()),
        sa.column("occurrence_anchor_month", sa.Integer()),
    )
    for bill_id, created_at in bind.execute(
        sa.select(bills.c.bill_id, bills.c.created_at)
    ).fetchall():
        bind.execute(
            bills.update()
            .where(bills.c.bill_id == bill_id)
            .values(
                occurrence_anchor_year=created_at.year, occurrence_anchor_month=created_at.month
            )
        )

    with op.batch_alter_table("bills") as batch_op:
        batch_op.alter_column("occurrence_anchor_year", nullable=False)
        batch_op.alter_column("occurrence_anchor_month", nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("bills", "occurrence_anchor_month")
    op.drop_column("bills", "occurrence_anchor_year")
