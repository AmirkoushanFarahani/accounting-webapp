"""Persist business presentation profiles; existing users remain retail."""

import sqlalchemy as sa

from alembic import op

revision = "20260907_0012"
down_revision = "20260903_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(
            sa.Column("business_category", sa.String(20), nullable=False, server_default="RETAIL")
        )
        batch.create_check_constraint(
            "valid_business_category",
            "business_category IN ('RETAIL','EDUCATION','ONLINE','SERVICES')",
        )


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_constraint("valid_business_category", type_="check")
        batch.drop_column("business_category")
