"""Last time and best set on PostgreSQL: its date order and float compare."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from tests.conftest import register_and_login

pytestmark = pytest.mark.integration


def test_last_and_best_on_postgresql(db: Session, pg_client: TestClient) -> None:
    headers = register_and_login(pg_client, "history@example.com")
    squat = pg_client.post("/exercises", json={"name": "Squat"}, headers=headers)
    squat_id = squat.json()["id"]
    workout_ids = []
    for day, weight in (
        ("2026-11-01", 102.5),
        ("2026-11-09", 100),
        ("2026-11-05", 97.5),
    ):
        body = {
            "performed_on": day,
            "note": None,
            "exercises": [
                {"exercise_id": squat_id, "sets": [{"reps": 5, "weight_kg": weight}]}
            ],
        }
        response = pg_client.post("/workouts", json=body, headers=headers)
        workout_ids.append(response.json()["id"])

    last = pg_client.get(f"/exercises/{squat_id}/last", headers=headers).json()
    best = pg_client.get(f"/exercises/{squat_id}/best", headers=headers).json()
    before = pg_client.get(
        f"/exercises/{squat_id}/last",
        params={"before_workout": workout_ids[1]},
        headers=headers,
    ).json()

    assert (last["performed_on"], last["sets"][0]["weight_kg"]) == ("2026-11-09", 100)
    assert (best["performed_on"], best["weight_kg"]) == ("2026-11-01", 102.5)
    assert before["performed_on"] == "2026-11-05"
