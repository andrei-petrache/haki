from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.config import settings

# Argon2 with the library's recommended parameters (salted, deliberately slow)
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Return an Argon2 hash of the given plain-text password."""
    return password_hash.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Check a plain-text password against a stored hash."""
    return password_hash.verify(password, hashed)


def create_access_token(user_id: int) -> str:
    """Create a signed JWT that identifies the user and expires."""
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


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
