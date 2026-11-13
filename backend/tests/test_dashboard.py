"""The weekly dashboard (app/dashboard.py)."""

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.body import server_today
from app.config import settings
from app.consent import CURRENT_VERSIONS
from app.models import CatalogExercise, CatalogSource, Exercise, TdeeEstimate

MONDAY = date(2026, 11, 9)
WEDNESDAY = MONDAY + timedelta(days=2)
OATS = {
    "name": "Oats",
    "calories_per_100g": 400,
    "protein_per_100g": 10,
    "carbs_per_100g": 60,
    "fat_per_100g": 5,
}


def week(client: TestClient, headers: dict[str, str], start: date) -> Any:
    return client.get("/dashboard/week", params={"start": str(start)}, headers=headers)


def log_food(
    client: TestClient, headers: dict[str, str], day: date, grams: float
) -> None:
    food = client.post("/foods", json=OATS, headers=headers).json()
    if "id" not in food:  # already created: the name is unique per user
        food = next(f for f in client.get("/foods", headers=headers).json())
    body = {
        "food_id": food["id"],
        "eaten_on": str(day),
        "meal_type": "lunch",
        "grams": grams,
    }
    assert client.post("/entries", json=body, headers=headers).status_code == 201


def log_quick(
    client: TestClient, headers: dict[str, str], day: date, kcal: float
) -> None:
    body = {"eaten_on": str(day), "meal_type": "snack", "calories": kcal, "protein": 5}
    assert client.post("/entries/quick", json=body, headers=headers).status_code == 201


def log_workout(
    client: TestClient,
    headers: dict[str, str],
    day: date,
    exercise_id: int,
    sets: list[tuple[int, float]],
) -> None:
    body = {
        "performed_on": str(day),
        "exercises": [
            {
                "exercise_id": exercise_id,
                "sets": [{"reps": r, "weight_kg": w} for r, w in sets],
            }
        ],
    }
    assert client.post("/workouts", json=body, headers=headers).status_code == 201


def own_exercise(client: TestClient, headers: dict[str, str], name: str) -> int:
    return client.post("/exercises", json={"name": name}, headers=headers).json()["id"]


def catalog_exercise(
    session: Session, client: TestClient, headers: dict[str, str], muscles: list[str]
) -> int:
    source = CatalogSource(
        key="test-exercises",
        name="Test",
        url="https://example.com",
        license="CC0-1.0",
        attribution="Test",
        attribution_required=False,
        share_alike=False,
        version="1",
    )
    session.add(source)
    session.flush()
    item = CatalogExercise(
        source_id=source.id,
        source_ref="bench",
        name="Bench press",
        search_text="bench press",
        primary_muscles=muscles,
        secondary_muscles=[],
        image_refs=[],
    )
    session.add(item)
    session.commit()
    copy = client.post(
        "/exercises/from-catalog",
        json={"catalog_exercise_id": item.id},
        headers=headers,
    )
    return copy.json()["id"]


def test_an_empty_week_is_all_zeros(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = week(client, auth_headers, WEDNESDAY)

    body = response.json()
    assert response.status_code == 200
    assert body["week_start"] == str(MONDAY)
    assert [d["date"] for d in body["days"]] == [
        str(MONDAY + timedelta(days=n)) for n in range(7)
    ]
    assert all(not d["logged"] and d["kcal"] == 0 for d in body["days"])
    assert body["totals"]["avg_kcal"] is None
    assert body["totals"]["volume_by_muscle"] == {}
    assert body["previous_week"]["days_logged"] == 0
    assert body["body_weight"] is None


def test_food_and_quick_entries_add_up_per_day_and_week(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    log_food(client, auth_headers, MONDAY, 50)  # 200 kcal, 5 g protein
    log_quick(client, auth_headers, MONDAY, 100)  # 100 kcal, 5 g protein
    log_quick(client, auth_headers, WEDNESDAY, 500)
    log_quick(client, auth_headers, MONDAY - timedelta(days=1), 900)  # last week

    body = week(client, auth_headers, MONDAY).json()

    monday, _, wednesday = body["days"][:3]
    assert (monday["kcal"], monday["protein"], monday["logged"]) == (300, 10, True)
    assert (wednesday["kcal"], wednesday["logged"]) == (500, True)
    totals = body["totals"]
    assert (totals["kcal"], totals["days_logged"], totals["avg_kcal"]) == (800, 2, 400)
    previous = body["previous_week"]
    assert (previous["kcal"], previous["days_logged"]) == (900, 1)


def test_training_volume_per_day_and_muscle(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    squat = own_exercise(client, auth_headers, "Squat")
    bench = catalog_exercise(session, client, auth_headers, ["chest", "triceps"])
    log_workout(client, auth_headers, MONDAY, squat, [(5, 100), (5, 100)])
    log_workout(client, auth_headers, WEDNESDAY, bench, [(8, 60), (10, 0)])

    body = week(client, auth_headers, MONDAY).json()

    monday, _, wednesday = body["days"][:3]
    assert (monday["workouts"], monday["sets"], monday["reps"]) == (1, 2, 10)
    assert monday["volume_kg"] == 1000
    # A bodyweight set counts as a set and its reps, with no volume
    assert (wednesday["sets"], wednesday["reps"], wednesday["volume_kg"]) == (
        2,
        18,
        480,
    )
    assert body["totals"]["volume_kg"] == 1480
    assert body["totals"]["volume_by_muscle"] == {
        "chest": 240,
        "other": 1000,
        "triceps": 240,
    }


def test_the_target_is_the_users_own_and_never_creates_an_estimate(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    client.put(
        "/auth/me/target", json={"daily_calorie_target": 2100}, headers=auth_headers
    )

    body = week(client, auth_headers, MONDAY).json()

    assert {d["target_kcal"] for d in body["days"]} == {2100}
    assert session.scalar(select(func.count()).select_from(TdeeEstimate)) == 0


def test_body_weight_with_consent_shows_the_weeks_trend(
    client: TestClient, auth_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "body_weight_enabled", True)
    this_monday = server_today() - timedelta(days=server_today().weekday())
    consent = {"version": CURRENT_VERSIONS["health_data"], "locale": "en"}
    without = week(client, auth_headers, this_monday).json()
    client.put("/auth/me/consents/health_data", json=consent, headers=auth_headers)
    for n, kg in enumerate([80.0, 79.8]):
        day = this_monday + timedelta(days=n)
        client.put(f"/weights/{day}", json={"weight_kg": kg}, headers=auth_headers)

    body = week(client, auth_headers, this_monday).json()

    assert without["body_weight"] is None
    weight = body["body_weight"]
    assert weight["weigh_ins"] == 2
    assert weight["start_trend_kg"] == 80.0
    assert weight["end_trend_kg"] == 79.98  # the trend moves a tenth of the way
    assert weight["change_kg"] == -0.02


def test_another_users_week_is_theirs(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    log_quick(client, other_auth_headers, MONDAY, 700)

    body = week(client, auth_headers, MONDAY).json()

    assert body["totals"]["kcal"] == 0


@pytest.mark.parametrize("days", [None, 8])
def test_a_week_out_of_range_is_refused(
    client: TestClient, auth_headers: dict[str, str], days: int | None
) -> None:
    start = date(1999, 12, 31) if days is None else server_today() + timedelta(days)

    response = week(client, auth_headers, start)

    assert response.status_code == 422
    assert response.json()["code"] == "date_out_of_range"


def test_the_dashboard_needs_a_login(client: TestClient) -> None:
    assert (
        client.get("/dashboard/week", params={"start": str(MONDAY)}).status_code == 401
    )


def test_exercises_without_sets_still_count_as_workouts(
    client: TestClient, auth_headers: dict[str, str], session: Session
) -> None:
    exercise = session.scalar(select(Exercise.id))
    assert exercise is None  # nothing yet
    squat = own_exercise(client, auth_headers, "Squat")
    log_workout(client, auth_headers, MONDAY, squat, [(5, 100)])

    body = week(client, auth_headers, MONDAY).json()

    assert body["totals"]["workouts"] == 1
