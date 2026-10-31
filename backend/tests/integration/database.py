"""Safety guard for the database the integration tests run against."""

from sqlalchemy.engine import make_url

REQUIRED_SUFFIX = "_test"


def check_test_database_url(url: str) -> str:
    """Return the URL if it names a disposable test database, otherwise raise.

    Integration tests write and delete data, so they must never run against a
    real database such as the development database "haki".
    """
    database = make_url(url).database or ""
    if not database.endswith(REQUIRED_SUFFIX):
        raise RuntimeError(
            f"Refusing to run integration tests against database {database!r}: "
            f"its name must end with {REQUIRED_SUFFIX!r}"
        )
    return url
