"""Store due dates for check-based payment records."""

import sqlalchemy as sa

from alembic import op

revision = "20260920_0018"
down_revision = "20260920_0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payments", sa.Column("check_due_date", sa.Date(), nullable=True))
    op.add_column("bill_payments", sa.Column("check_due_date", sa.Date(), nullable=True))
    op.add_column("expenses", sa.Column("check_due_date", sa.Date(), nullable=True))
    op.add_column("school_costs", sa.Column("check_due_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("school_costs", "check_due_date")
    op.drop_column("expenses", "check_due_date")
    op.drop_column("bill_payments", "check_due_date")
    op.drop_column("payments", "check_due_date")
