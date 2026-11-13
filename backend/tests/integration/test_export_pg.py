"""The data export on PostgreSQL (app/export.py)."""

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session, sessionmaker

from app import export
from app.db import get_session
from app.main import app
from app.models import User
from tests.conftest import register_and_login
from tests.test_delete_account import PASSWORD, fill_account

pytestmark = [
    pytest.mark.integration,
    pytest.mark.filterwarnings("error::sqlalchemy.exc.SAWarning"),
]

EMAIL = "export-pg@example.com"


def test_every_user_table_is_exported_on_postgresql(
    db: Session, pg_client: TestClient
) -> None:
    headers = register_and_login(pg_client, EMAIL)
    fill_account(pg_client, headers)

    response = pg_client.post(
        "/auth/me/export", json={"password": PASSWORD}, headers=headers
    )

    data = json.loads(response.text)
    for table in export.user_tables():
        assert data.get(table.name), table.name
    assert data["complete"] is True
    # Numeric columns come out as numbers, never strings
    assert isinstance(data["body_weights"][0]["weight_kg"], float)


@pytest.fixture
def committing_client(pg_engine: Engine) -> Iterator[TestClient]:
    """A session per request that commits, as in production, so the export
    opens its own REPEATABLE READ transaction on the engine."""
    sessions = sessionmaker(bind=pg_engine, expire_on_commit=False)

    def get_committing_session() -> Iterator[Session]:
        with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = get_committing_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        with sessions.begin() as session:
            session.execute(delete(User).where(User.email == EMAIL))


def test_the_export_reads_one_consistent_moment(committing_client: TestClient) -> None:
    client = committing_client
    headers = register_and_login(client, EMAIL)
    food = {
        "name": "Oats",
        "calories_per_100g": 389,
        "protein_per_100g": 17,
        "carbs_per_100g": 66,
        "fat_per_100g": 7,
    }
    assert client.post("/foods", json=food, headers=headers).status_code == 201

    response = client.post(
        "/auth/me/export", json={"password": PASSWORD}, headers=headers
    )

    data = json.loads(response.text)
    assert data["complete"] is True
    assert [row["name"] for row in data["foods"]] == ["Oats"]
