from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.test_entries import RICE, create_entry, list_entries

DAY = "2026-11-10"
NEXT_DAY = "2026-11-11"
EGGS = {
    "name": "Eggs",
    "calories_per_100g": 143,
    "protein_per_100g": 12.6,
    "carbs_per_100g": 0.7,
    "fat_per_100g": 9.5,
}


def create_food(client: TestClient, headers: dict[str, str], food: dict) -> int:
    response = client.post("/foods", json=food, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def copy_body(**overrides: Any) -> dict[str, Any]:
    return {
        "from_day": DAY,
        "from_meal": "breakfast",
        "to_day": NEXT_DAY,
        "to_meal": "breakfast",
        **overrides,
    }


def log_breakfast(client: TestClient, headers: dict[str, str]) -> list[dict]:
    rice = create_food(client, headers, RICE)
    eggs = create_food(client, headers, EGGS)
    return [
        create_entry(client, headers, rice, eaten_on=DAY, grams=150),
        create_entry(client, headers, eggs, eaten_on=DAY, grams=120),
    ]


def without_id(entry: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in entry.items() if k != "id"}


def test_copy_meal_to_another_day_returns_new_entries_in_order(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    originals = log_breakfast(client, auth_headers)

    response = client.post("/entries/copy", json=copy_body(), headers=auth_headers)

    assert response.status_code == 201
    copies = response.json()
    assert [without_id(c) for c in copies] == [
        {**without_id(o), "eaten_on": NEXT_DAY} for o in originals
    ]
    assert {c["id"] for c in copies}.isdisjoint(o["id"] for o in originals)
    assert list_entries(client, auth_headers, NEXT_DAY) == copies


def test_copy_meal_to_another_meal_on_the_same_day(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    log_breakfast(client, auth_headers)

    response = client.post(
        "/entries/copy",
        json=copy_body(to_day=DAY, to_meal="dinner"),
        headers=auth_headers,
    )

    assert response.status_code == 201
    meals = [e["meal_type"] for e in list_entries(client, auth_headers, DAY)]
    assert meals == ["breakfast", "breakfast", "dinner", "dinner"]


def test_copy_meal_leaves_the_source_and_other_meals_alone(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    originals = log_breakfast(client, auth_headers)
    rice = originals[0]["food_id"]
    lunch = create_entry(client, auth_headers, rice, eaten_on=DAY, meal_type="lunch")

    client.post("/entries/copy", json=copy_body(), headers=auth_headers)

    assert list_entries(client, auth_headers, DAY) == [*originals, lunch]
    assert len(list_entries(client, auth_headers, NEXT_DAY)) == 2


def test_copy_an_empty_meal_returns_an_empty_list(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post("/entries/copy", json=copy_body(), headers=auth_headers)

    assert response.status_code == 201
    assert response.json() == []


def test_copy_meal_never_copies_another_users_entries(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    log_breakfast(client, auth_headers)

    response = client.post(
        "/entries/copy", json=copy_body(), headers=other_auth_headers
    )

    assert response.json() == []
    assert list_entries(client, other_auth_headers, NEXT_DAY) == []
    assert list_entries(client, auth_headers, NEXT_DAY) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"to_day": DAY},
        {"from_meal": "brunch"},
        {"to_meal": "Breakfast"},
        {"from_day": "yesterday"},
        {"to_day": None},
    ],
)
def test_copy_meal_rejects_invalid_requests(
    client: TestClient, auth_headers: dict[str, str], overrides: dict[str, Any]
) -> None:
    log_breakfast(client, auth_headers)

    response = client.post(
        "/entries/copy", json=copy_body(**overrides), headers=auth_headers
    )

    assert response.status_code == 422
    assert len(list_entries(client, auth_headers, DAY)) == 2


def test_copy_meal_requires_login(client: TestClient) -> None:
    assert client.post("/entries/copy", json=copy_body()).status_code == 401
