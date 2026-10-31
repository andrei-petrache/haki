from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.test_entries import DAY, create_entry, create_food

ZERO = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}


def get_summary(client: TestClient, headers: dict[str, str]) -> dict[str, Any]:
    response = client.get("/summary", params={"date": DAY}, headers=headers)
    assert response.status_code == 200
    return response.json()


def set_target(client: TestClient, headers: dict[str, str], target: int | None) -> Any:
    return client.put(
        "/auth/me/target", json={"daily_calorie_target": target}, headers=headers
    )


def test_summary_adds_up_the_day_per_meal_and_overall(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    food_id = create_food(client, auth_headers)
    create_entry(client, auth_headers, food_id, meal_type="breakfast", grams=150)
    create_entry(client, auth_headers, food_id, meal_type="lunch", grams=200)
    # Must not count: another day, another user
    create_entry(client, auth_headers, food_id, eaten_on="2026-11-01")
    create_entry(client, other_auth_headers, create_food(client, other_auth_headers))
    set_target(client, auth_headers, 2000)

    summary = get_summary(client, auth_headers)

    assert summary == {
        "eaten_on": DAY,
        "totals": {"calories": 455.0, "protein": 9.1, "carbs": 98.0, "fat": 1.2},
        "meals": {
            "breakfast": {"calories": 195.0, "protein": 3.9, "carbs": 42.0, "fat": 0.5},
            "lunch": {"calories": 260.0, "protein": 5.2, "carbs": 56.0, "fat": 0.7},
            "dinner": ZERO,
            "snack": ZERO,
        },
        "daily_calorie_target": 2000,
        "calories_remaining": 1545.0,
    }


def test_summary_of_empty_day_without_target(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    summary = get_summary(client, auth_headers)

    assert summary["totals"] == ZERO
    assert summary["meals"] == {meal: ZERO for meal in summary["meals"]}
    assert len(summary["meals"]) == 4
    assert summary["daily_calorie_target"] is None
    assert summary["calories_remaining"] is None


def test_summary_remaining_is_negative_over_target(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    food_id = create_food(client, auth_headers)
    create_entry(client, auth_headers, food_id, grams=500)  # 650 kcal
    set_target(client, auth_headers, 500)

    assert get_summary(client, auth_headers)["calories_remaining"] == -150.0


def test_set_target_shows_in_me_and_null_clears_it(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = set_target(client, auth_headers, 2200)

    assert response.status_code == 200
    assert response.json()["daily_calorie_target"] == 2200
    me = client.get("/auth/me", headers=auth_headers).json()
    assert me["daily_calorie_target"] == 2200

    assert set_target(client, auth_headers, None).json()["daily_calorie_target"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"daily_calorie_target": 499},
        {"daily_calorie_target": 10001},
        {"daily_calorie_target": "lots"},
        {},
    ],
)
def test_set_target_rejects_invalid_values(
    client: TestClient, auth_headers: dict[str, str], body: dict[str, Any]
) -> None:
    response = client.put("/auth/me/target", json=body, headers=auth_headers)

    assert response.status_code == 422
