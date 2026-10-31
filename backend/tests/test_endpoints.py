from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.db import database_is_reachable
from app.main import app

client = TestClient(app)


@pytest.fixture
def database_up() -> Iterator[None]:
    """Pretend the database is reachable for the duration of a test."""
    app.dependency_overrides[database_is_reachable] = lambda: True
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def database_down() -> Iterator[None]:
    """Pretend the database is unreachable for the duration of a test."""
    app.dependency_overrides[database_is_reachable] = lambda: False
    yield
    app.dependency_overrides.clear()


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_returns_ready_when_database_is_up(database_up: None) -> None:
    response = client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


def test_ready_returns_503_when_database_is_down(database_down: None) -> None:
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json() == {"status": "not ready", "database": "unreachable"}
