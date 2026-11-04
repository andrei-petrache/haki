"""Input limits that only matter on PostgreSQL, checked through the API.

Ids are PostgreSQL "integer" columns: before the limits, a larger id made the
database raise and the API answer 500. SQLite has no such limit, so the unit
tests could not catch it.
"""

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from app.models import User
from app.schemas import MAX_DB_ID
from app.security import create_access_token

pytestmark = pytest.mark.integration

FOOD = {
    "name": "Rice",
    "calories_per_100g": 130,
    "protein_per_100g": 2.6,
    "carbs_per_100g": 28,
    "fat_per_100g": 0.34,
}


def entry(food_id: int) -> dict[str, object]:
    return {
        "food_id": food_id,
        "eaten_on": "2026-11-01",
        "meal_type": "lunch",
        "grams": 150,
    }


def workout(exercise_id: int) -> dict[str, object]:
    return {
        "performed_on": "2026-11-01",
        "exercises": [
            {"exercise_id": exercise_id, "sets": [{"reps": 5, "weight_kg": 100}]}
        ],
    }


def program(exercise_id: int) -> dict[str, object]:
    planned = {"exercise_id": exercise_id, "sets": 3, "reps": 5, "weight_kg": 100}
    return {
        "name": "Strength",
        "days": [{"position": 1, "name": "Legs", "exercises": [planned]}],
    }


START = {"performed_on": "2026-11-01"}


@pytest.fixture
def headers(make_user: Callable[[str], User]) -> dict[str, str]:
    user = make_user("andrei@example.com")
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.mark.parametrize(
    ("id_", "expected"),
    [(MAX_DB_ID, 404), (MAX_DB_ID + 1, 422)],
)
@pytest.mark.parametrize(
    "request_for",
    [
        lambda id_: ("PUT", f"/foods/{id_}", FOOD),
        lambda id_: ("DELETE", f"/foods/{id_}", None),
        lambda id_: ("DELETE", f"/entries/{id_}", None),
        lambda id_: ("POST", "/entries", entry(id_)),
        lambda id_: ("PUT", f"/exercises/{id_}", {"name": "Squat"}),
        lambda id_: ("DELETE", f"/exercises/{id_}", None),
        lambda id_: ("GET", f"/workouts/{id_}", None),
        lambda id_: ("PUT", f"/workouts/{id_}", workout(1)),
        lambda id_: ("DELETE", f"/workouts/{id_}", None),
        lambda id_: ("POST", "/workouts", workout(id_)),
        lambda id_: ("GET", f"/programs/{id_}", None),
        lambda id_: ("DELETE", f"/programs/{id_}", None),
        lambda id_: ("POST", "/programs", program(id_)),
        lambda id_: ("POST", f"/programs/{id_}/days/1/workouts", START),
    ],
    ids=[
        "update food",
        "delete food",
        "delete entry",
        "log entry",
        "rename exercise",
        "delete exercise",
        "read workout",
        "replace workout",
        "delete workout",
        "log workout exercise",
        "read program",
        "delete program",
        "plan exercise",
        "start from program",
    ],
)
def test_ids_at_the_postgres_integer_limit(
    pg_client: TestClient,
    headers: dict[str, str],
    request_for: Callable[[int], tuple[str, str, object]],
    id_: int,
    expected: int,
) -> None:
    method, path, body = request_for(id_)

    response = pg_client.request(method, path, json=body, headers=headers)

    assert response.status_code == expected


@pytest.mark.parametrize(
    ("offset", "expected"), [(MAX_DB_ID, 200), (MAX_DB_ID + 1, 422)]
)
def test_workout_list_offset_at_the_postgres_integer_limit(
    pg_client: TestClient, headers: dict[str, str], offset: int, expected: int
) -> None:
    response = pg_client.get(f"/workouts?offset={offset}", headers=headers)

    assert response.status_code == expected


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        (f"offset={MAX_DB_ID}", 200),
        (f"offset={MAX_DB_ID + 1}", 422),
        ("limit=100", 200),
        ("limit=101", 422),
    ],
)
def test_program_list_paging_at_its_limits(
    pg_client: TestClient, headers: dict[str, str], query: str, expected: int
) -> None:
    response = pg_client.get(f"/programs?{query}", headers=headers)

    assert response.status_code == expected


@pytest.mark.parametrize(
    ("day_id", "expected"), [(MAX_DB_ID, 404), (MAX_DB_ID + 1, 422)]
)
def test_program_day_id_at_the_postgres_integer_limit(
    pg_client: TestClient, headers: dict[str, str], day_id: int, expected: int
) -> None:
    # On a real program, so the day id is what decides the answer
    squat = pg_client.post("/exercises", json={"name": "Squat"}, headers=headers)
    created = pg_client.post(
        "/programs", json=program(squat.json()["id"]), headers=headers
    )
    path = f"/programs/{created.json()['id']}/days/{day_id}/workouts"

    response = pg_client.post(path, json=START, headers=headers)

    assert response.status_code == expected
