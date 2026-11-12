from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event

from tests.test_exercises import create_exercise

DAY = "2026-11-01"


def workout(*exercise_ids: int, **overrides: Any) -> dict[str, Any]:
    """A workout body: each exercise with two sets, unless overridden."""
    return {
        "performed_on": DAY,
        "note": "Leg day",
        "exercises": [
            {
                "exercise_id": exercise_id,
                "sets": [{"reps": 8, "weight_kg": 60}, {"reps": 6, "weight_kg": 70}],
            }
            for exercise_id in exercise_ids
        ],
        **overrides,
    }


def create_workout(
    client: TestClient, headers: dict[str, str], body: dict[str, Any]
) -> dict[str, Any]:
    response = client.post("/workouts", json=body, headers=headers)
    assert response.status_code == 201
    return response.json()


@pytest.fixture
def squat(client: TestClient, auth_headers: dict[str, str]) -> int:
    return create_exercise(client, auth_headers, "Squat")["id"]


@pytest.fixture
def deadlift(client: TestClient, auth_headers: dict[str, str]) -> int:
    return create_exercise(client, auth_headers, "Deadlift")["id"]


@contextmanager
def count_queries() -> Iterator[list[str]]:
    """Record every SQL statement sent to any database while inside."""
    statements: list[str] = []

    def record(*args: Any) -> None:
        statements.append(args[2])  # (connection, cursor, statement, ...)

    event.listen(Engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(Engine, "before_cursor_execute", record)


def test_create_workout_returns_it_with_exercises_and_sets(
    client: TestClient, auth_headers: dict[str, str], squat: int, deadlift: int
) -> None:
    body = workout(squat, deadlift, note="  Leg day  ")

    response = client.post("/workouts", json=body, headers=auth_headers)

    assert response.status_code == 201
    created = response.json()
    assert created == {
        "id": created["id"],
        "performed_on": DAY,
        "note": "Leg day",
        "exercises": [
            {
                "exercise_id": squat,
                "exercise_name": "Squat",
                "sets": [{"reps": 8, "weight_kg": 60}, {"reps": 6, "weight_kg": 70}],
            },
            {
                "exercise_id": deadlift,
                "exercise_name": "Deadlift",
                "sets": [{"reps": 8, "weight_kg": 60}, {"reps": 6, "weight_kg": 70}],
            },
        ],
        "program_day_id": None,
    }


@pytest.mark.parametrize("note", [None, "", "   "])
def test_create_workout_without_a_note(
    client: TestClient, auth_headers: dict[str, str], squat: int, note: str | None
) -> None:
    created = create_workout(client, auth_headers, workout(squat, note=note))

    assert created["note"] is None


def test_create_workout_without_exercises(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    created = create_workout(client, auth_headers, workout(note="Rest day"))

    assert created["exercises"] == []


def test_create_workout_can_repeat_an_exercise(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    created = create_workout(client, auth_headers, workout(squat, squat))

    assert [item["exercise_id"] for item in created["exercises"]] == [squat, squat]


def test_create_workout_accepts_bodyweight_sets(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    pull_up = create_exercise(client, auth_headers, "Pull-up")["id"]
    body = workout(
        exercises=[{"exercise_id": pull_up, "sets": [{"reps": 10, "weight_kg": 0}]}]
    )

    created = create_workout(client, auth_headers, body)

    assert created["exercises"][0]["sets"] == [{"reps": 10, "weight_kg": 0}]


@pytest.mark.parametrize(
    "performed_on",
    [date(2000, 1, 1), date.today(), date.today() + timedelta(days=1)],
)
def test_create_workout_accepts_dates_in_range(
    client: TestClient, auth_headers: dict[str, str], squat: int, performed_on: date
) -> None:
    body = workout(squat, performed_on=performed_on.isoformat())

    response = client.post("/workouts", json=body, headers=auth_headers)

    assert response.status_code == 201


def test_read_workout_returns_what_was_created(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    created = create_workout(client, auth_headers, workout(squat))

    response = client.get(f"/workouts/{created['id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == created


def test_read_workout_takes_the_same_queries_however_many_exercises(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    ids = [create_exercise(client, auth_headers, f"E{n}")["id"] for n in range(5)]
    small = create_workout(client, auth_headers, workout(ids[0]))
    large = create_workout(client, auth_headers, workout(*ids))

    with count_queries() as small_queries:
        client.get(f"/workouts/{small['id']}", headers=auth_headers)
    with count_queries() as large_queries:
        client.get(f"/workouts/{large['id']}", headers=auth_headers)

    assert len(large_queries) == len(small_queries)


def test_renaming_an_exercise_shows_in_past_workouts(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    created = create_workout(client, auth_headers, workout(squat))
    client.put(f"/exercises/{squat}", json={"name": "Back squat"}, headers=auth_headers)

    response = client.get(f"/workouts/{created['id']}", headers=auth_headers)

    assert response.json()["exercises"][0]["exercise_name"] == "Back squat"


def test_list_workouts_returns_own_workouts_newest_first_with_counts(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    squat: int,
    deadlift: int,
) -> None:
    older = create_workout(
        client, auth_headers, workout(squat, performed_on="2026-10-30")
    )
    newer = create_workout(client, auth_headers, workout(squat, deadlift, note=None))
    other_squat = create_exercise(client, other_auth_headers)["id"]
    create_workout(client, other_auth_headers, workout(other_squat))

    response = client.get("/workouts", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": newer["id"],
            "performed_on": DAY,
            "note": None,
            "exercise_count": 2,
            "set_count": 4,
        },
        {
            "id": older["id"],
            "performed_on": "2026-10-30",
            "note": "Leg day",
            "exercise_count": 1,
            "set_count": 2,
        },
    ]


def test_list_workouts_pages_with_limit_and_offset(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    ids = [
        create_workout(
            client, auth_headers, workout(squat, performed_on=f"2026-10-0{day}")
        )["id"]
        for day in range(1, 6)
    ]

    response = client.get("/workouts?limit=2&offset=1", headers=auth_headers)

    assert response.status_code == 200
    # Newest first: day 5, then 4, 3, 2, 1; skip one, take two
    assert [item["id"] for item in response.json()] == [ids[3], ids[2]]


def test_replace_workout_replaces_everything(
    client: TestClient, auth_headers: dict[str, str], squat: int, deadlift: int
) -> None:
    created = create_workout(client, auth_headers, workout(squat, deadlift))
    changes = {
        "performed_on": "2026-10-31",
        "note": None,
        "exercises": [
            {"exercise_id": deadlift, "sets": [{"reps": 5, "weight_kg": 120.5}]}
        ],
    }

    response = client.put(
        f"/workouts/{created['id']}", json=changes, headers=auth_headers
    )

    expected = {
        "id": created["id"],
        "performed_on": "2026-10-31",
        "note": None,
        "exercises": [
            {
                "exercise_id": deadlift,
                "exercise_name": "Deadlift",
                "sets": [{"reps": 5, "weight_kg": 120.5}],
            }
        ],
        "program_day_id": None,
    }
    assert response.status_code == 200
    assert response.json() == expected
    stored = client.get(f"/workouts/{created['id']}", headers=auth_headers)
    assert stored.json() == expected


def test_delete_workout_removes_it_but_keeps_the_exercises(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    created = create_workout(client, auth_headers, workout(squat))

    response = client.delete(f"/workouts/{created['id']}", headers=auth_headers)

    assert response.status_code == 204
    assert client.get("/workouts", headers=auth_headers).json() == []
    exercises = client.get("/exercises", headers=auth_headers).json()
    assert [exercise["id"] for exercise in exercises] == [squat]


ONE_SET = {"reps": 1, "weight_kg": 1}


def too_many_sets(exercise_id: int) -> dict[str, Any]:
    sets = [ONE_SET] * 51
    return {"exercises": [{"exercise_id": exercise_id, "sets": sets}]}


@pytest.mark.parametrize(
    "overrides",
    [
        lambda e: {"performed_on": "1999-12-31"},
        lambda e: {"performed_on": (date.today() + timedelta(days=2)).isoformat()},
        lambda e: {"performed_on": "yesterday"},
        lambda e: {"note": "x" * 501},
        lambda e: {"exercises": [{"exercise_id": e, "sets": []}]},
        too_many_sets,
        lambda e: {"exercises": [{"exercise_id": e, "sets": [{"reps": 1}]}]},
        lambda e: {"exercises": [{"exercise_id": 0, "sets": [ONE_SET]}]},
        lambda e: {"exercises": [{"exercise_id": 2**31, "sets": [ONE_SET]}]},
        lambda e: {"exercises": workout(*[e] * 51)["exercises"]},
    ],
    ids=[
        "date before 2000",
        "date after tomorrow",
        "date not a date",
        "note too long",
        "no sets",
        "51 sets",
        "set without weight",
        "exercise id 0",
        "exercise id too large",
        "51 exercises",
    ],
)
def test_create_workout_rejects_invalid_values(
    client: TestClient, auth_headers: dict[str, str], squat: int, overrides: Any
) -> None:
    response = client.post(
        "/workouts", json=workout(squat, **overrides(squat)), headers=auth_headers
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    "bad_set",
    [
        {"reps": 0, "weight_kg": 60},
        {"reps": 1001, "weight_kg": 60},
        {"reps": "eight", "weight_kg": 60},
        {"reps": 8, "weight_kg": -1},
        {"reps": 8, "weight_kg": 1000.5},
    ],
)
def test_create_workout_rejects_invalid_sets(
    client: TestClient,
    auth_headers: dict[str, str],
    squat: int,
    bad_set: dict[str, Any],
) -> None:
    body = workout(exercises=[{"exercise_id": squat, "sets": [bad_set]}])

    response = client.post("/workouts", json=body, headers=auth_headers)

    assert response.status_code == 422
    assert client.get("/workouts", headers=auth_headers).json() == []


def test_create_workout_rejects_missing_field(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    body = workout(squat)
    del body["performed_on"]

    response = client.post("/workouts", json=body, headers=auth_headers)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=101", "offset=-1", f"offset={2**31}", "limit=a"]
)
def test_list_workouts_rejects_invalid_paging(
    client: TestClient, auth_headers: dict[str, str], query: str
) -> None:
    response = client.get(f"/workouts?{query}", headers=auth_headers)

    assert response.status_code == 422


def test_create_workout_rejects_unknown_exercise(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    response = client.post("/workouts", json=workout(squat, 999), headers=auth_headers)

    assert response.status_code == 404
    assert client.get("/workouts", headers=auth_headers).json() == []


def test_user_cannot_log_another_users_exercise(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    squat: int,
) -> None:
    response = client.post("/workouts", json=workout(squat), headers=other_auth_headers)

    assert response.status_code == 404
    assert client.get("/workouts", headers=other_auth_headers).json() == []


def test_replace_workout_rejects_another_users_exercise_and_keeps_it(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    squat: int,
) -> None:
    created = create_workout(client, auth_headers, workout(squat))
    other_squat = create_exercise(client, other_auth_headers)["id"]

    response = client.put(
        f"/workouts/{created['id']}", json=workout(other_squat), headers=auth_headers
    )

    assert response.status_code == 404
    stored = client.get(f"/workouts/{created['id']}", headers=auth_headers)
    assert stored.json() == created


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/workouts"),
        ("POST", "/workouts"),
        ("GET", "/workouts/1"),
        ("PUT", "/workouts/1"),
        ("DELETE", "/workouts/1"),
    ],
)
def test_workouts_endpoints_require_authentication(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(method, path, json=workout())

    assert response.status_code == 401


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_unknown_workout_returns_404(
    client: TestClient, auth_headers: dict[str, str], method: str
) -> None:
    response = client.request(
        method, "/workouts/999", json=workout(), headers=auth_headers
    )

    assert response.status_code == 404


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
@pytest.mark.parametrize("workout_id", [0, -1, 2**31])
def test_out_of_range_workout_id_returns_422(
    client: TestClient, auth_headers: dict[str, str], method: str, workout_id: int
) -> None:
    response = client.request(
        method, f"/workouts/{workout_id}", json=workout(), headers=auth_headers
    )

    assert response.status_code == 422


@pytest.mark.parametrize(
    ("method", "body"), [("GET", None), ("PUT", workout()), ("DELETE", None)]
)
def test_user_cannot_touch_another_users_workout(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    squat: int,
    method: str,
    body: dict[str, Any] | None,
) -> None:
    created = create_workout(client, auth_headers, workout(squat))

    response = client.request(
        method, f"/workouts/{created['id']}", json=body, headers=other_auth_headers
    )

    assert response.status_code == 404
    stored = client.get(f"/workouts/{created['id']}", headers=auth_headers)
    assert stored.json() == created
