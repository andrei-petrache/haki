from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import User
from app.schemas import (
    CalorieTargetIn,
    LoginRequest,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]
bearer_scheme = HTTPBearer(auto_error=False)

# Checked when the email is unknown, so a failed login takes the same time
# whether or not the account exists (prevents probing for registered emails).
DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing")


def unauthorized(detail: str) -> HTTPException:
    """Build a 401 response that tells clients to use a bearer token."""
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    session: SessionDep,
) -> User:
    """Resolve the user from the bearer token, or reject the request with 401."""
    if credentials is None:
        raise unauthorized("Not authenticated")
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise unauthorized("Invalid or expired token")
    user = session.get(User, user_id)
    if user is None:
        raise unauthorized("Invalid or expired token")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post(
    "/signup", status_code=status.HTTP_201_CREATED, response_model=UserResponse
)
def signup(data: SignupRequest, session: SessionDep) -> User:
    """Register a new account."""
    user = User(email=data.email.lower(), password_hash=hash_password(data.password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        ) from None
    session.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, session: SessionDep) -> TokenResponse:
    """Exchange valid credentials for an access token."""
    user = session.scalar(select(User).where(User.email == data.email.lower()))
    stored_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    password_ok = verify_password(data.password, stored_hash)
    if user is None or not password_ok:
        raise unauthorized("Invalid email or password")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse)
def me(current_user: CurrentUser) -> User:
    """Return the currently authenticated user."""
    return current_user


@router.put("/me/target", response_model=UserResponse)
def set_calorie_target(
    data: CalorieTargetIn, current_user: CurrentUser, session: SessionDep
) -> User:
    """Set the current user's daily calorie target, or clear it with null."""
    current_user.daily_calorie_target = data.daily_calorie_target
    session.commit()
    return current_user
