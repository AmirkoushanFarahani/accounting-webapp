from datetime import date

from backend.app.core.passwords import hash_password
from backend.app.db.database import SessionLocal
from backend.app.db.models import Role, User
from fastapi.testclient import TestClient
from sqlalchemy import select

PASSWORD = "school-demo-password-123"


def login_headers(client: TestClient, email: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def school_users(client: TestClient) -> tuple[dict[str, str], dict[str, str]]:
    with SessionLocal.begin() as session:
        manager_role = session.scalar(select(Role).where(Role.name == "MANAGER"))
        employee_role = session.scalar(select(Role).where(Role.name == "EMPLOYEE"))
        assert manager_role is not None and employee_role is not None
        manager = User(
            email="manager@example.com",
            password_hash=hash_password(PASSWORD),
            first_name="School",
            last_name="Manager",
            business_category="EDUCATION",
            roles=[manager_role],
        )
        session.add(manager)
        session.flush()
        session.add(
            User(
                email="employee@example.com",
                password_hash=hash_password(PASSWORD),
                first_name="School",
                last_name="Employee",
                business_category="EDUCATION",
                school_manager_id=manager.id,
                roles=[employee_role],
            )
        )
    return (
        login_headers(client, "manager@example.com"),
        login_headers(client, "employee@example.com"),
    )


def test_manager_courses_employee_enrollment_and_shared_student_view(client: TestClient) -> None:
    manager, employee = school_users(client)
    course = client.post(
        "/api/v1/school/courses",
        headers=manager,
        json={"name": "ریاضی تقویتی", "grade": "GRADE_7", "price": "1200000"},
    )
    assert course.status_code == 201
    assert client.post(
        "/api/v1/school/courses",
        headers=employee,
        json={"name": "مجاز نیست", "grade": "GRADE_7", "price": "1"},
    ).status_code == 403
    discount = client.post(
        "/api/v1/school/discounts",
        headers=manager,
        json={"code": "WELCOME10", "percentage": "10"},
    )
    assert discount.status_code == 201
    enrolled = client.post(
        "/api/v1/school/students/enroll",
        headers=employee,
        json={
            "full_name": "دانش‌آموز آزمایشی",
            "national_id": "1234567890",
            "birth_date": "2013-01-01",
            "grade": "GRADE_7",
            "guardian_full_name": "ولی آزمایشی",
            "guardian_phone": "09120000000",
            "course_ids": [course.json()["id"]],
            "discount_code": "welcome10",
            "payments": [
                {"amount": "200000", "method": "CASH"},
                {"amount": "500000", "method": "INSTALLMENT", "due_date": "2030-01-01"},
            ],
        },
    )
    assert enrolled.status_code == 201
    enrollment = enrolled.json()["enrollments"][0]
    assert enrollment["subtotal"] == "1200000.00"
    assert enrollment["discount_amount"] == "120000.00"
    assert enrollment["total_amount"] == "1080000.00"
    assert enrollment["amount_paid"] == "200000"
    assert enrollment["status"] == "PARTIALLY_PAID"
    students = client.get("/api/v1/school/students", headers=manager).json()
    assert students[0]["full_name"] == enrolled.json()["full_name"]
    installment = next(item for item in enrollment["payments"] if item["method"] == "INSTALLMENT")
    cleared = client.patch(
        f"/api/v1/school/payments/{installment['id']}", headers=employee, json={"status": "PAID"}
    )
    assert cleared.status_code == 200


def test_employee_cannot_choose_course_from_another_grade(client: TestClient) -> None:
    manager, employee = school_users(client)
    course = client.post(
        "/api/v1/school/courses",
        headers=manager,
        json={"name": "علوم", "grade": "GRADE_8", "price": "100000"},
    ).json()
    response = client.post(
        "/api/v1/school/students/enroll",
        headers=employee,
        json={
            "full_name": "دانش‌آموز دوم",
            "national_id": "1234567891",
            "birth_date": str(date(2014, 1, 1)),
            "grade": "GRADE_7",
            "guardian_full_name": "ولی دوم",
            "guardian_phone": "09120000001",
            "course_ids": [course["id"]],
        },
    )
    assert response.status_code == 422


def test_check_cost_requires_and_returns_a_due_date(client: TestClient) -> None:
    manager, _ = school_users(client)
    missing_date = client.post(
        "/api/v1/school/costs",
        headers=manager,
        json={
            "factor_number": "CHECK-COST-001",
            "reason": "Utility payment",
            "amount": "500000",
            "cost_date": "2030-01-01",
            "payment_method": "CHECK",
        },
    )
    assert missing_date.status_code == 422

    created = client.post(
        "/api/v1/school/costs",
        headers=manager,
        json={
            "factor_number": "CHECK-COST-001",
            "reason": "Utility payment",
            "amount": "500000",
            "cost_date": "2030-01-01",
            "payment_method": "CHECK",
            "check_due_date": "2030-02-01",
        },
    )
    assert created.status_code == 201
    assert created.json()["check_due_date"] == "2030-02-01"
