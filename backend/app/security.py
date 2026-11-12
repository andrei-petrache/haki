import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.config import settings

# Argon2 with the library's recommended parameters (salted, deliberately slow)
password_hash = PasswordHash.recommended()


class HashingBusy(Exception):
    """Every hashing slot stayed busy for longer than the allowed wait."""


class ConcurrencyLimit:
    """Lets at most `capacity` callers in at once; others wait up to `timeout`."""

    def __init__(self, capacity: int, timeout: float) -> None:
        self._slots = threading.BoundedSemaphore(capacity)
        self._timeout = timeout

    @contextmanager
    def slot(self) -> Iterator[None]:
        if not self._slots.acquire(timeout=self._timeout):
            raise HashingBusy
        try:
            yield
        finally:
            self._slots.release()


# Bounds memory however many requests arrive, with or without a proxy in front
hashing_limit = ConcurrencyLimit(
    settings.password_hash_concurrency, settings.password_hash_wait_seconds
)


def hash_password(password: str) -> str:
    """Return an Argon2 hash of the given plain-text password."""
    with hashing_limit.slot():
        return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Check a plain-text password against a stored hash."""
    with hashing_limit.slot():
        return password_hash.verify(password, hashed)


EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def password_stamp(changed_at: datetime | None) -> int | None:
    """The moment of the last password change, in whole microseconds since
    the epoch, or None if the password was never changed.

    A token carries it (claim "pwc") and must match the user's current one,
    so a password change refuses every token issued before it. Exact, unlike
    "iat", which has whole seconds: a token from the same second as the
    change would pass, or the fresh one would fail. SQLite returns the time
    without its zone; it is UTC.
    """
    if changed_at is None:
        return None
    if changed_at.tzinfo is None:
        changed_at = changed_at.replace(tzinfo=UTC)
    return (changed_at - EPOCH) // timedelta(microseconds=1)


@dataclass(frozen=True)
class TokenClaims:
    user_id: int
    # None for a token issued while the password had never been changed
    password_stamp: int | None


def create_access_token(user_id: int, stamp: int | None = None) -> str:
    """Create a signed JWT that identifies the user and expires, tied to the
    user's current password_stamp."""
    now = datetime.now(UTC)
    payload: dict[str, object] = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    if stamp is not None:
        payload["pwc"] = stamp
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_token(token: str) -> TokenClaims | None:
    """The claims of a valid token, or None if invalid or expired."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
        stamp = payload.get("pwc")
        if stamp is not None and not isinstance(stamp, int):
            return None
        return TokenClaims(user_id=int(payload["sub"]), password_stamp=stamp)
    except jwt.InvalidTokenError, ValueError:
        return None


def decode_access_token(token: str) -> int | None:
    """Return the user id from a valid token, or None if invalid or expired."""
    claims = decode_token(token)
    return None if claims is None else claims.user_id
