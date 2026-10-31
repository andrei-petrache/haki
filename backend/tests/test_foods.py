from typing import Any

import pytest
from fastapi.testclient import TestClient

OATS = {
    "name": "Oats",
    "calories_per_100g": 389,
    "protein_per_100g": 16.9,
    "carbs_per_100g": 66.3,
    "fat_per_100g": 6.9,
}


def create_food(
    client: TestClient, headers: dict[str, str], **overrides: Any
) -> dict[str, Any]:
    response = client.post("/foods", json={**OATS, **overrides}, headers=headers)
    assert response.status_code == 201
    return response.json()


def test_create_food_returns_it_with_id(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/foods", json={**OATS, "name": "  Oats  "}, headers=auth_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body == {**OATS, "id": body["id"]}


def test_list_foods_returns_own_foods_sorted_by_name(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    create_food(client, auth_headers, name="Rice")
    create_food(client, auth_headers, name="Apple")
    create_food(client, other_auth_headers, name="Banana")

    response = client.get("/foods", headers=auth_headers)

    assert response.status_code == 200
    assert [food["name"] for food in response.json()] == ["Apple", "Rice"]


def test_update_food_replaces_fields(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    food = create_food(client, auth_headers)
    changes = {**OATS, "name": "Rolled oats", "calories_per_100g": 379}

    response = client.put(f"/foods/{food['id']}", json=changes, headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {**changes, "id": food["id"]}


def test_delete_food_removes_it(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    food = create_food(client, auth_headers)

    response = client.delete(f"/foods/{food['id']}", headers=auth_headers)

    assert response.status_code == 204
    assert client.get("/foods", headers=auth_headers).json() == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"name": "   "},
        {"name": "x" * 101},
        {"calories_per_100g": 901},
        {"calories_per_100g": -1},
        {"protein_per_100g": 101},
        {"carbs_per_100g": -0.5},
        {"fat_per_100g": "a lot"},
    ],
)
def test_create_food_rejects_invalid_values(
    client: TestClient, auth_headers: dict[str, str], overrides: dict[str, Any]
) -> None:
    response = client.post("/foods", json={**OATS, **overrides}, headers=auth_headers)

    assert response.status_code == 422


def test_create_food_rejects_missing_field(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    incomplete = {key: value for key, value in OATS.items() if key != "fat_per_100g"}

    response = client.post("/foods", json=incomplete, headers=auth_headers)

    assert response.status_code == 422


def test_create_food_rejects_duplicate_name(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    create_food(client, auth_headers)

    response = client.post("/foods", json=OATS, headers=auth_headers)

    assert response.status_code == 409


def test_different_users_can_have_foods_with_same_name(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    create_food(client, auth_headers)

    response = client.post("/foods", json=OATS, headers=other_auth_headers)

    assert response.status_code == 201


def test_update_food_rejects_renaming_to_existing_name(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    create_food(client, auth_headers, name="Rice")
    oats = create_food(client, auth_headers)

    response = client.put(
        f"/foods/{oats['id']}", json={**OATS, "name": "Rice"}, headers=auth_headers
    )

    assert response.status_code == 409


def test_delete_food_rejects_food_used_by_meal_entries(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    food = create_food(client, auth_headers)
    entry = {
        "food_id": food["id"],
        "eaten_on": "2026-10-31",
        "meal_type": "breakfast",
        "grams": 50,
    }
    assert client.post("/entries", json=entry, headers=auth_headers).status_code == 201

    response = client.delete(f"/foods/{food['id']}", headers=auth_headers)

    assert response.status_code == 409
    assert len(client.get("/foods", headers=auth_headers).json()) == 1


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/foods"),
        ("POST", "/foods"),
        ("PUT", "/foods/1"),
        ("DELETE", "/foods/1"),
    ],
)
def test_foods_endpoints_require_authentication(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(method, path, json=OATS)

    assert response.status_code == 401


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_unknown_food_returns_404(
    client: TestClient, auth_headers: dict[str, str], method: str
) -> None:
    response = client.request(method, "/foods/999", json=OATS, headers=auth_headers)

    assert response.status_code == 404


def test_user_cannot_update_another_users_food(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    food = create_food(client, auth_headers)

    response = client.put(
        f"/foods/{food['id']}",
        json={**OATS, "name": "Hacked"},
        headers=other_auth_headers,
    )

    assert response.status_code == 404
    assert client.get("/foods", headers=auth_headers).json() == [food]


def test_user_cannot_delete_another_users_food(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    food = create_food(client, auth_headers)

    response = client.delete(f"/foods/{food['id']}", headers=other_auth_headers)

    assert response.status_code == 404
    assert client.get("/foods", headers=auth_headers).json() == [food]
