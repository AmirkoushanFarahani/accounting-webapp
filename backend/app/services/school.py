from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models import (
    DiscountCode,
    EnrollmentCourse,
    EnrollmentPayment,
    SchoolCost,
    SchoolCourse,
    Student,
    StudentEnrollment,
    User,
)
from backend.app.schemas.school import (
    CourseCreate,
    DiscountCodeCreate,
    EnrollmentPaymentCreate,
    PaymentStatusUpdate,
    SchoolCostCreate,
    StudentEnrollmentCreate,
)


class SchoolError(ValueError):
    pass


class SchoolConflictError(SchoolError):
    pass


def workspace_id(actor: User) -> UUID:
    """Return the manager workspace shared by a manager and their employees."""
    return actor.school_manager_id or actor.id


class SchoolService:
    def __init__(self, session: Session, actor: User) -> None:
        self.session = session
        self.actor = actor
        self.workspace_owner_id = workspace_id(actor)

    def list_courses(self, grade: str | None = None) -> list[SchoolCourse]:
        query = select(SchoolCourse).where(
            SchoolCourse.workspace_owner_id == self.workspace_owner_id
        )
        if grade is not None:
            query = query.where(SchoolCourse.grade == grade)
        return list(self.session.scalars(query.order_by(SchoolCourse.grade, SchoolCourse.name)))

    def create_course(self, data: CourseCreate) -> SchoolCourse:
        course = SchoolCourse(workspace_owner_id=self.workspace_owner_id, **data.model_dump())
        self.session.add(course)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise SchoolConflictError(
                "A course with this name already exists for this grade"
            ) from exc
        return course

    def list_discounts(self) -> list[DiscountCode]:
        return list(
            self.session.scalars(
                select(DiscountCode)
                .where(DiscountCode.workspace_owner_id == self.workspace_owner_id)
                .order_by(DiscountCode.code)
            )
        )

    def create_discount(self, data: DiscountCodeCreate) -> DiscountCode:
        code = DiscountCode(workspace_owner_id=self.workspace_owner_id, **data.model_dump())
        self.session.add(code)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise SchoolConflictError("This discount code already exists") from exc
        return code

    def list_students(self) -> list[Student]:
        students = list(
            self.session.scalars(
                select(Student)
                .where(Student.workspace_owner_id == self.workspace_owner_id)
                .order_by(Student.full_name)
            )
        )
        for student in students:
            self._load_student_details(student)
        return students

    def list_costs(
        self, start_date: date | None = None, end_date: date | None = None
    ) -> list[SchoolCost]:
        query = select(SchoolCost).where(SchoolCost.workspace_owner_id == self.workspace_owner_id)
        if start_date is not None:
            query = query.where(SchoolCost.cost_date >= start_date)
        if end_date is not None:
            query = query.where(SchoolCost.cost_date <= end_date)
        return list(
            self.session.scalars(
                query.order_by(SchoolCost.cost_date.desc(), SchoolCost.created_at.desc())
            )
        )

    def create_cost(self, data: SchoolCostCreate) -> SchoolCost:
        cost = SchoolCost(
            workspace_owner_id=self.workspace_owner_id,
            created_by_id=self.actor.id,
            **data.model_dump(),
        )
        self.session.add(cost)
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise SchoolConflictError("A cost factor with this number already exists") from exc
        return cost

    def get_student(self, student_id: UUID) -> Student:
        student = self.session.scalar(
            select(Student).where(
                Student.id == student_id, Student.workspace_owner_id == self.workspace_owner_id
            )
        )
        if student is None:
            raise SchoolError("Student was not found")
        self._load_student_details(student)
        return student

    def create_enrollment(self, data: StudentEnrollmentCreate) -> Student:
        course_ids = list(dict.fromkeys(data.course_ids))
        courses = list(
            self.session.scalars(
                select(SchoolCourse).where(
                    SchoolCourse.workspace_owner_id == self.workspace_owner_id,
                    SchoolCourse.id.in_(course_ids),
                    SchoolCourse.is_active.is_(True),
                )
            )
        )
        if len(courses) != len(course_ids):
            raise SchoolError("One or more selected courses are unavailable")
        if any(course.grade != data.grade for course in courses):
            raise SchoolError("Every selected course must match the student's grade")

        discount = self._resolve_discount(data.discount_code)
        subtotal = sum((course.price for course in courses), Decimal("0"))
        discount_amount = (
            (subtotal * discount.percentage / Decimal("100")).quantize(
                Decimal("0.01"), ROUND_HALF_UP
            )
            if discount is not None
            else Decimal("0")
        )
        total = subtotal - discount_amount
        paid_amount = sum(
            (item.amount for item in data.payments if item.method in {"CASH", "BANK_TRANSFER"}),
            Decimal("0"),
        )
        if paid_amount > total:
            raise SchoolError("Immediate payments cannot exceed the enrollment total")

        student = Student(
            workspace_owner_id=self.workspace_owner_id,
            created_by_id=self.actor.id,
            **data.model_dump(
                exclude={"course_ids", "discount_code", "payments", "registration_date"}
            ),
            registration_date=data.registration_date or date.today(),
        )
        self.session.add(student)
        self.session.flush()
        enrollment = StudentEnrollment(
            workspace_owner_id=self.workspace_owner_id,
            student_id=student.id,
            created_by_id=self.actor.id,
            discount_code_id=discount.id if discount else None,
            subtotal=subtotal,
            discount_amount=discount_amount,
            total_amount=total,
            amount_paid=paid_amount,
            balance_due=total - paid_amount,
            status=self._status(total, paid_amount, data.payments),
        )
        self.session.add(enrollment)
        self.session.flush()
        self.session.add_all(
            [
                EnrollmentCourse(
                    enrollment_id=enrollment.id,
                    course_id=course.id,
                    course_name=course.name,
                    price=course.price,
                )
                for course in courses
            ]
        )
        self.session.add_all(
            [
                EnrollmentPayment(
                    workspace_owner_id=self.workspace_owner_id,
                    enrollment_id=enrollment.id,
                    recorded_by_id=self.actor.id,
                    amount=item.amount,
                    method=item.method,
                    due_date=item.due_date,
                    tracking_code=item.tracking_code,
                    sayad_id=item.sayad_id,
                    status="PAID" if item.method in {"CASH", "BANK_TRANSFER"} else "PENDING",
                )
                for item in data.payments
            ]
        )
        if discount is not None:
            discount.uses_count += 1
        try:
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise SchoolConflictError("A student with this national ID already exists") from exc
        self._load_student_details(student)
        return student

    def update_payment_status(
        self, payment_id: UUID, data: PaymentStatusUpdate
    ) -> EnrollmentPayment:
        payment = self.session.scalar(
            select(EnrollmentPayment).where(
                EnrollmentPayment.id == payment_id,
                EnrollmentPayment.workspace_owner_id == self.workspace_owner_id,
            )
        )
        if payment is None:
            raise SchoolError("Payment was not found")
        if payment.status == "PAID":
            raise SchoolConflictError("A paid payment cannot be changed")
        payment.status = data.status
        enrollment = self.session.get(StudentEnrollment, payment.enrollment_id)
        assert enrollment is not None
        payments = list(
            self.session.scalars(
                select(EnrollmentPayment).where(EnrollmentPayment.enrollment_id == enrollment.id)
            )
        )
        paid = sum((row.amount for row in payments if row.status == "PAID"), Decimal("0"))
        if paid > enrollment.total_amount:
            raise SchoolError("Payments cannot exceed the enrollment total")
        enrollment.amount_paid = paid
        enrollment.balance_due = enrollment.total_amount - paid
        enrollment.status = self._status(enrollment.total_amount, paid, payments)
        self.session.commit()
        return payment

    def _resolve_discount(self, supplied_code: str | None) -> DiscountCode | None:
        if not supplied_code:
            return None
        code = self.session.scalar(
            select(DiscountCode).where(
                DiscountCode.workspace_owner_id == self.workspace_owner_id,
                DiscountCode.code == supplied_code.strip().upper(),
            )
        )
        if code is None or not code.is_active:
            raise SchoolError("The discount code is invalid or inactive")
        if code.expires_on is not None and code.expires_on < date.today():
            raise SchoolError("The discount code has expired")
        if code.max_uses is not None and code.uses_count >= code.max_uses:
            raise SchoolError("The discount code has reached its use limit")
        return code

    @staticmethod
    def _status(
        total: Decimal,
        paid: Decimal,
        payments: list[EnrollmentPaymentCreate] | list[EnrollmentPayment],
    ) -> str:
        if paid >= total:
            return "PAID"
        overdue = any(
            getattr(item, "status", "PENDING") == "PENDING"
            and item.due_date is not None
            and item.due_date < date.today()
            for item in payments
        )
        if overdue:
            return "OVERDUE"
        return "PARTIALLY_PAID" if paid > 0 else "UNPAID"

    def _load_student_details(self, student: Student) -> None:
        # Relationships are select-in loaded; this explicit read gives deterministic
        # newest-first enrolments for the API response.
        student.enrollments = list(
            self.session.scalars(
                select(StudentEnrollment)
                .where(StudentEnrollment.student_id == student.id)
                .order_by(StudentEnrollment.created_at.desc())
            )
        )
