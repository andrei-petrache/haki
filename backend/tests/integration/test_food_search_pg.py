"""The unified food search on PostgreSQL: its trigram-indexed catalog
search, the NOT IN for copied items, and Romanian collation."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_import import import_catalog
from app.models import CatalogFood
from tests.conftest import register_and_login

pytestmark = pytest.mark.integration

FETA = "173420"


def test_food_search_on_postgresql(db: Session, pg_client: TestClient) -> None:
    import_catalog(db)
    headers = register_and_login(pg_client, "search-pg@example.com")
    feta_id = db.scalar(select(CatalogFood.id).where(CatalogFood.source_ref == FETA))
    pg_client.post(
        "/foods/from-catalog",
        json={"catalog_food_id": feta_id, "language": "ro"},
        headers=headers,
    )

    response = pg_client.get(
        "/foods/search", params={"q": "branza", "language": "ro"}, headers=headers
    )

    assert response.status_code == 200
    results = response.json()
    assert (results[0]["origin"], results[0]["name"]) == ("own", "Brânză feta")
    catalog_ids = [r["id"] for r in results if r["origin"] == "catalog"]
    assert catalog_ids and feta_id not in catalog_ids
