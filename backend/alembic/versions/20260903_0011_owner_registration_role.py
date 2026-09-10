"""Separate workspace ownership from platform administration.

Revision ID: 20260903_0011
Revises: 20260901_0010
"""

import logging
import os
from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from alembic import op

revision: str = "20260903_0011"
down_revision: str | None = "20260901_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LOGGER = logging.getLogger("alembic.runtime.migration")
OWNER_DESCRIPTION = "Full control of own workspace without user administration"


def _role_id(connection: Connection, name: str) -> object | None:
    return connection.execute(
        sa.text("SELECT id FROM roles WHERE name = :name"), {"name": name}
    ).scalar_one_or_none()


def _ensure_owner_role(connection: Connection) -> object:
    owner_id = _role_id(connection, "OWNER")
    if owner_id is None:
        owner_id = str(uuid4())
        connection.execute(
            sa.text(
                "INSERT INTO roles (id, name, description, created_at, updated_at) "
                "VALUES (:id, 'OWNER', :description, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"id": owner_id, "description": OWNER_DESCRIPTION},
        )
    else:
        connection.execute(
            sa.text("UPDATE roles SET description = :description WHERE id = :id"),
            {"id": owner_id, "description": OWNER_DESCRIPTION},
        )

    connection.execute(
        sa.text("DELETE FROM role_permissions WHERE role_id = :owner_id"),
        {"owner_id": owner_id},
    )
    connection.execute(
        sa.text(
            "INSERT INTO role_permissions (role_id, permission_id) "
            "SELECT :owner_id, id FROM permissions WHERE name NOT LIKE 'users:%'"
        ),
        {"owner_id": owner_id},
    )
    return owner_id


def _admin_holders(connection: Connection, admin_id: object) -> list[dict[str, object]]:
    return [
        dict(row)
        for row in connection.execute(
            sa.text(
                "SELECT users.id, users.email, users.phone_number "
                "FROM users JOIN user_roles ON user_roles.user_id = users.id "
                "WHERE user_roles.role_id = :admin_id ORDER BY users.email, users.id"
            ),
            {"admin_id": admin_id},
        ).mappings()
    ]


def _admin_label(row: dict[str, object]) -> str:
    return str(row.get("email") or row.get("phone_number") or row["id"])


def _migrate_admin_holders(
    connection: Connection, owner_id: object, bootstrap_admin_email: str | None
) -> int:
    admin_id = _role_id(connection, "ADMIN")
    if admin_id is None:
        # On an empty installation migrations run before role bootstrap. There are
        # no holders to reclassify. Still fail closed for an inconsistent populated DB.
        if connection.execute(sa.text("SELECT COUNT(*) FROM users")).scalar_one() == 0:
            return 0
        raise RuntimeError("The ADMIN role must exist before adding OWNER")
    admins = _admin_holders(connection, admin_id)
    if not admins:
        return 0

    normalized_email = (bootstrap_admin_email or "").strip().casefold()
    if not normalized_email:
        LOGGER.warning(
            "BOOTSTRAP_ADMIN_EMAIL is not set; no ADMIN users were changed. "
            "Review current ADMIN holders manually: %s",
            ", ".join(_admin_label(row) for row in admins),
        )
        return 0

    bootstrap_admin = next(
        (
            row
            for row in admins
            if isinstance(row.get("email"), str)
            and str(row["email"]).strip().casefold() == normalized_email
        ),
        None,
    )
    if bootstrap_admin is None:
        raise RuntimeError(
            "BOOTSTRAP_ADMIN_EMAIL does not identify a current ADMIN; "
            "no administrator roles were changed"
        )

    affected = 0
    for row in admins:
        if row["id"] == bootstrap_admin["id"]:
            continue
        connection.execute(
            sa.text(
                "INSERT INTO user_roles (user_id, role_id) "
                "SELECT :user_id, :owner_id WHERE NOT EXISTS ("
                "SELECT 1 FROM user_roles WHERE user_id = :user_id AND role_id = :owner_id)"
            ),
            {"user_id": row["id"], "owner_id": owner_id},
        )
        connection.execute(
            sa.text(
                "DELETE FROM user_roles WHERE user_id = :user_id AND role_id = :admin_id"
            ),
            {"user_id": row["id"], "admin_id": admin_id},
        )
        affected += 1
    return affected


def upgrade() -> None:
    connection = op.get_bind()
    owner_id = _ensure_owner_role(connection)
    affected = _migrate_admin_holders(
        connection, owner_id, os.environ.get("BOOTSTRAP_ADMIN_EMAIL")
    )
    if affected:
        LOGGER.info("Changed %d non-bootstrap ADMIN user(s) to OWNER", affected)


def downgrade() -> None:
    connection = op.get_bind()
    owner_id = _role_id(connection, "OWNER")
    if owner_id is None:
        return
    admin_id = _role_id(connection, "ADMIN")
    if admin_id is None:
        raise RuntimeError("Cannot remove OWNER because the ADMIN role is missing")
    connection.execute(
        sa.text(
            "INSERT INTO user_roles (user_id, role_id) "
            "SELECT owner_users.user_id, :admin_id FROM user_roles AS owner_users "
            "WHERE owner_users.role_id = :owner_id AND NOT EXISTS ("
            "SELECT 1 FROM user_roles AS admin_users "
            "WHERE admin_users.user_id = owner_users.user_id "
            "AND admin_users.role_id = :admin_id)"
        ),
        {"owner_id": owner_id, "admin_id": admin_id},
    )
    connection.execute(
        sa.text("DELETE FROM user_roles WHERE role_id = :owner_id"),
        {"owner_id": owner_id},
    )
    connection.execute(
        sa.text("DELETE FROM role_permissions WHERE role_id = :owner_id"),
        {"owner_id": owner_id},
    )
    connection.execute(
        sa.text("DELETE FROM roles WHERE id = :owner_id"), {"owner_id": owner_id}
    )
