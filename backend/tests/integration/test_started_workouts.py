"""Programs and the workouts started from them, on PostgreSQL."""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import ProgramDay, ProgramExercise, User
from app.security import create_access_token

pytestmark = pytest.mark.integration


@pytest.fixture
def headers(make_user: Callable[[str], User]) -> dict[str, str]:
    user = make_user("andrei@example.com")
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_changing_a_program_leaves_a_started_workout_alone(
    pg_client: TestClient, db: Session, headers: dict[str, str]
) -> None:
    squat = pg_client.post("/exercises", json={"name": "Squat"}, headers=headers)
    body = {
        "name": "Legs",
        "days": [
            {
                "position": 1,
                "name": "Light",
                "exercises": [
                    {
                        "exercise_id": squat.json()["id"],
                        "sets": 2,
                        "reps": 8,
                        "weight_kg": 60,
                    }
                ],
            }
        ],
    }
    created = pg_client.post("/programs", json=body, headers=headers).json()
    day_id = created["days"][0]["id"]
    started = pg_client.post(
        f"/programs/{created['id']}/days/{day_id}/workouts",
        json={"performed_on": "2026-11-01"},
        headers=headers,
    ).json()

    # There is no PUT /programs yet: change the plan in the database, as any
    # later edit would
    db.execute(
        update(ProgramExercise)
        .where(ProgramExercise.program_day_id == day_id)
        .values(sets=5, reps=3, weight_kg=140)
    )
    db.execute(update(ProgramDay).where(ProgramDay.id == day_id).values(name="Heavy"))
    db.expire_all()

    stored = pg_client.get(f"/workouts/{started['id']}", headers=headers)
    assert stored.json() == started
    plan = pg_client.get(f"/programs/{created['id']}", headers=headers).json()
    assert plan["days"][0]["name"] == "Heavy"  # the change did land
    assert plan["days"][0]["exercises"][0]["reps"] == 3
