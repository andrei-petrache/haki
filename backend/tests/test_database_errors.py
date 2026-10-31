from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import get_session
from app.main import app
from app.security import create_access_token


@pytest.fixture
def broken_db_client() -> Iterator[TestClient]:
    """A client whose database can never be opened, like a database that is down.

    SQLite raises the same OperationalError that PostgreSQL raises when the
    server refuses connections, without needing a network.
    """
    engine = create_engine("sqlite:////nonexistent-dir/haki.db")
    broken_session = sessionmaker(bind=engine)

    def override_get_session() -> Iterator[Session]:
        with broken_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_unreachable_database_returns_503(broken_db_client: TestClient) -> None:
    response = broken_db_client.post(
        "/auth/login", json={"email": "andrei@example.com", "password": "whatever"}
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Service temporarily unavailable, try again shortly"
    }
    assert response.headers["Retry-After"] == "5"


def test_unreachable_database_returns_503_on_authenticated_endpoint(
    broken_db_client: TestClient,
) -> None:
    # A well-signed token: the request gets past the token check to the database
    headers = {"Authorization": f"Bearer {create_access_token(1)}"}

    response = broken_db_client.get("/foods", headers=headers)

    assert response.status_code == 503


def test_unreachable_database_error_details_stay_out_of_response(
    broken_db_client: TestClient,
) -> None:
    response = broken_db_client.post(
        "/auth/login", json={"email": "andrei@example.com", "password": "whatever"}
    )

    assert "sqlite" not in response.text.lower()
    assert "nonexistent-dir" not in response.text
