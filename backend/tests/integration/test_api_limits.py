"""Input limits that only matter on PostgreSQL, checked through the API.

Ids are PostgreSQL "integer" columns: before the limits, a larger id made the
database raise and the API answer 500. SQLite has no such limit, so the unit
tests could not catch it.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.models import User
from app.schemas import MAX_DB_ID
from app.security import create_access_token

pytestmark = pytest.mark.integration

FOOD = {
    "name": "Rice",
    "calories_per_100g": 130,
    "protein_per_100g": 2.6,
    "carbs_per_100g": 28,
    "fat_per_100g": 0.34,
}


def entry(food_id: int) -> dict[str, object]:
    return {
        "food_id": food_id,
        "eaten_on": "2026-11-01",
        "meal_type": "lunch",
        "grams": 150,
    }


@pytest.fixture
def headers(make_user: Callable[[str], User]) -> dict[str, str]:
    user = make_user("andrei@example.com")
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.mark.parametrize(
    ("id_", "expected"),
    [(MAX_DB_ID, 404), (MAX_DB_ID + 1, 422)],
)
@pytest.mark.parametrize(
    "request_for",
    [
        lambda id_: ("PUT", f"/foods/{id_}", FOOD),
        lambda id_: ("DELETE", f"/foods/{id_}", None),
        lambda id_: ("DELETE", f"/entries/{id_}", None),
        lambda id_: ("POST", "/entries", entry(id_)),
    ],
    ids=["update food", "delete food", "delete entry", "log entry"],
)
def test_ids_at_the_postgres_integer_limit(
    pg_client: TestClient,
    headers: dict[str, str],
    request_for: Callable[[int], tuple[str, str, object]],
    id_: int,
    expected: int,
) -> None:
    method, path, body = request_for(id_)

    response = pg_client.request(method, path, json=body, headers=headers)

    assert response.status_code == expected
