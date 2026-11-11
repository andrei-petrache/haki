"""Copying a meal on PostgreSQL: the copies keep the source's order."""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import register_and_login

pytestmark = pytest.mark.integration


def test_copy_meal_on_postgresql(pg_client: TestClient) -> None:
    headers = register_and_login(pg_client, "copy@example.com")
    food = {
        "name": "Rice",
        "calories_per_100g": 130,
        "protein_per_100g": 2.7,
        "carbs_per_100g": 28,
        "fat_per_100g": 0.3,
    }
    food_id = pg_client.post("/foods", json=food, headers=headers).json()["id"]
    for grams in (100, 50, 25):
        entry = {
            "food_id": food_id,
            "eaten_on": "2026-11-10",
            "meal_type": "lunch",
            "grams": grams,
        }
        assert (
            pg_client.post("/entries", json=entry, headers=headers).status_code == 201
        )

    response = pg_client.post(
        "/entries/copy",
        json={
            "from_day": "2026-11-10",
            "from_meal": "lunch",
            "to_day": "2026-11-11",
            "to_meal": "dinner",
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert [e["grams"] for e in response.json()] == [100, 50, 25]
    day = pg_client.get("/entries", params={"date": "2026-11-11"}, headers=headers)
    assert [e["meal_type"] for e in day.json()] == ["dinner"] * 3
