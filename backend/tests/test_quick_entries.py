from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.test_entries import DAY, create_entry, create_food, list_entries


def quick_body(**overrides: Any) -> dict[str, Any]:
    return {"eaten_on": DAY, "meal_type": "lunch", "calories": 450, **overrides}


def quick_add(
    client: TestClient, headers: dict[str, str], **overrides: Any
) -> dict[str, Any]:
    response = client.post(
        "/entries/quick", json=quick_body(**overrides), headers=headers
    )
    assert response.status_code == 201
    return response.json()


def summary(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.get("/summary", params={"date": DAY}, headers=headers)
    assert response.status_code == 200
    return response.json()


def test_quick_add_returns_an_entry_without_a_food(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post("/entries/quick", json=quick_body(), headers=auth_headers)

    assert response.status_code == 201
    body = response.json()
    assert body == {
        "id": body["id"],
        "food_id": None,
        "food_name": "Quick add",
        "eaten_on": DAY,
        "meal_type": "lunch",
        "grams": None,
        "calories": 450.0,
        "protein": 0.0,
        "carbs": 0.0,
        "fat": 0.0,
        "quick": True,
    }


def test_quick_add_keeps_a_name_and_macros(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = quick_add(
        client,
        auth_headers,
        name="  Sarmale la bunica  ",
        protein=21.5,
        carbs=30,
        fat=18.25,
    )

    assert body["food_name"] == "Sarmale la bunica"
    assert (body["protein"], body["carbs"], body["fat"]) == (21.5, 30.0, 18.2)


def test_quick_entries_list_with_food_entries_in_meal_order(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    food_id = create_food(client, auth_headers)
    dinner = create_entry(client, auth_headers, food_id, meal_type="dinner")
    quick_lunch = quick_add(client, auth_headers, meal_type="lunch")
    breakfast = create_entry(client, auth_headers, food_id, meal_type="breakfast")
    quick_dinner = quick_add(client, auth_headers, meal_type="dinner")

    entries = list_entries(client, auth_headers)

    assert [(e["quick"], e["id"]) for e in entries] == [
        (False, breakfast["id"]),
        (True, quick_lunch["id"]),
        (False, dinner["id"]),
        (True, quick_dinner["id"]),
    ]


def test_quick_entries_count_in_the_summary(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    food_id = create_food(client, auth_headers)
    create_entry(client, auth_headers, food_id, meal_type="lunch")  # 195 kcal
    quick_add(client, auth_headers, calories=450, protein=20.04)
    quick_add(client, auth_headers, calories=100, protein=0.04, meal_type="snack")

    totals = summary(client, auth_headers)

    assert totals["meals"]["lunch"]["calories"] == 645.0
    assert totals["meals"]["snack"]["calories"] == 100.0
    assert totals["totals"]["calories"] == 745.0
    # Summed exactly, rounded once: 3.9 + 20.04 + 0.04 = 23.98
    assert totals["totals"]["protein"] == 24.0


def test_quick_entries_are_only_for_their_day_and_user(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    quick_add(client, auth_headers, eaten_on="2026-10-30")
    quick_add(client, other_auth_headers)

    assert list_entries(client, auth_headers) == []
    assert summary(client, auth_headers)["totals"]["calories"] == 0


def test_delete_quick_entry(client: TestClient, auth_headers: dict[str, str]) -> None:
    entry = quick_add(client, auth_headers)

    response = client.delete(f"/entries/quick/{entry['id']}", headers=auth_headers)

    assert response.status_code == 204
    assert list_entries(client, auth_headers) == []


def test_ids_of_quick_and_food_entries_are_separate(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    # The first of each kind both get id 1: deleting one leaves the other
    food_id = create_food(client, auth_headers)
    food_entry = create_entry(client, auth_headers, food_id)
    quick = quick_add(client, auth_headers)
    assert food_entry["id"] == quick["id"]

    client.delete(f"/entries/{food_entry['id']}", headers=auth_headers)

    assert [(e["quick"], e["id"]) for e in list_entries(client, auth_headers)] == [
        (True, quick["id"])
    ]


def test_user_cannot_delete_another_users_quick_entry(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    entry = quick_add(client, auth_headers)

    response = client.delete(
        f"/entries/quick/{entry['id']}", headers=other_auth_headers
    )

    assert response.status_code == 404
    assert list_entries(client, auth_headers) == [entry]


def test_delete_unknown_quick_entry_is_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.delete("/entries/quick/999", headers=auth_headers)

    assert response.status_code == 404


def test_copy_meal_copies_quick_entries_too(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    food_id = create_food(client, auth_headers)
    create_entry(client, auth_headers, food_id, meal_type="lunch")
    quick_add(client, auth_headers, name="Ciorbă", calories=300, fat=12)
    body = {
        "from_day": DAY,
        "from_meal": "lunch",
        "to_day": "2026-11-01",
        "to_meal": "dinner",
    }

    response = client.post("/entries/copy", json=body, headers=auth_headers)

    assert response.status_code == 201
    copies = response.json()
    assert [(c["quick"], c["food_name"]) for c in copies] == [
        (False, "Rice"),
        (True, "Ciorbă"),
    ]
    assert copies[1]["fat"] == 12.0
    copied_day = list_entries(client, auth_headers, "2026-11-01")
    assert [c["meal_type"] for c in copied_day] == ["dinner", "dinner"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"calories": 5001},
        {"calories": -1},
        {"calories": None},
        {"protein": 501},
        {"fat": -0.1},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 101},
        {"meal_type": "brunch"},
        {"eaten_on": "yesterday"},
    ],
)
def test_quick_add_rejects_invalid_values(
    client: TestClient, auth_headers: dict[str, str], overrides: dict[str, Any]
) -> None:
    response = client.post(
        "/entries/quick", json=quick_body(**overrides), headers=auth_headers
    )

    assert response.status_code == 422


def test_quick_add_requires_calories(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    body = quick_body()
    del body["calories"]

    response = client.post("/entries/quick", json=body, headers=auth_headers)

    assert response.status_code == 422


def test_quick_entries_require_login(client: TestClient) -> None:
    assert client.post("/entries/quick", json=quick_body()).status_code == 401
    assert client.delete("/entries/quick/1").status_code == 401
