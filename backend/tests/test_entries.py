from typing import Any

import pytest
from fastapi.testclient import TestClient

DAY = "2026-10-31"
# 150 g -> 195.0 kcal, 3.9 g protein, 42.0 g carbs, 0.51 g fat (shown as 0.5)
RICE = {
    "name": "Rice",
    "calories_per_100g": 130,
    "protein_per_100g": 2.6,
    "carbs_per_100g": 28,
    "fat_per_100g": 0.34,
}


def create_food(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post("/foods", json=RICE, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def entry_body(food_id: int, /, **overrides: Any) -> dict[str, Any]:
    return {
        "food_id": food_id,
        "eaten_on": DAY,
        "meal_type": "breakfast",
        "grams": 150,
        **overrides,
    }


def create_entry(
    client: TestClient, headers: dict[str, str], food_id: int, **overrides: Any
) -> dict[str, Any]:
    response = client.post(
        "/entries", json=entry_body(food_id, **overrides), headers=headers
    )
    assert response.status_code == 201
    return response.json()


def list_entries(
    client: TestClient, headers: dict[str, str], day: str = DAY
) -> list[dict[str, Any]]:
    response = client.get("/entries", params={"date": day}, headers=headers)
    assert response.status_code == 200
    return response.json()


def test_create_entry_returns_computed_nutrients(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    food_id = create_food(client, auth_headers)

    response = client.post("/entries", json=entry_body(food_id), headers=auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "food_id": food_id,
        "food_name": "Rice",
        "eaten_on": DAY,
        "meal_type": "breakfast",
        "grams": 150,
        "calories": 195.0,
        "protein": 3.9,
        "carbs": 42.0,
        "fat": 0.5,
    }


def test_list_entries_returns_own_entries_for_day_in_meal_order(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    food_id = create_food(client, auth_headers)
    snack = create_entry(client, auth_headers, food_id, meal_type="snack")
    first_breakfast = create_entry(client, auth_headers, food_id)
    dinner = create_entry(client, auth_headers, food_id, meal_type="dinner")
    second_breakfast = create_entry(client, auth_headers, food_id)
    create_entry(client, auth_headers, food_id, eaten_on="2026-10-30")
    create_entry(client, other_auth_headers, create_food(client, other_auth_headers))

    entries = list_entries(client, auth_headers)

    assert [entry["id"] for entry in entries] == [
        first_breakfast["id"],
        second_breakfast["id"],
        dinner["id"],
        snack["id"],
    ]


@pytest.mark.parametrize("params", [{}, {"date": "31-10-2026"}, {"date": "today"}])
def test_list_entries_requires_valid_date(
    client: TestClient, auth_headers: dict[str, str], params: dict[str, str]
) -> None:
    response = client.get("/entries", params=params, headers=auth_headers)

    assert response.status_code == 422


def test_delete_entry_removes_it(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    entry = create_entry(client, auth_headers, create_food(client, auth_headers))

    response = client.delete(f"/entries/{entry['id']}", headers=auth_headers)

    assert response.status_code == 204
    assert list_entries(client, auth_headers) == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"grams": 0},
        {"grams": -10},
        {"grams": 5001},
        {"meal_type": "brunch"},
        {"eaten_on": "2026-13-01"},
        {"eaten_on": None},
        {"food_id": "rice"},
    ],
)
def test_create_entry_rejects_invalid_values(
    client: TestClient, auth_headers: dict[str, str], overrides: dict[str, Any]
) -> None:
    food_id = create_food(client, auth_headers)

    response = client.post(
        "/entries", json=entry_body(food_id, **overrides), headers=auth_headers
    )

    assert response.status_code == 422


def test_create_entry_rejects_unknown_food(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post("/entries", json=entry_body(999), headers=auth_headers)

    assert response.status_code == 404


def test_user_cannot_log_another_users_food(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    victims_food_id = create_food(client, auth_headers)

    response = client.post(
        "/entries", json=entry_body(victims_food_id), headers=other_auth_headers
    )

    assert response.status_code == 404
    assert list_entries(client, other_auth_headers) == []


def test_user_cannot_delete_another_users_entry(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    entry = create_entry(client, auth_headers, create_food(client, auth_headers))

    response = client.delete(f"/entries/{entry['id']}", headers=other_auth_headers)

    assert response.status_code == 404
    assert list_entries(client, auth_headers) == [entry]


def test_user_does_not_see_another_users_entries(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    create_entry(client, auth_headers, create_food(client, auth_headers))

    assert list_entries(client, other_auth_headers) == []


def test_unknown_entry_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.delete("/entries/999", headers=auth_headers)

    assert response.status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", f"/entries?date={DAY}"),
        ("POST", "/entries"),
        ("DELETE", "/entries/1"),
        ("GET", f"/summary?date={DAY}"),
        ("PUT", "/auth/me/target"),
    ],
)
def test_endpoints_require_authentication(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(method, path, json={})

    assert response.status_code == 401
