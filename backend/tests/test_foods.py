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
    assert body == {
        **OATS,
        "id": body["id"],
        "catalog_food_id": None,
        "favourite": False,
        "last_logged": None,
    }


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
    assert response.json() == {
        **changes,
        "id": food["id"],
        "catalog_food_id": None,
        "favourite": False,
        "last_logged": None,
    }


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
        {"calories_per_100g": 951},
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


def test_create_food_accepts_fats_up_to_950_kcal(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    lard = {"name": "Lard", "calories_per_100g": 902, "fat_per_100g": 100}
    edge = {"name": "Edge", "calories_per_100g": 950, "fat_per_100g": 100}

    responses = [
        client.post("/foods", json={**OATS, **food}, headers=auth_headers)
        for food in (lard, edge)
    ]

    assert [r.status_code for r in responses] == [201, 201]


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


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize("food_id", [0, -1, 2**31])
def test_out_of_range_food_id_returns_422(
    client: TestClient, auth_headers: dict[str, str], method: str, food_id: int
) -> None:
    response = client.request(
        method, f"/foods/{food_id}", json=OATS, headers=auth_headers
    )

    assert response.status_code == 422


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


def log(client: TestClient, headers: dict[str, str], food_id: int, day: str) -> None:
    entry = {"food_id": food_id, "eaten_on": day, "meal_type": "lunch", "grams": 100}
    response = client.post("/entries", json=entry, headers=headers)
    assert response.status_code == 201


def recent_names(
    client: TestClient, headers: dict[str, str], **params: Any
) -> list[str]:
    response = client.get("/foods/recent", params=params, headers=headers)
    assert response.status_code == 200
    return [food["name"] for food in response.json()]


def favourite_names(
    client: TestClient, headers: dict[str, str], favourite: bool
) -> list[str]:
    response = client.get("/foods", params={"favourite": favourite}, headers=headers)
    assert response.status_code == 200
    return [food["name"] for food in response.json()]


def test_recent_foods_are_ordered_by_last_logged_each_once(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    oats, rice, eggs = (
        create_food(client, auth_headers, name=name)["id"]
        for name in ("Oats", "Rice", "Eggs")
    )
    create_food(client, auth_headers, name="Never logged")
    log(client, auth_headers, oats, "2026-11-10")
    log(client, auth_headers, rice, "2026-11-11")
    log(client, auth_headers, oats, "2026-11-11")
    # Logged last, for an earlier day: it still counts as the newest use
    log(client, auth_headers, eggs, "2026-11-01")

    names = recent_names(client, auth_headers)

    assert names == ["Eggs", "Oats", "Rice"]


def test_recent_foods_returns_full_foods(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    food = create_food(client, auth_headers)
    log(client, auth_headers, food["id"], "2026-11-11")

    response = client.get("/foods/recent", headers=auth_headers)

    last = {"grams": 100.0, "meal_type": "lunch", "eaten_on": "2026-11-11"}
    assert response.json() == [{**food, "last_logged": last}]


def test_recent_foods_respects_limit(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    for name in ("A", "B", "C"):
        food_id = create_food(client, auth_headers, name=name)["id"]
        log(client, auth_headers, food_id, "2026-11-11")

    names = recent_names(client, auth_headers, limit=2)

    assert names == ["C", "B"]


def test_recent_foods_is_empty_without_entries(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    create_food(client, auth_headers)

    assert recent_names(client, auth_headers) == []


def test_recent_foods_shows_only_own_foods(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    mine = create_food(client, auth_headers, name="Mine")["id"]
    theirs = create_food(client, other_auth_headers, name="Theirs")["id"]
    log(client, auth_headers, mine, "2026-11-11")
    log(client, other_auth_headers, theirs, "2026-11-11")

    assert recent_names(client, auth_headers) == ["Mine"]
    assert recent_names(client, other_auth_headers) == ["Theirs"]


@pytest.mark.parametrize("limit", [0, 51, "many"])
def test_recent_foods_rejects_invalid_limit(
    client: TestClient, auth_headers: dict[str, str], limit: Any
) -> None:
    response = client.get(
        "/foods/recent", params={"limit": limit}, headers=auth_headers
    )

    assert response.status_code == 422


def test_recent_foods_requires_login(client: TestClient) -> None:
    assert client.get("/foods/recent").status_code == 401


def test_mark_favourite_returns_the_food_marked(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    food = create_food(client, auth_headers)

    response = client.put(f"/foods/{food['id']}/favourite", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {**food, "favourite": True}


def test_new_foods_are_not_favourites(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    food = create_food(client, auth_headers)

    assert food["favourite"] is False


def test_list_foods_filters_by_favourite(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    for name in ("Rice", "Oats", "Eggs"):
        food = create_food(client, auth_headers, name=name)
        if name != "Eggs":
            client.put(f"/foods/{food['id']}/favourite", headers=auth_headers)

    favourites = favourite_names(client, auth_headers, True)
    others = favourite_names(client, auth_headers, False)
    everything = client.get("/foods", headers=auth_headers).json()

    assert favourites == ["Oats", "Rice"]
    assert others == ["Eggs"]
    assert len(everything) == 3


def test_mark_and_unmark_favourite_are_idempotent(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    food_id = create_food(client, auth_headers)["id"]
    path = f"/foods/{food_id}/favourite"

    marked = [client.put(path, headers=auth_headers) for _ in range(2)]
    favourites_after_marking = favourite_names(client, auth_headers, True)
    unmarked = [client.delete(path, headers=auth_headers) for _ in range(2)]

    assert [r.status_code for r in marked] == [200, 200]
    assert favourites_after_marking == ["Oats"]
    assert [r.status_code for r in unmarked] == [204, 204]
    assert favourite_names(client, auth_headers, True) == []


def test_editing_a_food_keeps_it_a_favourite(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    food = create_food(client, auth_headers)
    client.put(f"/foods/{food['id']}/favourite", headers=auth_headers)

    response = client.put(
        f"/foods/{food['id']}",
        json={**OATS, "name": "Rolled oats"},
        headers=auth_headers,
    )

    assert response.json()["favourite"] is True


@pytest.mark.parametrize("method", ["put", "delete"])
def test_favourite_of_another_users_food_is_404_and_unchanged(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    method: str,
) -> None:
    food = create_food(client, auth_headers)
    client.put(f"/foods/{food['id']}/favourite", headers=auth_headers)

    response = client.request(
        method, f"/foods/{food['id']}/favourite", headers=other_auth_headers
    )

    assert response.status_code == 404
    assert favourite_names(client, auth_headers, True) == ["Oats"]
    assert favourite_names(client, other_auth_headers, True) == []


@pytest.mark.parametrize("method", ["put", "delete"])
def test_favourite_of_unknown_food_is_404(
    client: TestClient, auth_headers: dict[str, str], method: str
) -> None:
    response = client.request(method, "/foods/999/favourite", headers=auth_headers)

    assert response.status_code == 404


def test_list_foods_rejects_invalid_favourite_filter(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/foods", params={"favourite": "maybe"}, headers=auth_headers)

    assert response.status_code == 422


@pytest.mark.parametrize("method", ["put", "delete"])
def test_favourite_requires_login(client: TestClient, method: str) -> None:
    assert client.request(method, "/foods/1/favourite").status_code == 401
