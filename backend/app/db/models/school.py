from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

GRADE_CHECK = (
    "grade IN ('GRADE_1','GRADE_2','GRADE_3','GRADE_4','GRADE_5','GRADE_6',"
    "'GRADE_7','GRADE_8','GRADE_9','GRADE_10','GRADE_11','GRADE_12')"
)


class SchoolCourse(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "school_courses"
    __table_args__ = (
        UniqueConstraint(
            "workspace_owner_id", "name", "grade", name="uq_school_course_workspace_name_grade"
        ),
        CheckConstraint(GRADE_CHECK, name="valid_school_course_grade"),
        CheckConstraint("price >= 0", name="nonnegative_school_course_price"),
    )

    workspace_owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    instructor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    grade: Mapped[str] = mapped_column(String(20), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class DiscountCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "school_discount_codes"
    __table_args__ = (
        UniqueConstraint("workspace_owner_id", "code", name="uq_school_discount_workspace_code"),
        CheckConstraint(
            "percentage > 0 AND percentage <= 100", name="valid_school_discount_percentage"
        ),
        CheckConstraint("max_uses IS NULL OR max_uses > 0", name="valid_school_discount_max_uses"),
    )

    workspace_owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    code: Mapped[str] = mapped_column(String(50))
    percentage: Mapped[Decimal] = mapped_column(Numeric(5, 2))
    expires_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uses_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Student(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint(
            "workspace_owner_id", "national_id", name="uq_student_workspace_national_id"
        ),
        CheckConstraint(GRADE_CHECK, name="valid_student_grade"),
    )

    workspace_owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(200))
    national_id: Mapped[str] = mapped_column(String(20))
    student_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    birth_date: Mapped[date] = mapped_column(Date)
    registration_date: Mapped[date] = mapped_column(
        Date, default=date.today, server_default="CURRENT_DATE"
    )
    first_exam_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    grade: Mapped[str] = mapped_column(String(20), index=True)
    academic_track: Mapped[str | None] = mapped_column(String(100), nullable=True)
    book_voucher_eligible: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    exam_registered: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    guardian_full_name: Mapped[str] = mapped_column(String(200))
    guardian_phone: Mapped[str] = mapped_column(String(32))
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    previous_school: Mapped[str | None] = mapped_column(String(200), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    enrollments: Mapped[list["StudentEnrollment"]] = relationship(
        back_populates="student", cascade="all, delete-orphan", lazy="selectin"
    )


class StudentEnrollment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "student_enrollments"
    __table_args__ = (
        CheckConstraint(
            "subtotal >= 0 AND discount_amount >= 0 AND total_amount >= 0 "
            "AND amount_paid >= 0 AND balance_due >= 0",
            name="nonnegative_enrollment_amounts",
        ),
        CheckConstraint(
            "status IN ('UNPAID','PARTIALLY_PAID','PAID','OVERDUE')", name="valid_enrollment_status"
        ),
    )

    workspace_owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    student_id: Mapped[UUID] = mapped_column(
        ForeignKey("students.id", ondelete="RESTRICT"), index=True
    )
    created_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    discount_code_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("school_discount_codes.id", ondelete="RESTRICT"), nullable=True
    )
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    discount_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, server_default="0")
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, server_default="0")
    balance_due: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(20), default="UNPAID", server_default="UNPAID")
    student: Mapped[Student] = relationship(back_populates="enrollments")
    courses: Mapped[list["EnrollmentCourse"]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan", lazy="selectin"
    )
    payments: Mapped[list["EnrollmentPayment"]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan", lazy="selectin"
    )


class EnrollmentCourse(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "enrollment_courses"
    __table_args__ = (UniqueConstraint("enrollment_id", "course_id", name="uq_enrollment_course"),)

    enrollment_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_enrollments.id", ondelete="CASCADE"), index=True
    )
    course_id: Mapped[UUID] = mapped_column(ForeignKey("school_courses.id", ondelete="RESTRICT"))
    course_name: Mapped[str] = mapped_column(String(200))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    enrollment: Mapped[StudentEnrollment] = relationship(back_populates="courses")


class EnrollmentPayment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "enrollment_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="positive_enrollment_payment_amount"),
        CheckConstraint(
            "method IN ('CASH','BANK_TRANSFER','CHECK','INSTALLMENT')",
            name="valid_enrollment_payment_method",
        ),
        CheckConstraint(
            "status IN ('PENDING','PAID','BOUNCED')", name="valid_enrollment_payment_status"
        ),
        Index("ix_enrollment_payment_due_date", "due_date"),
    )

    workspace_owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    enrollment_id: Mapped[UUID] = mapped_column(
        ForeignKey("student_enrollments.id", ondelete="CASCADE"), index=True
    )
    recorded_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    method: Mapped[str] = mapped_column(String(20))
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tracking_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sayad_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="PENDING", server_default="PENDING")
    enrollment: Mapped[StudentEnrollment] = relationship(back_populates="payments")


class SchoolCost(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "school_costs"
    __table_args__ = (
        UniqueConstraint(
            "workspace_owner_id", "factor_number", name="uq_school_cost_workspace_factor_number"
        ),
        CheckConstraint("amount > 0", name="positive_school_cost_amount"),
        CheckConstraint(
            "payment_method IN ('CASH','CHECK','BANK_TRANSFER')",
            name="valid_school_cost_payment_method",
        ),
    )

    workspace_owner_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    created_by_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    factor_number: Mapped[str] = mapped_column(String(100))
    vendor_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    reason: Mapped[str] = mapped_column(String(300))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    cost_date: Mapped[date] = mapped_column(Date, index=True)
    payment_method: Mapped[str] = mapped_column(String(20))
    check_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    tracking_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(1000), nullable=True)
