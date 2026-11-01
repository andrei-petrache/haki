import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, make_url

from app.config import Settings

DATABASE_URL = "postgresql+psycopg://test:test@localhost:5432/test"
STRONG_KEY = "k" * 32


def make_settings(jwt_secret_key: str) -> Settings:
    # _env_file=None: only the values given here, never a local .env
    return Settings(
        _env_file=None,
        database_url=DATABASE_URL,
        db_user=None,
        db_password=None,
        db_host=None,
        db_name=None,
        jwt_secret_key=jwt_secret_key,
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


# Every character that breaks a URL or Alembic's config if not escaped
TRICKY_PASSWORD = "p%@/:#ss"
DB_PARTS = {
    "db_user": "haki",
    "db_password": TRICKY_PASSWORD,
    "db_host": "db",
    "db_name": "haki",
}
NO_DB_PARTS = dict.fromkeys(DB_PARTS)


def make_db_settings(**values: object) -> Settings:
    # Unset values passed as None, so variables from the environment never mix in
    return Settings(_env_file=None, jwt_secret_key=STRONG_KEY, **values)


def test_builds_the_url_from_parts_with_any_password() -> None:
    url = make_db_settings(**DB_PARTS, database_url=None).db_url

    assert url.drivername == "postgresql+psycopg"
    assert (url.username, url.host, url.port, url.database) == (
        "haki",
        "db",
        5432,
        "haki",
    )
    assert url.password == TRICKY_PASSWORD


def test_url_from_parts_survives_rendering_and_parsing() -> None:
    url = make_db_settings(**DB_PARTS, database_url=None).db_url

    rendered = url.render_as_string(hide_password=False)

    assert make_url(rendered).password == TRICKY_PASSWORD


def test_engine_gets_the_exact_password() -> None:
    url = make_db_settings(**DB_PARTS, database_url=None).db_url

    engine = create_engine(url)  # no connection is made here

    assert engine.url.password == TRICKY_PASSWORD
    engine.dispose()


def test_database_url_still_works_with_an_encoded_password() -> None:
    encoded = "postgresql+psycopg://haki:p%25%40%2F%3A%23ss@db:5432/haki"

    url = make_db_settings(**NO_DB_PARTS, database_url=encoded).db_url

    assert url.password == TRICKY_PASSWORD


def test_rejects_both_ways_at_once() -> None:
    with pytest.raises(ValidationError, match="not both"):
        make_db_settings(**DB_PARTS, database_url=DATABASE_URL)


@pytest.mark.parametrize("missing", ["db_user", "db_password", "db_host", "db_name"])
def test_rejects_incomplete_parts(missing: str) -> None:
    with pytest.raises(ValidationError, match="DB_USER, DB_PASSWORD"):
        make_db_settings(**{**DB_PARTS, missing: None}, database_url=None)


def test_database_error_does_not_reveal_the_password() -> None:
    with pytest.raises(ValidationError) as error:
        make_db_settings(**DB_PARTS, database_url=DATABASE_URL)

    assert TRICKY_PASSWORD not in str(error.value)
    assert TRICKY_PASSWORD not in repr(
        make_db_settings(**DB_PARTS, database_url=None).db_url
    )
