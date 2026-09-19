from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SchoolGrade = Literal[
    "GRADE_1",
    "GRADE_2",
    "GRADE_3",
    "GRADE_4",
    "GRADE_5",
    "GRADE_6",
    "GRADE_7",
    "GRADE_8",
    "GRADE_9",
    "GRADE_10",
    "GRADE_11",
    "GRADE_12",
]
PaymentMethod = Literal["CASH", "BANK_TRANSFER", "CHECK", "INSTALLMENT"]
SchoolCostPaymentMethod = Literal["CASH", "BANK_TRANSFER", "CHECK"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CourseCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    instructor_name: str | None = Field(default=None, max_length=200)
    grade: SchoolGrade
    price: Decimal = Field(ge=0, max_digits=18, decimal_places=2)


class CourseRead(ORMModel):
    id: UUID
    name: str
    instructor_name: str | None
    grade: SchoolGrade
    price: Decimal
    is_active: bool


class DiscountCodeCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    code: str = Field(min_length=2, max_length=50)
    percentage: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)
    expires_on: date | None = None
    max_uses: int | None = Field(default=None, gt=0)

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        return value.upper()


class DiscountCodeRead(ORMModel):
    id: UUID
    code: str
    percentage: Decimal
    expires_on: date | None
    max_uses: int | None
    uses_count: int
    is_active: bool


class EnrollmentPaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    method: PaymentMethod
    due_date: date | None = None
    tracking_code: str | None = Field(default=None, max_length=100)
    sayad_id: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def scheduled_payments_require_due_date(self) -> "EnrollmentPaymentCreate":
        if self.method in {"CHECK", "INSTALLMENT"} and self.due_date is None:
            raise ValueError("A check or installment payment requires a due date")
        return self


class StudentEnrollmentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    full_name: str = Field(min_length=3, max_length=200)
    national_id: str = Field(min_length=5, max_length=20)
    student_phone: str | None = Field(default=None, max_length=32)
    birth_date: date
    registration_date: date | None = None
    first_exam_date: date | None = None
    grade: SchoolGrade
    academic_track: str | None = Field(default=None, max_length=100)
    book_voucher_eligible: bool = False
    exam_registered: bool = False
    guardian_full_name: str = Field(min_length=3, max_length=200)
    guardian_phone: str = Field(min_length=7, max_length=32)
    address: str | None = Field(default=None, max_length=500)
    previous_school: str | None = Field(default=None, max_length=200)
    emergency_contact: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=1000)
    course_ids: list[UUID] = Field(min_length=1)
    discount_code: str | None = Field(default=None, max_length=50)
    payments: list[EnrollmentPaymentCreate] = Field(default_factory=list)


class EnrollmentCourseRead(ORMModel):
    course_id: UUID
    course_name: str
    price: Decimal


class EnrollmentPaymentRead(ORMModel):
    id: UUID
    amount: Decimal
    method: PaymentMethod
    due_date: date | None
    tracking_code: str | None
    sayad_id: str | None
    status: Literal["PENDING", "PAID", "BOUNCED"]


class EnrollmentRead(ORMModel):
    id: UUID
    subtotal: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    status: Literal["UNPAID", "PARTIALLY_PAID", "PAID", "OVERDUE"]
    courses: list[EnrollmentCourseRead]
    payments: list[EnrollmentPaymentRead]


class StudentRead(ORMModel):
    id: UUID
    full_name: str
    national_id: str
    student_phone: str | None
    birth_date: date
    registration_date: date
    first_exam_date: date | None
    grade: SchoolGrade
    academic_track: str | None
    book_voucher_eligible: bool
    exam_registered: bool
    guardian_full_name: str
    guardian_phone: str
    address: str | None
    previous_school: str | None
    emergency_contact: str | None
    notes: str | None
    created_by_id: UUID
    enrollments: list[EnrollmentRead]


class PaymentStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["PAID", "BOUNCED"]


class StudentSegmentationRead(BaseModel):
    student_id: UUID
    segment: int
    behavioral_description: str
    model_version: str
    prediction_timestamp: datetime
    as_of: date


class SchoolCostCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    factor_number: str = Field(min_length=1, max_length=100)
    vendor_name: str | None = Field(default=None, max_length=200)
    reason: str = Field(min_length=1, max_length=300)
    amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)
    cost_date: date
    payment_method: SchoolCostPaymentMethod
    check_due_date: date | None = None
    tracking_code: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def check_requires_due_date(self) -> "SchoolCostCreate":
        if self.payment_method == "CHECK" and self.check_due_date is None:
            raise ValueError("A check cost requires a due date")
        return self


class SchoolCostRead(ORMModel):
    id: UUID
    factor_number: str
    vendor_name: str | None
    reason: str
    amount: Decimal
    cost_date: date
    payment_method: SchoolCostPaymentMethod
    check_due_date: date | None
    tracking_code: str | None
    notes: str | None


class SchoolCostList(BaseModel):
    items: list[SchoolCostRead]
    total: Decimal
