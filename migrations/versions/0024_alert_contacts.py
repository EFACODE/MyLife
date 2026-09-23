"""alert contacts

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-23 00:40:00.000000

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa  # noqa: F401  (kept for consistency across migrations)
from alembic import op  # noqa: F401  (kept for consistency across migrations)

# revision identifiers, used by Alembic.
revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "alert_emails",
        sa.Column("alert_email_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("alert_email_id"),
    )
    op.create_index(op.f("ix_alert_emails_user_id"), "alert_emails", ["user_id"], unique=False)
    op.create_table(
        "alert_phones",
        sa.Column("alert_phone_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("alert_phone_id"),
    )
    op.create_index(op.f("ix_alert_phones_user_id"), "alert_phones", ["user_id"], unique=False)

    # Migrate any existing single WhatsApp number into the new multi-value
    # registry before dropping the old column.
    bind = op.get_bind()
    preferences = sa.table(
        "notification_preferences",
        sa.column("user_id", sa.Uuid()),
        sa.column("whatsapp_phone", sa.String()),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    alert_phones = sa.table(
        "alert_phones",
        sa.column("alert_phone_id", sa.Uuid()),
        sa.column("user_id", sa.Uuid()),
        sa.column("phone", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    for user_id, whatsapp_phone, updated_at in bind.execute(
        sa.select(preferences.c.user_id, preferences.c.whatsapp_phone, preferences.c.updated_at)
    ).fetchall():
        if whatsapp_phone:
            bind.execute(
                alert_phones.insert().values(
                    alert_phone_id=uuid.uuid4(),
                    user_id=user_id,
                    phone=whatsapp_phone,
                    created_at=updated_at,
                )
            )

    with op.batch_alter_table("notification_preferences") as batch_op:
        batch_op.drop_column("whatsapp_phone")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("notification_preferences") as batch_op:
        batch_op.add_column(sa.Column("whatsapp_phone", sa.String(), nullable=True))
    op.drop_index(op.f("ix_alert_phones_user_id"), table_name="alert_phones")
    op.drop_table("alert_phones")
    op.drop_index(op.f("ix_alert_emails_user_id"), table_name="alert_emails")
    op.drop_table("alert_emails")
