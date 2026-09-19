from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies import require_permission
from backend.app.core.config import Settings, get_settings
from backend.app.db.database import get_db
from backend.app.db.models import (
    DiscountCode,
    EnrollmentPayment,
    SchoolCost,
    SchoolCourse,
    Student,
    User,
)
from backend.app.ml.registry import (
    ModelNotFoundError,
    NoActiveModelError,
    PredictionExecutionError,
    PredictionInputError,
)
from backend.app.schemas.school import (
    CourseCreate,
    CourseRead,
    DiscountCodeCreate,
    DiscountCodeRead,
    EnrollmentCourseRead,
    EnrollmentPaymentRead,
    EnrollmentRead,
    PaymentStatusUpdate,
    SchoolCostCreate,
    SchoolCostList,
    SchoolCostRead,
    StudentEnrollmentCreate,
    StudentRead,
    StudentSegmentationRead,
)
from backend.app.services.ml import MLService
from backend.app.services.school import SchoolConflictError, SchoolError, SchoolService

router = APIRouter(prefix="/school")
SessionDep = Annotated[Session, Depends(get_db)]


def service(session: Session, actor: User) -> SchoolService:
    return SchoolService(session, actor)


def student_read(student: Student) -> StudentRead:
    return StudentRead(
        id=student.id,
        full_name=student.full_name,
        national_id=student.national_id,
        student_phone=student.student_phone,
        birth_date=student.birth_date,
        registration_date=student.registration_date,
        first_exam_date=student.first_exam_date,
        grade=student.grade,
        academic_track=student.academic_track,
        book_voucher_eligible=student.book_voucher_eligible,
        exam_registered=student.exam_registered,
        guardian_full_name=student.guardian_full_name,
        guardian_phone=student.guardian_phone,
        address=student.address,
        previous_school=student.previous_school,
        emergency_contact=student.emergency_contact,
        notes=student.notes,
        created_by_id=student.created_by_id,
        enrollments=[
            EnrollmentRead(
                id=enrollment.id,
                subtotal=enrollment.subtotal,
                discount_amount=enrollment.discount_amount,
                total_amount=enrollment.total_amount,
                amount_paid=enrollment.amount_paid,
                balance_due=enrollment.balance_due,
                status=enrollment.status,
                courses=[EnrollmentCourseRead.model_validate(row) for row in enrollment.courses],
                payments=[EnrollmentPaymentRead.model_validate(row) for row in enrollment.payments],
            )
            for enrollment in student.enrollments
        ],
    )


@router.get("/courses", response_model=list[CourseRead])
def list_courses(
    session: SessionDep,
    actor: Annotated[User, Depends(require_permission("school:read"))],
    grade: str | None = None,
) -> list[SchoolCourse]:
    return service(session, actor).list_courses(grade)


@router.post("/courses", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
def create_course(
    data: CourseCreate,
    session: SessionDep,
    actor: Annotated[User, Depends(require_permission("school:manage"))],
) -> SchoolCourse:
    try:
        return service(session, actor).create_course(data)
    except SchoolConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/discounts", response_model=list[DiscountCodeRead])
def list_discounts(
    session: SessionDep, actor: Annotated[User, Depends(require_permission("school:manage"))]
) -> list[DiscountCode]:
    return service(session, actor).list_discounts()


@router.post("/discounts", response_model=DiscountCodeRead, status_code=status.HTTP_201_CREATED)
def create_discount(
    data: DiscountCodeCreate,
    session: SessionDep,
    actor: Annotated[User, Depends(require_permission("school:manage"))],
) -> DiscountCode:
    try:
        return service(session, actor).create_discount(data)
    except SchoolConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/students", response_model=list[StudentRead])
def list_students(
    session: SessionDep, actor: Annotated[User, Depends(require_permission("school:read"))]
) -> list[StudentRead]:
    return [student_read(student) for student in service(session, actor).list_students()]


@router.get("/students/{student_id}", response_model=StudentRead)
def get_student(
    student_id: UUID,
    session: SessionDep,
    actor: Annotated[User, Depends(require_permission("school:read"))],
) -> StudentRead:
    try:
        return student_read(service(session, actor).get_student(student_id))
    except SchoolError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/costs", response_model=SchoolCostList)
def list_school_costs(
    session: SessionDep,
    actor: Annotated[User, Depends(require_permission("school:manage"))],
    start_date: date | None = None,
    end_date: date | None = None,
) -> SchoolCostList:
    if start_date is not None and end_date is not None and start_date > end_date:
        raise HTTPException(422, "Start date must not be after end date")
    rows = service(session, actor).list_costs(start_date, end_date)
    return SchoolCostList(
        items=[SchoolCostRead.model_validate(row) for row in rows],
        total=sum((row.amount for row in rows), Decimal("0")),
    )


@router.post("/costs", response_model=SchoolCostRead, status_code=status.HTTP_201_CREATED)
def create_school_cost(
    data: SchoolCostCreate,
    session: SessionDep,
    actor: Annotated[User, Depends(require_permission("school:manage"))],
) -> SchoolCost:
    try:
        return service(session, actor).create_cost(data)
    except SchoolConflictError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/students/enroll", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
def enroll_student(
    data: StudentEnrollmentCreate,
    session: SessionDep,
    actor: Annotated[User, Depends(require_permission("school:enroll"))],
) -> StudentRead:
    try:
        return student_read(service(session, actor).create_enrollment(data))
    except SchoolConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except SchoolError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.patch("/payments/{payment_id}", response_model=EnrollmentPaymentRead)
def update_payment(
    payment_id: UUID,
    data: PaymentStatusUpdate,
    session: SessionDep,
    actor: Annotated[User, Depends(require_permission("school:payments"))],
) -> EnrollmentPayment:
    try:
        return service(session, actor).update_payment_status(payment_id, data)
    except SchoolConflictError as exc:
        raise HTTPException(409, str(exc)) from exc
    except SchoolError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post(
    "/accounting/students/{student_id}/segment", response_model=StudentSegmentationRead
)
def segment_student_for_school_accounting(
    student_id: UUID,
    session: SessionDep,
    settings: Annotated[Settings, Depends(get_settings)],
    actor: Annotated[User, Depends(require_permission("school:manage"))],
) -> StudentSegmentationRead:
    # Verify the student belongs to the manager's shared school workspace before ML inference.
    try:
        service(session, actor).get_student(student_id)
        prediction, value = MLService(session, settings).segment_student(
            student_id, date.today(), actor
        )
    except ModelNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (NoActiveModelError, PredictionExecutionError, PredictionInputError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return StudentSegmentationRead(
        student_id=student_id,
        segment=int(value["segment"]),
        behavioral_description=str(value["behavioral_description"]),
        model_version=str(value["model_version"]),
        prediction_timestamp=prediction.predicted_at,
        as_of=date.today(),
    )
