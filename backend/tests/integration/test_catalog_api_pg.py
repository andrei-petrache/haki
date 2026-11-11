"""Catalog search and copies on PostgreSQL, whose LIKE and ordering differ
from SQLite's in ways the unit tests cannot see."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.catalog_import import import_catalog
from app.catalog_search import normalize
from tests.conftest import register_and_login

pytestmark = pytest.mark.integration


@pytest.fixture
def headers(db: Session, pg_client: TestClient) -> dict[str, str]:
    import_catalog(db)
    return register_and_login(pg_client, "catalog@example.com")


def test_search_without_diacritics_on_postgresql(
    pg_client: TestClient, headers: dict[str, str]
) -> None:
    response = pg_client.get(
        "/catalog/foods", params={"q": "branza feta"}, headers=headers
    )

    assert response.status_code == 200
    assert [item["name_ro"] for item in response.json()] == ["Brânză feta"]


def test_romanian_order_on_postgresql(
    pg_client: TestClient, headers: dict[str, str]
) -> None:
    response = pg_client.get(
        "/catalog/exercises", params={"language": "ro", "limit": 100}, headers=headers
    )

    # The database collation orders them ("Împins" among the I words, spaces
    # ignored at first): checked letter by letter, without diacritics
    initials = [normalize(item["name_ro"])[0] for item in response.json()]
    assert len(initials) == 88
    assert initials == sorted(initials)


def test_copy_twice_on_postgresql(
    pg_client: TestClient, headers: dict[str, str]
) -> None:
    feta = pg_client.get("/catalog/foods", params={"q": "feta"}, headers=headers)
    body = {"catalog_food_id": feta.json()[0]["id"], "language": "ro"}

    first = pg_client.post("/foods/from-catalog", json=body, headers=headers)
    second = pg_client.post("/foods/from-catalog", json=body, headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
