"""workouts.program_day_id on the schema the migrations create."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import User, Workout
from tests.conftest import register_and_login

pytestmark = pytest.mark.integration


def test_the_previous_versions_insert_still_works(
    db: Session, make_user: Callable[[str], User]
) -> None:
    # The previous version names only the columns it knows
    user = make_user("old-insert@example.com")

    db.execute(
        text("INSERT INTO workouts (user_id, performed_on) VALUES (:u, '2026-11-12')"),
        {"u": user.id},
    )

    stored = db.scalar(select(Workout.program_day_id).where(Workout.user_id == user.id))
    assert stored is None


def test_deleting_the_program_clears_the_link_on_postgresql(
    db: Session, pg_client: TestClient
) -> None:
    headers = register_and_login(pg_client, "program-day@example.com")
    squat = pg_client.post("/exercises", json={"name": "Squat"}, headers=headers)
    plan = pg_client.post(
        "/programs",
        json={
            "name": "Legs",
            "days": [
                {
                    "position": 1,
                    "name": "Legs",
                    "exercises": [
                        {
                            "exercise_id": squat.json()["id"],
                            "sets": 3,
                            "reps": 5,
                            "weight_kg": 100,
                        }
                    ],
                }
            ],
        },
        headers=headers,
    ).json()
    day_id = plan["days"][0]["id"]
    started = pg_client.post(
        f"/programs/{plan['id']}/days/{day_id}/workouts",
        json={"performed_on": "2026-11-12"},
        headers=headers,
    ).json()

    pg_client.delete(f"/programs/{plan['id']}", headers=headers)

    stored = pg_client.get(f"/workouts/{started['id']}", headers=headers).json()
    assert started["program_day_id"] == day_id
    assert stored["program_day_id"] is None
    assert started["program_id"] == plan["id"] and stored["program_id"] is None
    assert stored["exercises"] == started["exercises"]


def test_moving_kept_days_keeps_every_workout_on_its_day_on_postgresql(
    db: Session, pg_client: TestClient
) -> None:
    # Positions are unique per program and checked row by row on PostgreSQL:
    # a full week reversed has no free position to pass through
    headers = register_and_login(pg_client, "program-week@example.com")
    squat = pg_client.post("/exercises", json={"name": "Squat"}, headers=headers)
    planned = {
        "exercise_id": squat.json()["id"],
        "sets": 3,
        "reps": 5,
        "weight_kg": 100,
    }
    week = {
        "name": "Week",
        "days": [
            {"position": p, "name": f"Day {p}", "exercises": [planned]}
            for p in range(1, 8)
        ],
    }
    plan = pg_client.post("/programs", json=week, headers=headers).json()
    started = {
        d["name"]: pg_client.post(
            f"/programs/{plan['id']}/days/{d['id']}/workouts",
            json={"performed_on": "2026-11-12"},
            headers=headers,
        ).json()
        for d in plan["days"]
    }
    body = {
        "name": "Week, reversed",
        "days": [
            {
                "id": d["id"],
                "position": 8 - d["position"],
                "name": d["name"],
                "exercises": [planned],
            }
            for d in plan["days"]
        ],
    }

    response = pg_client.put(f"/programs/{plan['id']}", json=body, headers=headers)

    assert response.status_code == 200
    days = {d["name"]: d for d in response.json()["days"]}
    assert days == {
        d["name"]: d | {"position": 8 - d["position"]} for d in plan["days"]
    }
    for name, workout in started.items():
        stored = pg_client.get(f"/workouts/{workout['id']}", headers=headers).json()
        assert stored["program_day_id"] == days[name]["id"]
        assert stored["program_id"] == plan["id"]
    programs = pg_client.get("/programs", headers=headers).json()
    assert [p["name"] for p in programs] == ["Week, reversed"]
