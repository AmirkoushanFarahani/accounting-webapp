"""Add manager-entered school cost factors."""

import sqlalchemy as sa

from alembic import op

revision = "20260920_0017"
down_revision = "20260919_0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "school_costs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("workspace_owner_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("factor_number", sa.String(length=100), nullable=False),
        sa.Column("vendor_name", sa.String(length=200), nullable=True),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("cost_date", sa.Date(), nullable=False),
        sa.Column("payment_method", sa.String(length=20), nullable=False),
        sa.Column("tracking_code", sa.String(length=100), nullable=True),
        sa.Column("notes", sa.String(length=1000), nullable=True),
        sa.CheckConstraint("amount > 0", name="positive_school_cost_amount"),
        sa.CheckConstraint(
            "payment_method IN ('CASH','CHECK','BANK_TRANSFER')",
            name="valid_school_cost_payment_method",
        ),
        sa.ForeignKeyConstraint(["workspace_owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_owner_id", "factor_number", name="uq_school_cost_workspace_factor_number"
        ),
    )
    op.create_index("ix_school_costs_workspace_owner_id", "school_costs", ["workspace_owner_id"])
    op.create_index("ix_school_costs_created_by_id", "school_costs", ["created_by_id"])
    op.create_index("ix_school_costs_cost_date", "school_costs", ["cost_date"])


def downgrade() -> None:
    op.drop_index("ix_school_costs_cost_date", table_name="school_costs")
    op.drop_index("ix_school_costs_created_by_id", table_name="school_costs")
    op.drop_index("ix_school_costs_workspace_owner_id", table_name="school_costs")
    op.drop_table("school_costs")
