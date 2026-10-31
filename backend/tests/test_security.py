from datetime import UTC, datetime, timedelta

import jwt

from app.config import settings
from app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_is_not_the_plain_password() -> None:
    assert hash_password("s3cret-pass") != "s3cret-pass"


def test_verify_accepts_correct_password() -> None:
    hashed = hash_password("s3cret-pass")

    assert verify_password("s3cret-pass", hashed)


def test_verify_rejects_wrong_password() -> None:
    hashed = hash_password("s3cret-pass")

    assert not verify_password("wrong-pass", hashed)


def test_same_password_gives_different_hashes() -> None:
    # A random salt per hash means identical passwords never share a hash
    assert hash_password("s3cret-pass") != hash_password("s3cret-pass")


def test_token_round_trip_returns_user_id() -> None:
    token = create_access_token(user_id=42)

    assert decode_access_token(token) == 42


def test_token_signed_with_other_key_is_rejected() -> None:
    forged = jwt.encode(
        {"sub": "42", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        "attacker-key-long-enough-to-pass-length-check",
        algorithm=settings.jwt_algorithm,
    )

    assert decode_access_token(forged) is None


def test_expired_token_is_rejected() -> None:
    expired = jwt.encode(
        {"sub": "42", "exp": datetime.now(UTC) - timedelta(minutes=1)},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    assert decode_access_token(expired) is None
