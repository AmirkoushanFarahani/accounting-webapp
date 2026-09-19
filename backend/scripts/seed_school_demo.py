"""Create a clearly labelled local school demo workspace.

Run with ``DEMO_SCHOOL_PASSWORD`` set.  The script is idempotent: it creates
missing demo records but never deletes or alters unrelated user data.
"""

import os
from datetime import date
from decimal import Decimal

from backend.app.core.passwords import hash_password
from backend.app.db.bootstrap import seed_rbac
from backend.app.db.database import SessionLocal
from backend.app.db.models import (
    DiscountCode,
    EnrollmentCourse,
    EnrollmentPayment,
    Role,
    SchoolCourse,
    Student,
    StudentEnrollment,
    User,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

MANAGER_EMAIL = "school.manager@example.com"
EMPLOYEE_EMAIL = "school.employee@example.com"

COURSES = (
    ("ریاضی تقویتی", "GRADE_1", "1800000"),
    ("فارسی و نگارش", "GRADE_2", "1600000"),
    ("علوم تجربی", "GRADE_3", "1700000"),
    ("ریاضی پیشرفته", "GRADE_4", "2200000"),
    ("زبان انگلیسی", "GRADE_5", "2000000"),
    ("آمادگی آزمون", "GRADE_6", "2400000"),
    ("ریاضی هفتم", "GRADE_7", "2500000"),
    ("علوم هشتم", "GRADE_8", "2600000"),
    ("ادبیات نهم", "GRADE_9", "2300000"),
    ("فیزیک دهم", "GRADE_10", "3000000"),
    ("شیمی یازدهم", "GRADE_11", "3200000"),
    ("جمع‌بندی کنکور", "GRADE_12", "4500000"),
)


def _user(
    session: Session, *, email: str, first_name: str, last_name: str, role: Role, password: str,
) -> User:
    user = session.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            password_hash=hash_password(password),
            first_name=first_name,
            last_name=last_name,
            business_category="EDUCATION",
            roles=[role],
        )
        session.add(user)
        session.flush()
    return user


def main() -> None:
    password = os.environ.get("DEMO_SCHOOL_PASSWORD")
    if not password:
        raise RuntimeError("Set DEMO_SCHOOL_PASSWORD before seeding local demo accounts.")

    with SessionLocal.begin() as session:
        seed_rbac(session)
        manager_role = session.scalar(select(Role).where(Role.name == "MANAGER"))
        employee_role = session.scalar(select(Role).where(Role.name == "EMPLOYEE"))
        if manager_role is None or employee_role is None:
            raise RuntimeError("School roles could not be initialized.")

        manager = _user(
            session,
            email=MANAGER_EMAIL,
            first_name="مدیر",
            last_name="آموزشگاه نمونه",
            role=manager_role,
            password=password,
        )
        employee = _user(
            session,
            email=EMPLOYEE_EMAIL,
            first_name="کارمند",
            last_name="ثبت‌نام نمونه",
            role=employee_role,
            password=password,
        )
        employee.school_manager_id = manager.id
        employee.roles = [employee_role]

        courses: dict[str, SchoolCourse] = {}
        for name, grade, price in COURSES:
            course = session.scalar(
                select(SchoolCourse).where(
                    SchoolCourse.workspace_owner_id == manager.id,
                    SchoolCourse.name == name,
                    SchoolCourse.grade == grade,
                )
            )
            if course is None:
                course = SchoolCourse(
                    workspace_owner_id=manager.id,
                    name=name,
                    grade=grade,
                    price=Decimal(price),
                )
                session.add(course)
                session.flush()
            courses[grade] = course

        discount = session.scalar(
            select(DiscountCode).where(
                DiscountCode.workspace_owner_id == manager.id,
                DiscountCode.code == "SCHOOL10",
            )
        )
        if discount is None:
            session.add(
                DiscountCode(
                    workspace_owner_id=manager.id,
                    code="SCHOOL10",
                    percentage=Decimal("10"),
                    max_uses=100,
                )
            )

        _seed_student(
            session,
            manager=manager,
            employee=employee,
            course=courses["GRADE_7"],
            full_name="آرین رضایی (نمونه)",
            national_id="9000000001",
            guardian="رضا رضایی",
            phone="09120000001",
            payment_method="CHECK",
            payment_status="PENDING",
            payment_amount=Decimal("2500000"),
        )
        _seed_student(
            session,
            manager=manager,
            employee=employee,
            course=courses["GRADE_10"],
            full_name="سارا احمدی (نمونه)",
            national_id="9000000002",
            guardian="مریم احمدی",
            phone="09120000002",
            payment_method="INSTALLMENT",
            payment_status="PENDING",
            payment_amount=Decimal("1500000"),
        )
        for number, grade, name in (
            (3, "GRADE_1", "نیلا کریمی (نمونه)"), (4, "GRADE_4", "پارسا محمدی (نمونه)"),
            (5, "GRADE_8", "هلیا موسوی (نمونه)"), (6, "GRADE_12", "امیرحسین حسینی (نمونه)"),
        ):
            _seed_student(
                session, manager=manager, employee=employee, course=courses[grade], full_name=name,
                national_id=f"900000000{number}", guardian=f"ولی {name}",
                phone=f"0912000000{number}", payment_method="CASH", payment_status="PAID",
                payment_amount=courses[grade].price,
            )

    print(f"Local demo accounts are ready: {MANAGER_EMAIL} and {EMPLOYEE_EMAIL}")


def _seed_student(
    session: Session,
    *,
    manager: User,
    employee: User,
    course: SchoolCourse,
    full_name: str,
    national_id: str,
    guardian: str,
    phone: str,
    payment_method: str,
    payment_status: str,
    payment_amount: Decimal,
) -> None:
    student = session.scalar(
        select(Student).where(
            Student.workspace_owner_id == manager.id, Student.national_id == national_id
        )
    )
    if student is not None:
        return
    student = Student(
        workspace_owner_id=manager.id,
        created_by_id=employee.id,
        full_name=full_name,
        national_id=national_id,
        birth_date=date(2012, 1, 1),
        grade=course.grade,
        guardian_full_name=guardian,
        guardian_phone=phone,
    )
    session.add(student)
    session.flush()
    enrollment = StudentEnrollment(
        workspace_owner_id=manager.id,
        student_id=student.id,
        created_by_id=employee.id,
        subtotal=course.price,
        discount_amount=Decimal("0"),
        total_amount=course.price,
        amount_paid=Decimal("0"),
        balance_due=course.price,
        status="UNPAID",
    )
    session.add(enrollment)
    session.flush()
    session.add(
        EnrollmentCourse(
            enrollment_id=enrollment.id,
            course_id=course.id,
            course_name=course.name,
            price=course.price,
        )
    )
    session.add(
        EnrollmentPayment(
            workspace_owner_id=manager.id,
            enrollment_id=enrollment.id,
            recorded_by_id=employee.id,
            amount=payment_amount,
            method=payment_method,
            due_date=date(2026, 10, 1),
            sayad_id="DEMO-SAYAD-001" if payment_method == "CHECK" else None,
            status=payment_status,
        )
    )


if __name__ == "__main__":
    main()
