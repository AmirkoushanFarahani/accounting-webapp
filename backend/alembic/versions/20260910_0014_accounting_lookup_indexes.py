"""Index measured ledger and invoice relationship lookups.

Revision ID: 20260910_0014
Revises: 20260909_0013
"""

from alembic import op

revision = "20260910_0014"
down_revision = "20260909_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_journal_lines_journal_id", "journal_lines", ["journal_id"])
    op.create_index("ix_journal_lines_account_id", "journal_lines", ["account_id"])
    op.create_index("ix_invoice_items_invoice_id", "invoice_items", ["invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_invoice_items_invoice_id", table_name="invoice_items")
    op.drop_index("ix_journal_lines_account_id", table_name="journal_lines")
    op.drop_index("ix_journal_lines_journal_id", table_name="journal_lines")
