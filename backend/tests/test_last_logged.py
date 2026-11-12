from typing import Any

from fastapi.testclient import TestClient

from tests.test_foods import create_food
from tests.test_workouts import count_queries


def log(
    client: TestClient,
    headers: dict[str, str],
    food_id: int,
    grams: float,
    meal: str = "lunch",
    day: str = "2026-11-12",
) -> dict[str, Any]:
    body = {"food_id": food_id, "eaten_on": day, "meal_type": meal, "grams": grams}
    response = client.post("/entries", json=body, headers=headers)
    assert response.status_code == 201
    return response.json()


def last_of(foods: list[dict[str, Any]], name: str) -> Any:
    return next(food for food in foods if food["name"] == name)["last_logged"]


def test_a_food_never_logged_has_no_last_logged(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    create_food(client, auth_headers)

    foods = client.get("/foods", headers=auth_headers).json()

    assert foods[0]["last_logged"] is None


def test_last_logged_is_the_newest_entry_even_for_an_earlier_day(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    oats = create_food(client, auth_headers)["id"]
    log(client, auth_headers, oats, 40, "breakfast", "2026-11-12")
    # Logged last, for yesterday: still the newest use, as in recents
    log(client, auth_headers, oats, 60, "snack", "2026-11-11")

    foods = client.get("/foods", headers=auth_headers).json()

    assert foods[0]["last_logged"] == {
        "grams": 60.0,
        "meal_type": "snack",
        "eaten_on": "2026-11-11",
    }


def test_each_food_has_its_own_last_logged_on_every_list(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    oats = create_food(client, auth_headers, name="Oats")["id"]
    rice = create_food(client, auth_headers, name="Rice")["id"]
    log(client, auth_headers, oats, 40, "breakfast")
    log(client, auth_headers, rice, 150, "dinner")
    client.put(f"/foods/{oats}/favourite", headers=auth_headers)

    for path, params in (
        ("/foods", {}),
        ("/foods/recent", {}),
        ("/foods", {"favourite": True}),
    ):
        foods = client.get(path, params=params, headers=auth_headers).json()
        assert last_of(foods, "Oats")["grams"] == 40.0, path

    everything = client.get("/foods", headers=auth_headers).json()
    assert last_of(everything, "Rice") == {
        "grams": 150.0,
        "meal_type": "dinner",
        "eaten_on": "2026-11-12",
    }


def test_deleting_the_newest_entry_shows_the_one_before(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    oats = create_food(client, auth_headers)["id"]
    log(client, auth_headers, oats, 40)
    newest = log(client, auth_headers, oats, 80)

    client.delete(f"/entries/{newest['id']}", headers=auth_headers)

    foods = client.get("/foods", headers=auth_headers).json()
    assert foods[0]["last_logged"]["grams"] == 40.0


def test_single_food_answers_carry_last_logged(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    oats = create_food(client, auth_headers)["id"]
    log(client, auth_headers, oats, 40)

    favourite = client.put(f"/foods/{oats}/favourite", headers=auth_headers)
    renamed = client.put(
        f"/foods/{oats}",
        json={
            "name": "Rolled oats",
            "calories_per_100g": 379,
            "protein_per_100g": 13,
            "carbs_per_100g": 67,
            "fat_per_100g": 6.5,
        },
        headers=auth_headers,
    )

    assert favourite.json()["last_logged"]["grams"] == 40.0
    assert renamed.json()["last_logged"]["grams"] == 40.0


def test_listing_foods_takes_the_same_queries_however_many(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    def queries_for_list() -> int:
        with count_queries() as statements:
            client.get("/foods", headers=auth_headers)
        return len(statements)

    first = create_food(client, auth_headers, name="Food 0")["id"]
    log(client, auth_headers, first, 10)
    one = queries_for_list()
    for i in range(1, 6):
        food_id = create_food(client, auth_headers, name=f"Food {i}")["id"]
        log(client, auth_headers, food_id, 10 + i)

    assert queries_for_list() == one
