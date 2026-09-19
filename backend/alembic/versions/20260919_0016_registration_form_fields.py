"""Store fields shown on the school registration form."""

import sqlalchemy as sa

from alembic import op

revision = "20260919_0016"
down_revision = "20260919_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("school_courses", sa.Column("instructor_name", sa.String(200), nullable=True))
    op.add_column("students", sa.Column("student_phone", sa.String(32), nullable=True))
    op.add_column(
        "students",
        sa.Column(
            "registration_date", sa.Date(), server_default=sa.text("CURRENT_DATE"), nullable=False
        ),
    )
    op.add_column("students", sa.Column("first_exam_date", sa.Date(), nullable=True))
    op.add_column("students", sa.Column("academic_track", sa.String(100), nullable=True))
    op.add_column(
        "students",
        sa.Column(
            "book_voucher_eligible", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
    )
    op.add_column(
        "students",
        sa.Column("exam_registered", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    for column in (
        "exam_registered", "book_voucher_eligible", "academic_track", "first_exam_date",
        "registration_date", "student_phone",
    ):
        op.drop_column("students", column)
    op.drop_column("school_courses", "instructor_name")
