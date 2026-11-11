"""Favourites on PostgreSQL, which stores the time with its time zone."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Food
from tests.conftest import register_and_login

pytestmark = pytest.mark.integration

RICE = {
    "name": "Rice",
    "calories_per_100g": 130,
    "protein_per_100g": 2.7,
    "carbs_per_100g": 28,
    "fat_per_100g": 0.3,
}


def test_favourite_on_postgresql(db: Session, pg_client: TestClient) -> None:
    headers = register_and_login(pg_client, "favourite@example.com")
    food_id = pg_client.post("/foods", json=RICE, headers=headers).json()["id"]

    marked = pg_client.put(f"/foods/{food_id}/favourite", headers=headers)
    favourites = pg_client.get("/foods", params={"favourite": True}, headers=headers)

    assert marked.json()["favourite"] is True
    assert [food["id"] for food in favourites.json()] == [food_id]
    stored = db.scalar(select(Food.favourited_at).where(Food.id == food_id))
    assert stored is not None and stored.utcoffset() is not None
