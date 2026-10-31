import pytest
from pydantic import ValidationError

from app.config import Settings

DATABASE_URL = "postgresql+psycopg://test:test@localhost:5432/test"
STRONG_KEY = "k" * 32


def make_settings(jwt_secret_key: str) -> Settings:
    # _env_file=None: only the values given here, never a local .env
    return Settings(
        _env_file=None, database_url=DATABASE_URL, jwt_secret_key=jwt_secret_key
    )


def test_accepts_a_key_of_32_bytes() -> None:
    assert make_settings(STRONG_KEY).jwt_secret_key == STRONG_KEY


@pytest.mark.parametrize(
    "key",
    [
        "change-me-generate-with-secrets-token-urlsafe",  # the .env.example value
        "change-me-but-long-enough-to-pass-the-length-check",
    ],
)
def test_rejects_the_placeholder(key: str) -> None:
    with pytest.raises(ValidationError, match="placeholder"):
        make_settings(key)


def test_rejects_a_key_shorter_than_32_bytes() -> None:
    with pytest.raises(ValidationError, match="at least 32 bytes"):
        make_settings("k" * 31)


def test_counts_bytes_not_characters() -> None:
    # 16 characters, but 32 bytes in UTF-8
    assert make_settings("ă" * 16).jwt_secret_key == "ă" * 16


def test_error_message_does_not_reveal_the_key() -> None:
    key = "short-but-secret"

    with pytest.raises(ValidationError) as error:
        make_settings(key)

    assert key not in str(error.value)
