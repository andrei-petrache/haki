import threading
from collections.abc import Iterator
from contextlib import contextmanager
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


def create_access_token(user_id: int) -> str:
    """Create a signed JWT that identifies the user and expires."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> int | None:
    """Return the user id from a valid token, or None if invalid or expired."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError:
        return None
    return int(payload["sub"])
