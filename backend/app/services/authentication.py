from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.core.passwords import hash_password, verify_password
from backend.app.core.tokens import create_access_token
from backend.app.db.models import User
from backend.app.repositories.audit import AuditRepository
from backend.app.repositories.roles import RoleRepository
from backend.app.repositories.users import UserRepository
from backend.app.schemas.auth import BusinessProfileUpdate, LoginRequest, RegisterRequest

PUBLIC_REGISTRATION_ROLE = "OWNER"


class DuplicateEmailError(ValueError):
    pass


class AuthenticationError(ValueError):
    pass


def normalize_email(email: str) -> str:
    return email.strip().casefold()


class AuthenticationService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.roles = RoleRepository(session)
        self.audit = AuditRepository(session)

    def register(self, data: RegisterRequest) -> User:
        email = normalize_email(str(data.email)) if data.email is not None else None
        if email is not None and self.users.get_by_email(email) is not None:
            self.audit.record(
                action="identity.registration",
                resource_type="user",
                success=False,
                details={"email": email, "reason": "duplicate"},
            )
            self.session.commit()
            raise DuplicateEmailError("An account with this email already exists")
        if data.phone_number is not None and self.users.get_by_phone_number(data.phone_number):
            self.audit.record(
                action="identity.registration",
                resource_type="user",
                success=False,
                details={"reason": "duplicate_phone_number"},
            )
            self.session.commit()
            raise DuplicateEmailError("An account with this phone number already exists")

        default_role = self.roles.get_by_name(PUBLIC_REGISTRATION_ROLE)
        if default_role is None:
            raise RuntimeError("Default registration role has not been bootstrapped")
        user = User(
            email=email,
            phone_number=data.phone_number,
            business_category=data.business_category,
            password_hash=hash_password(data.password),
            first_name=data.first_name.strip(),
            last_name=data.last_name.strip(),
            roles=[default_role],
        )
        self.users.add(user)
        try:
            self.session.flush()
            self.audit.record(
                action="identity.registration",
                resource_type="user",
                resource_id=str(user.id),
                actor_id=user.id,
                success=True,
            )
            self.session.commit()
        except IntegrityError as exc:
            self.session.rollback()
            raise DuplicateEmailError(
                "An account with this email or phone number already exists"
            ) from exc
        return user

    def update_business_profile(self, user: User, data: BusinessProfileUpdate) -> User:
        previous = user.business_category
        user.business_category = data.business_category
        self.audit.record(
            action="identity.business_profile.updated",
            resource_type="user",
            resource_id=str(user.id),
            actor_id=user.id,
            success=True,
            details={"previous_category": previous, "business_category": data.business_category},
        )
        self.session.commit()
        return user

    def login(self, data: LoginRequest) -> tuple[User, str]:
        if data.email is not None:
            identifier = normalize_email(str(data.email))
            identifier_type = "email"
            user = self.users.get_by_email(identifier)
        else:
            assert data.phone_number is not None
            identifier = data.phone_number
            identifier_type = "phone_number"
            user = self.users.get_by_phone_number(identifier)
        if user is None:
            hash_password(data.password)
            self._record_failed_login(identifier_type=identifier_type, identifier=identifier)
            raise AuthenticationError("Invalid email, phone number, or password")
        if not user.is_active or not verify_password(data.password, user.password_hash):
            self._record_failed_login(
                identifier_type=identifier_type, identifier=identifier, actor=user
            )
            raise AuthenticationError("Invalid email, phone number, or password")

        user.last_login_at = datetime.now(UTC)
        self.audit.record(
            action="identity.login",
            resource_type="user",
            resource_id=str(user.id),
            actor_id=user.id,
            success=True,
        )
        self.session.commit()
        return user, create_access_token(user.id)

    def _record_failed_login(
        self, *, identifier_type: str, identifier: str, actor: User | None = None
    ) -> None:
        self.audit.record(
            action="identity.login",
            resource_type="user",
            resource_id=str(actor.id) if actor else None,
            actor_id=actor.id if actor else None,
            success=False,
            details={identifier_type: identifier, "reason": "credentials_rejected"},
        )
        self.session.commit()
