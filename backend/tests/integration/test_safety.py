"""The guard that keeps integration tests away from real databases.

Not marked "integration": these need no database and run in every test run.
"""

import pytest

from tests.integration.database import check_test_database_url

BASE = "postgresql+psycopg://haki:secret@localhost:5432"


@pytest.mark.parametrize(
    "database",
    ["haki", "test", "haki_test_copy", "haki_TEST", ""],
)
def test_refuses_databases_not_ending_in_test(database: str) -> None:
    with pytest.raises(RuntimeError, match="Refusing"):
        check_test_database_url(f"{BASE}/{database}")


def test_accepts_a_test_database() -> None:
    url = f"{BASE}/haki_test"

    assert check_test_database_url(url) == url
