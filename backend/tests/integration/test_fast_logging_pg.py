"""Fast logging queries on PostgreSQL, which is stricter than SQLite about
grouping and ordering."""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import register_and_login

pytestmark = pytest.mark.integration

FOOD = {
    "calories_per_100g": 100,
    "protein_per_100g": 1,
    "carbs_per_100g": 1,
    "fat_per_100g": 1,
}


def create_food(client: TestClient, headers: dict[str, str], name: str) -> int:
    response = client.post("/foods", json={**FOOD, "name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def log(client: TestClient, headers: dict[str, str], food_id: int) -> None:
    entry = {
        "food_id": food_id,
        "eaten_on": "2026-11-11",
        "meal_type": "lunch",
        "grams": 100,
    }
    assert client.post("/entries", json=entry, headers=headers).status_code == 201


def test_recent_foods_on_postgresql(pg_client: TestClient) -> None:
    headers = register_and_login(pg_client, "recent@example.com")
    oats, rice = (create_food(pg_client, headers, name) for name in ("Oats", "Rice"))
    for food_id in (oats, rice, oats):
        log(pg_client, headers, food_id)

    response = pg_client.get("/foods/recent", headers=headers)

    assert response.status_code == 200
    assert [food["name"] for food in response.json()] == ["Oats", "Rice"]
