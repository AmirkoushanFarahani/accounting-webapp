import importlib
import logging
from collections.abc import Iterator
from uuid import uuid4

import pytest
import sqlalchemy as sa
from sqlalchemy.engine import Connection

migration = importlib.import_module(
    "backend.alembic.versions.20260903_0011_owner_registration_role"
)


@pytest.fixture
def migration_connection() -> Iterator[Connection]:
    engine = sa.create_engine("sqlite+pysqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table(
        "roles",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, unique=True, nullable=False),
        sa.Column("description", sa.String, nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )
    sa.Table(
        "permissions",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("name", sa.String, unique=True, nullable=False),
    )
    sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("email", sa.String),
        sa.Column("phone_number", sa.String),
    )
    sa.Table(
        "user_roles",
        metadata,
        sa.Column("user_id", sa.String, primary_key=True),
        sa.Column("role_id", sa.String, primary_key=True),
    )
    sa.Table(
        "role_permissions",
        metadata,
        sa.Column("role_id", sa.String, primary_key=True),
        sa.Column("permission_id", sa.String, primary_key=True),
    )
    metadata.create_all(engine)
    with engine.begin() as connection:
        admin_id = str(uuid4())
        connection.execute(
            sa.text(
                "INSERT INTO roles (id, name, description, created_at, updated_at) "
                "VALUES (:id, 'ADMIN', 'Administrator', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": admin_id},
        )
        for name in ("users:read", "users:manage", "invoices:write", "reports:read", "ml:manage"):
            permission_id = str(uuid4())
            connection.execute(
                sa.text("INSERT INTO permissions (id, name) VALUES (:id, :name)"),
                {"id": permission_id, "name": name},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO role_permissions (role_id, permission_id) "
                    "VALUES (:role_id, :permission_id)"
                ),
                {"role_id": admin_id, "permission_id": permission_id},
            )
        for email in ("bootstrap@example.com", "owner-one@example.com", "owner-two@example.com"):
            user_id = str(uuid4())
            connection.execute(
                sa.text(
                    "INSERT INTO users (id, email, phone_number) VALUES (:id, :email, NULL)"
                ),
                {"id": user_id, "email": email},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO user_roles (user_id, role_id) VALUES (:user_id, :role_id)"
                ),
                {"user_id": user_id, "role_id": admin_id},
            )
        yield connection
    engine.dispose()


def _roles_by_email(connection: Connection) -> dict[str, list[str]]:
    rows = connection.execute(
        sa.text(
            "SELECT users.email, roles.name FROM users "
            "JOIN user_roles ON user_roles.user_id = users.id "
            "JOIN roles ON roles.id = user_roles.role_id ORDER BY users.email, roles.name"
        )
    )
    result: dict[str, list[str]] = {}
    for email, role in rows:
        result.setdefault(str(email), []).append(str(role))
    return result


def test_empty_install_does_not_require_bootstrapped_admin(migration_connection):
    connection = migration_connection
    connection.execute(sa.text("DELETE FROM user_roles"))
    connection.execute(sa.text("DELETE FROM users"))
    connection.execute(sa.text("DELETE FROM role_permissions"))
    connection.execute(sa.text("DELETE FROM roles"))
    owner_id = migration._ensure_owner_role(connection)
    assert migration._migrate_admin_holders(connection, owner_id, None) == 0
    assert connection.execute(sa.text("SELECT COUNT(*) FROM users")).scalar_one() == 0


def test_missing_admin_with_existing_users_still_fails_closed(migration_connection):
    connection = migration_connection
    connection.execute(sa.text("DELETE FROM user_roles"))
    connection.execute(sa.text("DELETE FROM role_permissions"))
    connection.execute(sa.text("DELETE FROM roles"))
    owner_id = migration._ensure_owner_role(connection)
    with pytest.raises(RuntimeError, match="ADMIN role must exist"):
        migration._migrate_admin_holders(connection, owner_id, None)


def test_migration_keeps_bootstrap_admin_and_downgrades_other_admins(
    migration_connection: Connection,
) -> None:
    owner_id = migration._ensure_owner_role(migration_connection)
    affected = migration._migrate_admin_holders(
        migration_connection, owner_id, "BOOTSTRAP@EXAMPLE.COM"
    )

    assert affected == 2
    assert _roles_by_email(migration_connection) == {
        "bootstrap@example.com": ["ADMIN"],
        "owner-one@example.com": ["OWNER"],
        "owner-two@example.com": ["OWNER"],
    }
    owner_permissions = set(
        migration_connection.scalars(
            sa.text(
                "SELECT permissions.name FROM permissions "
                "JOIN role_permissions ON role_permissions.permission_id = permissions.id "
                "WHERE role_permissions.role_id = :role_id"
            ),
            {"role_id": owner_id},
        )
    )
    assert owner_permissions == {"invoices:write", "reports:read", "ml:manage"}
    admin_permissions = set(
        migration_connection.scalars(
            sa.text(
                "SELECT permissions.name FROM permissions "
                "JOIN role_permissions ON role_permissions.permission_id = permissions.id "
                "JOIN roles ON roles.id = role_permissions.role_id "
                "WHERE roles.name = 'ADMIN'"
            )
        )
    )
    assert {"users:read", "users:manage"} <= admin_permissions


def test_migration_without_bootstrap_email_warns_and_changes_no_admins(
    migration_connection: Connection, caplog: pytest.LogCaptureFixture
) -> None:
    owner_id = migration._ensure_owner_role(migration_connection)
    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        affected = migration._migrate_admin_holders(migration_connection, owner_id, None)

    assert affected == 0
    assert _roles_by_email(migration_connection) == {
        "bootstrap@example.com": ["ADMIN"],
        "owner-one@example.com": ["ADMIN"],
        "owner-two@example.com": ["ADMIN"],
    }
    assert "no ADMIN users were changed" in caplog.text
    assert "bootstrap@example.com" in caplog.text
    assert "owner-one@example.com" in caplog.text
    assert "owner-two@example.com" in caplog.text
