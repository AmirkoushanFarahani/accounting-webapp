"""Add school workspaces, courses, students, enrolments, and payment plans.

Revision ID: 20260919_0015
Revises: 20260910_0014
"""

import sqlalchemy as sa

from alembic import op

revision = "20260919_0015"
down_revision = "20260910_0014"
branch_labels = None
depends_on = None

GRADES = "'GRADE_1','GRADE_2','GRADE_3','GRADE_4','GRADE_5','GRADE_6','GRADE_7','GRADE_8','GRADE_9','GRADE_10','GRADE_11','GRADE_12'"


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("school_manager_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_users_school_manager_id_users", "users", ["school_manager_id"], ["id"], ondelete="RESTRICT")
        batch.create_index("ix_users_school_manager_id", ["school_manager_id"])

    op.create_table(
        "school_courses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("grade", sa.String(20), nullable=False),
        sa.Column("price", sa.Numeric(18, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_owner_id", "name", "grade", name="uq_school_course_workspace_name_grade"),
        sa.CheckConstraint(f"grade IN ({GRADES})", name="valid_school_course_grade"),
        sa.CheckConstraint("price >= 0", name="nonnegative_school_course_price"),
    )
    op.create_index("ix_school_courses_workspace_owner_id", "school_courses", ["workspace_owner_id"])
    op.create_index("ix_school_courses_grade", "school_courses", ["grade"])
    op.create_table(
        "school_discount_codes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("uses_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_owner_id", "code", name="uq_school_discount_workspace_code"),
        sa.CheckConstraint("percentage > 0 AND percentage <= 100", name="valid_school_discount_percentage"),
        sa.CheckConstraint("max_uses IS NULL OR max_uses > 0", name="valid_school_discount_max_uses"),
    )
    op.create_index("ix_school_discount_codes_workspace_owner_id", "school_discount_codes", ["workspace_owner_id"])
    op.create_table(
        "students",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("national_id", sa.String(20), nullable=False),
        sa.Column("birth_date", sa.Date(), nullable=False),
        sa.Column("grade", sa.String(20), nullable=False),
        sa.Column("guardian_full_name", sa.String(200), nullable=False),
        sa.Column("guardian_phone", sa.String(32), nullable=False),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("previous_school", sa.String(200), nullable=True),
        sa.Column("emergency_contact", sa.String(200), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("workspace_owner_id", "national_id", name="uq_student_workspace_national_id"),
        sa.CheckConstraint(f"grade IN ({GRADES})", name="valid_student_grade"),
    )
    op.create_index("ix_students_workspace_owner_id", "students", ["workspace_owner_id"])
    op.create_index("ix_students_created_by_id", "students", ["created_by_id"])
    op.create_index("ix_students_grade", "students", ["grade"])
    op.create_table(
        "student_enrollments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("student_id", sa.Uuid(), sa.ForeignKey("students.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("discount_code_id", sa.Uuid(), sa.ForeignKey("school_discount_codes.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("subtotal", sa.Numeric(18, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("total_amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("amount_paid", sa.Numeric(18, 2), server_default="0", nullable=False),
        sa.Column("balance_due", sa.Numeric(18, 2), nullable=False),
        sa.Column("status", sa.String(20), server_default="UNPAID", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("subtotal >= 0 AND discount_amount >= 0 AND total_amount >= 0 AND amount_paid >= 0 AND balance_due >= 0", name="nonnegative_enrollment_amounts"),
        sa.CheckConstraint("status IN ('UNPAID','PARTIALLY_PAID','PAID','OVERDUE')", name="valid_enrollment_status"),
    )
    op.create_index("ix_student_enrollments_workspace_owner_id", "student_enrollments", ["workspace_owner_id"])
    op.create_index("ix_student_enrollments_student_id", "student_enrollments", ["student_id"])
    op.create_index("ix_student_enrollments_created_by_id", "student_enrollments", ["created_by_id"])
    op.create_table(
        "enrollment_courses",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("enrollment_id", sa.Uuid(), sa.ForeignKey("student_enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("course_id", sa.Uuid(), sa.ForeignKey("school_courses.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("course_name", sa.String(200), nullable=False),
        sa.Column("price", sa.Numeric(18, 2), nullable=False),
        sa.UniqueConstraint("enrollment_id", "course_id", name="uq_enrollment_course"),
    )
    op.create_index("ix_enrollment_courses_enrollment_id", "enrollment_courses", ["enrollment_id"])
    op.create_table(
        "enrollment_payments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("enrollment_id", sa.Uuid(), sa.ForeignKey("student_enrollments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("recorded_by_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("method", sa.String(20), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("tracking_code", sa.String(100), nullable=True),
        sa.Column("sayad_id", sa.String(32), nullable=True),
        sa.Column("status", sa.String(20), server_default="PENDING", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="positive_enrollment_payment_amount"),
        sa.CheckConstraint("method IN ('CASH','BANK_TRANSFER','CHECK','INSTALLMENT')", name="valid_enrollment_payment_method"),
        sa.CheckConstraint("status IN ('PENDING','PAID','BOUNCED')", name="valid_enrollment_payment_status"),
    )
    op.create_index("ix_enrollment_payments_workspace_owner_id", "enrollment_payments", ["workspace_owner_id"])
    op.create_index("ix_enrollment_payments_enrollment_id", "enrollment_payments", ["enrollment_id"])
    op.create_index("ix_enrollment_payments_recorded_by_id", "enrollment_payments", ["recorded_by_id"])
    op.create_index("ix_enrollment_payment_due_date", "enrollment_payments", ["due_date"])


def downgrade() -> None:
    op.drop_table("enrollment_payments")
    op.drop_table("enrollment_courses")
    op.drop_table("student_enrollments")
    op.drop_table("students")
    op.drop_table("school_discount_codes")
    op.drop_table("school_courses")
    with op.batch_alter_table("users") as batch:
        batch.drop_index("ix_users_school_manager_id")
        batch.drop_constraint("fk_users_school_manager_id_users", type_="foreignkey")
        batch.drop_column("school_manager_id")
