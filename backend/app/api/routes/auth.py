from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from backend.app.api.dependencies import require_authenticated_user
from backend.app.db.database import get_db
from backend.app.db.models import User
from backend.app.schemas.auth import (
    BusinessProfileUpdate,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserRead,
)
from backend.app.services.authentication import (
    AuthenticationError,
    AuthenticationService,
    DuplicateEmailError,
)

router = APIRouter(prefix="/auth")


def enforce_auth_rate_limit(request: Request, action: str) -> None:
    client_host = request.client.host if request.client is not None else "unknown"
    retry_after = request.app.state.auth_rate_limiter.check(f"{action}:{client_host}")
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many authentication attempts. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(
    data: RegisterRequest,
    session: Annotated[Session, Depends(get_db)],
    request: Request,
) -> User:
    enforce_auth_rate_limit(request, "register")
    try:
        return AuthenticationService(session).register(data)
    except DuplicateEmailError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/login", response_model=TokenResponse)
def login(
    data: LoginRequest,
    session: Annotated[Session, Depends(get_db)],
    request: Request,
) -> TokenResponse:
    enforce_auth_rate_limit(request, "login")
    try:
        _, token = AuthenticationService(session).login(data)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email, phone number, or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserRead)
def me(current_user: Annotated[User, Depends(require_authenticated_user)]) -> User:
    return current_user


@router.patch("/me/business-profile", response_model=UserRead)
def update_business_profile(
    data: BusinessProfileUpdate,
    current_user: Annotated[User, Depends(require_authenticated_user)],
    session: Annotated[Session, Depends(get_db)],
) -> User:
    return AuthenticationService(session).update_business_profile(current_user, data)
