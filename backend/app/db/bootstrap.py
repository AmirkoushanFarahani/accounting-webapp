from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.core.passwords import hash_password
from backend.app.db.database import SessionLocal
from backend.app.db.models import Permission, Role, User

PERMISSIONS = {
    "users:read": "View users",
    "users:manage": "Change user roles and activation status",
    "users:create": "Create users",
    "users:update": "Update users",
    "users:delete": "Deactivate or delete users",
    "accounting:read": "View accounting data",
    "accounting:write": "Create and update accounting data",
    "reports:read": "View financial reports",
    "ml:read": "View machine-learning results",
    "ml:train": "Train machine-learning models",
    "ml:predict": "Run registered machine-learning models",
    "ml:manage": "Register and activate machine-learning models",
    "ml:feedback": "Submit machine-learning prediction feedback",
    "parties:read": "View parties",
    "parties:write": "Create and update parties",
    "products:read": "View products",
    "products:write": "Create and update products",
    "accounts:read": "View the chart of accounts",
    "accounts:write": "Maintain the chart of accounts",
    "journals:read": "View journal entries",
    "journals:write": "Create draft journal entries",
    "journals:post": "Post and reverse journal entries",
    "invoices:read": "View invoices",
    "invoices:write": "Create invoices",
    "invoices:issue": "Issue invoices to the ledger",
    "payments:read": "View payments",
    "payments:write": "Create payments and allocations",
    "payments:post": "Post payments to the ledger",
    "bills:read": "View supplier bills",
    "bills:write": "Create supplier bills",
    "bills:issue": "Issue supplier bills to the ledger",
    "bill_payments:read": "View supplier bill payments",
    "bill_payments:write": "Create supplier bill payments and allocations",
    "bill_payments:post": "Post supplier bill payments to the ledger",
    "periods:read": "View financial periods",
    "periods:manage": "Create and close financial periods",
    "school:read": "View school courses, students, enrolments, and payment plans",
    "school:manage": "Manage school courses, fees, discount codes, and school staff",
    "school:enroll": "Register students and record their payment plans",
    "school:payments": "Update school check and installment payment statuses",
}

ACCOUNTING_READ = {
    "parties:read",
    "products:read",
    "accounts:read",
    "journals:read",
    "invoices:read",
    "payments:read",
    "bills:read",
    "bill_payments:read",
    "periods:read",
}
ACCOUNTING_WRITE = ACCOUNTING_READ | {
    "parties:write",
    "products:write",
    "accounts:write",
    "journals:write",
    "journals:post",
    "invoices:write",
    "invoices:issue",
    "payments:write",
    "payments:post",
    "bills:write",
    "bills:issue",
    "bill_payments:write",
    "bill_payments:post",
    "periods:manage",
}

ROLE_PERMISSIONS = {
    "ADMIN": set(PERMISSIONS),
    "OWNER": {name for name in PERMISSIONS if not name.startswith("users:")},
    "ACCOUNTANT": {
        "accounting:read",
        "accounting:write",
        "reports:read",
        "ml:read",
        "ml:predict",
        "ml:feedback",
    }
    | ACCOUNTING_WRITE,
    "MANAGER": {
        "users:read",
        "accounting:read",
        "reports:read",
        "ml:read",
        "ml:predict",
        "ml:feedback",
    }
    | ACCOUNTING_READ
    | {"school:read", "school:manage", "school:enroll", "school:payments"},
    "EMPLOYEE": {"school:read", "school:enroll", "school:payments"},
    "VIEWER": {"accounting:read", "reports:read", "ml:read"} | ACCOUNTING_READ,
}

ROLE_DESCRIPTIONS = {
    "ADMIN": "Full system administration",
    "OWNER": "Full control of own workspace without user administration",
    "ACCOUNTANT": "Accounting operations",
    "MANAGER": "Management oversight",
    "EMPLOYEE": "School registration employee",
    "VIEWER": "Read-only business access",
}


def seed_rbac(session: Session) -> None:
    """Idempotently create canonical roles, permissions, and their assignments."""
    existing_permissions = {item.name: item for item in session.scalars(select(Permission)).all()}
    for name, description in PERMISSIONS.items():
        existing_permissions.setdefault(name, Permission(name=name, description=description))
    session.add_all(existing_permissions.values())
    session.flush()

    existing_roles = {item.name: item for item in session.scalars(select(Role)).all()}
    for name, description in ROLE_DESCRIPTIONS.items():
        existing_roles.setdefault(name, Role(name=name, description=description))
    session.add_all(existing_roles.values())
    session.flush()

    for role_name, permission_names in ROLE_PERMISSIONS.items():
        existing_roles[role_name].permissions = [
            existing_permissions[name] for name in sorted(permission_names)
        ]


def seed_optional_admin(session: Session) -> None:
    """Create an optional admin only when both credentials are explicitly configured."""
    settings = get_settings()
    email = settings.BOOTSTRAP_ADMIN_EMAIL
    password = settings.BOOTSTRAP_ADMIN_PASSWORD
    if email is None and password is None:
        return
    if not email or password is None:
        raise RuntimeError("Both BOOTSTRAP_ADMIN_EMAIL and BOOTSTRAP_ADMIN_PASSWORD are required")
    normalized_email = str(email).strip().casefold()
    if session.scalar(select(User).where(User.email == normalized_email)) is not None:
        return
    admin_role = session.scalar(select(Role).where(Role.name == "ADMIN"))
    if admin_role is None:
        raise RuntimeError("RBAC roles must be seeded before the optional administrator")
    user = User(
        email=normalized_email,
        password_hash=hash_password(password.get_secret_value()),
        first_name="Development",
        last_name="Administrator",
        roles=[admin_role],
    )
    session.add(user)


def main() -> None:
    with SessionLocal.begin() as session:
        seed_rbac(session)
        seed_optional_admin(session)


if __name__ == "__main__":
    main()
