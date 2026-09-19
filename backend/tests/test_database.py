from backend.app.db.database import SessionLocal, engine
from backend.app.db.models import Permission, Role
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError


def test_stage_two_tables_and_constraints_exist() -> None:
    inspector = inspect(engine)
    assert {
        "users",
        "roles",
        "permissions",
        "user_roles",
        "role_permissions",
        "audit_events",
        "ml_model_versions",
        "ml_predictions",
        "ml_prediction_feedback",
    } <= set(inspector.get_table_names())
    assert any(
        item["name"] == "uq_users_email" for item in inspector.get_unique_constraints("users")
    )
    assert any(
        item["name"] == "uq_users_phone_number_not_null" and item["unique"]
        for item in inspector.get_indexes("users")
    )
    assert any(
        item["name"] == "ck_users_valid_plan_status"
        for item in inspector.get_check_constraints("users")
    )
    assert any(
        item["name"] == "ck_users_contact_method_required"
        for item in inspector.get_check_constraints("users")
    )
    assert "invoice_checks" in inspector.get_table_names()
    assert any(
        item["name"] == "uq_invoice_checks_sayad_id"
        for item in inspector.get_unique_constraints("invoice_checks")
    )
    invoice_check_sayad = next(
        column for column in inspector.get_columns("invoice_checks")
        if column["name"] == "sayad_id"
    )
    assert invoice_check_sayad["nullable"]
    assert {"sayad_id", "customer_credit_account_id"} <= {
        column["name"] for column in inspector.get_columns("payments")
    }
    assert "sayad_id" in {
        column["name"] for column in inspector.get_columns("bill_payments")
    }
    posting_role_constraint = next(
        item
        for item in inspector.get_check_constraints("accounts")
        if item["name"] == "ck_accounts_valid_posting_role"
    )
    assert "CUSTOMER_CREDIT" in posting_role_constraint["sqltext"]


def test_rbac_bootstrap_is_idempotent() -> None:
    from backend.app.db.bootstrap import PERMISSIONS, seed_rbac

    with SessionLocal.begin() as session:
        seed_rbac(session)
        seed_rbac(session)
        roles = {role.name: role for role in session.scalars(select(Role)).all()}
        assert set(roles) == {"ADMIN", "OWNER", "ACCOUNTANT", "MANAGER", "EMPLOYEE", "VIEWER"}
        assert len(session.scalars(select(Permission)).all()) == len(PERMISSIONS)
        assert {permission.name for permission in roles["OWNER"].permissions} == {
            name for name in PERMISSIONS if not name.startswith("users:")
        }


def test_role_name_database_uniqueness() -> None:
    with SessionLocal() as session:
        session.add(Role(name="VIEWER", description="duplicate"))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
        else:
            raise AssertionError("database accepted a duplicate role")
