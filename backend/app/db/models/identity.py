from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Table,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from backend.app.db.models.audit import AuditEvent

user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Uuid, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Uuid, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column(
        "permission_id",
        Uuid,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(
            "email IS NOT NULL OR phone_number IS NOT NULL",
            name="contact_method_required",
        ),
        CheckConstraint("plan_status IN ('FREE','PRO')", name="valid_plan_status"),
        CheckConstraint(
            "business_category IN ('RETAIL','EDUCATION','ONLINE','SERVICES')",
            name="valid_business_category",
        ),
        Index(
            "uq_users_phone_number_not_null",
            "phone_number",
            unique=True,
            postgresql_where=text("phone_number IS NOT NULL"),
            sqlite_where=text("phone_number IS NOT NULL"),
        ),
    )

    email: Mapped[str | None] = mapped_column(String(320), index=True, nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", nullable=False
    )
    plan_status: Mapped[str] = mapped_column(
        String(20), default="FREE", server_default="FREE", nullable=False
    )
    business_category: Mapped[str] = mapped_column(
        String(20), default="RETAIL", server_default="RETAIL", nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    roles: Mapped[list["Role"]] = relationship(
        secondary=user_roles,
        back_populates="users",
        lazy="selectin",
    )
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="actor")

    @property
    def role_names(self) -> list[str]:
        return sorted(role.name for role in self.roles)

    @property
    def permission_names(self) -> list[str]:
        return sorted({permission.name for role in self.roles for permission in role.permissions})


class Role(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("name", name="uq_roles_name"),)

    name: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    users: Mapped[list[User]] = relationship(
        secondary=user_roles,
        back_populates="roles",
    )
    permissions: Mapped[list["Permission"]] = relationship(
        secondary=role_permissions,
        back_populates="roles",
        lazy="selectin",
    )


class Permission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "permissions"
    __table_args__ = (UniqueConstraint("name", name="uq_permissions_name"),)

    name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    roles: Mapped[list[Role]] = relationship(
        secondary=role_permissions,
        back_populates="permissions",
    )
