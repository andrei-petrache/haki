from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_session
from app.errors import ApiError, ErrorCode
from app.models import Erasure, User
from app.schemas import (
    AccountDeleteIn,
    AccountSettingsIn,
    CalorieTargetIn,
    LoginRequest,
    PasswordChangeIn,
    SignupRequest,
    TokenResponse,
    UserResponse,
)
from app.security import (
    create_access_token,
    decode_token,
    hash_password,
    password_stamp,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

SessionDep = Annotated[Session, Depends(get_session)]
bearer_scheme = HTTPBearer(auto_error=False)

# Checked when the email is unknown, so a failed login takes the same time
# whether or not the account exists (prevents probing for registered emails).
DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-timing")


def unauthorized(code: ErrorCode) -> ApiError:
    """Build a 401 response that tells clients to use a bearer token."""
    return ApiError(code, headers={"WWW-Authenticate": "Bearer"})


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: SessionDep,
) -> User:
    """Resolve the user from the bearer token, or reject the request with 401."""
    if credentials is None:
        raise unauthorized(ErrorCode.NOT_AUTHENTICATED)
    claims = decode_token(credentials.credentials)
    if claims is None:
        raise unauthorized(ErrorCode.INVALID_TOKEN)
    user = session.get(User, claims.user_id)
    # A token from before the user's last password change is refused
    if user is None or claims.password_stamp != password_stamp(
        user.password_changed_at
    ):
        raise unauthorized(ErrorCode.INVALID_TOKEN)
    return user


def wrong_password() -> ApiError:
    """403, not 401: the token is valid, and clients sign out on a 401."""
    return ApiError(ErrorCode.WRONG_PASSWORD)


def token_for(user: User) -> TokenResponse:
    """A fresh token for the user, tied to their current password."""
    stamp = password_stamp(user.password_changed_at)
    return TokenResponse(access_token=create_access_token(user.id, stamp))


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
        raise ApiError(ErrorCode.EMAIL_TAKEN) from None
    session.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, session: SessionDep) -> TokenResponse:
    """Exchange valid credentials for an access token."""
    user = session.scalar(select(User).where(User.email == data.email.lower()))
    stored_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    password_ok = verify_password(data.password, stored_hash)
    if user is None or not password_ok:
        raise unauthorized(ErrorCode.INVALID_CREDENTIALS)
    return token_for(user)


@router.get("/me", response_model=UserResponse)
def me(current_user: CurrentUser) -> User:
    """Return the currently authenticated user."""
    return current_user


@router.put("/me", response_model=UserResponse)
def update_settings(
    data: AccountSettingsIn, current_user: CurrentUser, session: SessionDep
) -> User:
    """Set the current user's account settings: today only the language
    ("en", "ro", or null to follow the browser)."""
    current_user.language = data.language
    session.commit()
    return current_user


@router.put("/me/password", response_model=TokenResponse)
def change_password(
    data: PasswordChangeIn, current_user: CurrentUser, session: SessionDep
) -> TokenResponse:
    """Replace the current user's password, given the current one, and sign
    out everywhere else: every token issued before the change is refused
    from now on. Returns a fresh token for the device that made the change.

    403 if the current password is wrong: the token is fine, so not a 401,
    which clients rightly read as "signed out".
    """
    if not verify_password(data.current_password, current_user.password_hash):
        raise wrong_password()
    current_user.password_hash = hash_password(data.new_password)
    current_user.password_changed_at = datetime.now(UTC)
    session.commit()
    return token_for(current_user)


@router.put("/me/target", response_model=UserResponse)
def set_calorie_target(
    data: CalorieTargetIn, current_user: CurrentUser, session: SessionDep
) -> User:
    """Set the current user's daily calorie target, or clear it with null."""
    current_user.daily_calorie_target = data.daily_calorie_target
    session.commit()
    return current_user


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(
    data: Annotated[AccountDeleteIn, Body()],
    current_user: CurrentUser,
    session: SessionDep,
) -> Response:
    """Delete the current user and every row of theirs, in one transaction,
    given the current password. 403 if it is wrong, and nothing is deleted.

    One DELETE of the user row: every table of user data hangs off users
    with ON DELETE CASCADE, directly or through its parent. Every table
    ending empty, including meal_entries' RESTRICT on foods and the
    exercises' deferred references, is checked on PostgreSQL by
    tests/integration/test_delete_account_pg.py. Every token of the account
    is refused afterwards: its user is gone.
    """
    if not verify_password(data.password, current_user.password_hash):
        raise wrong_password()
    # In the same transaction: a restore from an older dump deletes the
    # account again (app/erasures.py); id and created_at, nothing personal
    session.add(
        Erasure(
            user_id=current_user.id,
            user_created_at=current_user.created_at,
            kind="account",
            erased_at=datetime.now(UTC),
        )
    )
    session.execute(delete(User).where(User.id == current_user.id))
    session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
