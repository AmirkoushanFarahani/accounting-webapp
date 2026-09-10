"""Standalone immediately paid expenses."""

import sqlalchemy as sa

from alembic import op

revision = "20260909_0013"
down_revision = "20260907_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("payment_date", sa.Date(), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("tracking_code", sa.String(100), nullable=True),
        sa.Column(
            "journal_id",
            sa.Uuid(),
            sa.ForeignKey("journal_entries.id", ondelete="RESTRICT"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("amount > 0", name="positive_amount"),
        sa.CheckConstraint("method IN ('CASH','CHECK','BANK_TRANSFER')", name="valid_method"),
    )
    op.create_index("ix_expenses_owner_id", "expenses", ["owner_id"])
    op.create_index("ix_expenses_payment_date", "expenses", ["payment_date"])


def downgrade() -> None:
    op.drop_table("expenses")
