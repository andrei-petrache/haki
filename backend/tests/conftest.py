import os

# Tests must not depend on a local .env file or a running database.
# setdefault keeps a real value if one is already set (e.g. in CI).
# These must be set before any app module is imported.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test"
)
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-not-for-production")

from collections.abc import Iterator  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import get_session  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base  # noqa: E402


@pytest.fixture
def client() -> Iterator[TestClient]:
    """A test client backed by a fresh in-memory SQLite database per test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # SQLite ignores foreign keys unless asked; PostgreSQL always enforces them
    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    testing_session = sessionmaker(bind=engine, expire_on_commit=False)

    def override_get_session() -> Iterator[Session]:
        with testing_session() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def register_and_login(client: TestClient, email: str) -> dict[str, str]:
    """Create an account and return headers authenticating as that user."""
    password = "correct-horse-battery"
    client.post("/auth/signup", json={"email": email, "password": password})
    response = client.post("/auth/login", json={"email": email, "password": password})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def auth_headers(client: TestClient) -> dict[str, str]:
    return register_and_login(client, "andrei@example.com")


@pytest.fixture
def other_auth_headers(client: TestClient) -> dict[str, str]:
    return register_and_login(client, "mallory@example.com")
