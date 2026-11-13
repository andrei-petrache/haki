"""Password reset by e-mail: ask for a link, then set a new password with it.

The link carries a reset token in its fragment (PUBLIC_BASE_URL/reset#token=…),
which neither the proxy's log nor a Referer ever sees. The token is a JWT of
kind "reset" (app.security), valid 30 minutes and tied to the password stamp:
the reset changes the stamp, so a link works once, and any password change
kills the links sent before it. No token is stored.

Behind settings.password_reset_enabled (off in prod until a real mail
provider exists); off, both endpoints answer 404.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, func, select

from app.auth import SessionDep, token_for
from app.config import settings
from app.errors import ApiError, ErrorCode
from app.mail import send_password_reset
from app.models import PasswordResetRequest, User
from app.schemas import (
    AcceptedResponse,
    PasswordResetConfirmIn,
    PasswordResetIn,
    TokenResponse,
)
from app.security import (
    create_reset_token,
    decode_reset_token,
    hash_password,
    password_stamp,
)

# Per account, so nobody can flood someone's mailbox. Counted in the
# database (two pods). Two requests at the very same moment can both pass
# the count before either is written: the cap can be passed by a request or
# two, never without bound, which is enough for a mailbox
MAX_REQUESTS_PER_HOUR = 3
WINDOW = timedelta(hours=1)
# The same answer whether or not the e-mail has an account
ACCEPTED = "If that e-mail has an account, a reset link is on its way"


def require_enabled() -> None:
    """Off, the endpoints answer as if they did not exist."""
    if not settings.password_reset_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


router = APIRouter(
    prefix="/auth/password-reset",
    tags=["auth"],
    dependencies=[Depends(require_enabled)],
)


def reset_link(token: str) -> str:
    """Built from the setting, never from the request's Host header."""
    return f"{settings.public_base_url.rstrip('/')}/reset#token={token}"


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=AcceptedResponse)
def request_reset(data: PasswordResetIn, session: SessionDep) -> AcceptedResponse:
    """Send a reset link to the account's e-mail, if there is an account.

    Always 202 with the same body, so nobody learns which e-mails have an
    account; above 3 requests an hour for one account, nothing is sent.
    """
    user = session.scalar(select(User).where(User.email == data.email.lower()))
    if user is None:
        return AcceptedResponse(detail=ACCEPTED)
    now = datetime.now(UTC)
    session.execute(
        delete(PasswordResetRequest).where(
            PasswordResetRequest.user_id == user.id,
            PasswordResetRequest.created_at < now - WINDOW,
        )
    )
    recent = session.scalar(
        select(func.count())
        .select_from(PasswordResetRequest)
        .where(PasswordResetRequest.user_id == user.id)
    )
    if (recent or 0) >= MAX_REQUESTS_PER_HOUR:
        session.commit()
        return AcceptedResponse(detail=ACCEPTED)
    session.add(PasswordResetRequest(user_id=user.id, created_at=now))
    session.commit()
    token = create_reset_token(user.id, password_stamp(user.password_changed_at))
    # The address stored for the account, never one from the request
    send_password_reset(user.email, reset_link(token))
    return AcceptedResponse(detail=ACCEPTED)


@router.post("/confirm", response_model=TokenResponse)
def confirm_reset(data: PasswordResetConfirmIn, session: SessionDep) -> TokenResponse:
    """Set a new password with a reset token, and sign out everywhere: every
    token issued before is refused from now on. Returns a fresh token.

    400 for a token that is not a reset token (an access token never resets
    a password), has expired, or was used up by a password change since.
    """
    claims = decode_reset_token(data.token)
    user = None if claims is None else session.get(User, claims.user_id)
    if (
        claims is None
        or user is None
        or claims.password_stamp != password_stamp(user.password_changed_at)
    ):
        raise ApiError(ErrorCode.INVALID_RESET_TOKEN)
    user.password_hash = hash_password(data.new_password)
    user.password_changed_at = datetime.now(UTC)
    session.commit()
    return token_for(user)
