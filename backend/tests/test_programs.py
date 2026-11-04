from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.schemas import (
    MAX_DAYS_PER_PROGRAM,
    MAX_EXERCISES_PER_PROGRAM_DAY,
    MAX_SETS_PER_EXERCISE,
)
from tests.test_exercises import create_exercise
from tests.test_workouts import count_queries


def planned(exercise_id: int, **overrides: Any) -> dict[str, Any]:
    """One planned exercise: 3 x 8 at 60 kg, unless overridden."""
    defaults = {"exercise_id": exercise_id, "sets": 3, "reps": 8, "weight_kg": 60}
    return defaults | overrides


def without_name(item: dict[str, Any]) -> dict[str, Any]:
    """A planned exercise from a response, as it was sent."""
    return {key: value for key, value in item.items() if key != "exercise_name"}


def day(*exercise_ids: int, position: int = 1, name: str = "Push") -> dict[str, Any]:
    return {
        "position": position,
        "name": name,
        "exercises": [planned(exercise_id) for exercise_id in exercise_ids],
    }


def program(*exercise_ids: int, **overrides: Any) -> dict[str, Any]:
    """A program body: one day (position 1) with the given exercises."""
    return {"name": "Push/Pull/Legs", "days": [day(*exercise_ids)], **overrides}


def create_program(
    client: TestClient, headers: dict[str, str], body: dict[str, Any]
) -> dict[str, Any]:
    response = client.post("/programs", json=body, headers=headers)
    assert response.status_code == 201
    return response.json()


def list_programs(client: TestClient, headers: dict[str, str]) -> list[Any]:
    return client.get("/programs", headers=headers).json()


@pytest.fixture
def squat(client: TestClient, auth_headers: dict[str, str]) -> int:
    return create_exercise(client, auth_headers, "Squat")["id"]


@pytest.fixture
def deadlift(client: TestClient, auth_headers: dict[str, str]) -> int:
    return create_exercise(client, auth_headers, "Deadlift")["id"]


def test_create_program_returns_it_with_days_and_exercises(
    client: TestClient, auth_headers: dict[str, str], squat: int, deadlift: int
) -> None:
    body = program(
        name="  PPL  ",
        days=[
            day(squat, position=1, name="  Legs  "),
            {
                "position": 2,
                "name": "Pull",
                "exercises": [planned(deadlift, sets=5, reps=5, weight_kg=120.5)],
            },
        ],
    )

    response = client.post("/programs", json=body, headers=auth_headers)

    assert response.status_code == 201
    created = response.json()
    assert created == {
        "id": created["id"],
        "name": "PPL",
        "days": [
            {
                "id": created["days"][0]["id"],
                "position": 1,
                "name": "Legs",
                "exercises": [
                    {
                        "exercise_id": squat,
                        "exercise_name": "Squat",
                        "sets": 3,
                        "reps": 8,
                        "weight_kg": 60,
                    }
                ],
            },
            {
                "id": created["days"][1]["id"],
                "position": 2,
                "name": "Pull",
                "exercises": [
                    {
                        "exercise_id": deadlift,
                        "exercise_name": "Deadlift",
                        "sets": 5,
                        "reps": 5,
                        "weight_kg": 120.5,
                    }
                ],
            },
        ],
    }


def test_program_days_come_back_by_position(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    body = program(days=[day(squat, position=5), day(squat, position=2)])

    created = create_program(client, auth_headers, body)
    stored = client.get(f"/programs/{created['id']}", headers=auth_headers).json()

    assert [item["position"] for item in created["days"]] == [2, 5]
    assert stored == created


def test_program_day_keeps_the_order_of_its_exercises(
    client: TestClient, auth_headers: dict[str, str], squat: int, deadlift: int
) -> None:
    bench = create_exercise(client, auth_headers, "Bench")["id"]
    created = create_program(client, auth_headers, program(deadlift, squat, bench))

    stored = client.get(f"/programs/{created['id']}", headers=auth_headers).json()

    order = [item["exercise_id"] for item in stored["days"][0]["exercises"]]
    assert order == [deadlift, squat, bench]


def test_create_program_accepts_values_at_the_limits(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    most = planned(squat, sets=MAX_SETS_PER_EXERCISE, reps=1000, weight_kg=1000)
    least = planned(squat, sets=1, reps=1, weight_kg=0)
    full_day = {
        "position": 1,
        "name": "x" * 100,
        "exercises": [most] + [least] * (MAX_EXERCISES_PER_PROGRAM_DAY - 1),
    }
    other_days = [
        day(squat, position=position) for position in range(2, MAX_DAYS_PER_PROGRAM + 1)
    ]
    body = program(name="x" * 100, days=[full_day, *other_days])

    created = create_program(client, auth_headers, body)

    assert len(created["days"]) == MAX_DAYS_PER_PROGRAM
    exercises = created["days"][0]["exercises"]
    assert len(exercises) == MAX_EXERCISES_PER_PROGRAM_DAY
    assert without_name(exercises[0]) == most
    assert without_name(exercises[1]) == least


def test_read_program_returns_what_was_created(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    created = create_program(client, auth_headers, program(squat))

    response = client.get(f"/programs/{created['id']}", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == created


def test_read_program_takes_the_same_queries_however_many_days_and_exercises(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    ids = [create_exercise(client, auth_headers, f"E{n}")["id"] for n in range(5)]
    small = create_program(client, auth_headers, program(ids[0], name="Small"))
    large_days = [day(*ids, position=position) for position in range(1, 6)]
    large = create_program(client, auth_headers, program(name="Large", days=large_days))

    with count_queries() as small_queries:
        client.get(f"/programs/{small['id']}", headers=auth_headers)
    with count_queries() as large_queries:
        client.get(f"/programs/{large['id']}", headers=auth_headers)

    assert len(large_queries) == len(small_queries)


def test_renaming_an_exercise_shows_in_programs(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    created = create_program(client, auth_headers, program(squat))
    client.put(f"/exercises/{squat}", json={"name": "Back squat"}, headers=auth_headers)

    stored = client.get(f"/programs/{created['id']}", headers=auth_headers).json()

    assert stored["days"][0]["exercises"][0]["exercise_name"] == "Back squat"


def test_list_programs_returns_own_programs_by_name_with_day_counts(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    squat: int,
) -> None:
    upper = create_program(
        client,
        auth_headers,
        program(
            name="upper/lower", days=[day(squat, position=1), day(squat, position=4)]
        ),
    )
    full = create_program(client, auth_headers, program(squat, name="Full body"))
    other_squat = create_exercise(client, other_auth_headers)["id"]
    create_program(client, other_auth_headers, program(other_squat, name="Other"))

    response = client.get("/programs", headers=auth_headers)

    assert response.status_code == 200
    # By name ignoring case: "Full body" before "upper/lower"
    assert response.json() == [
        {"id": full["id"], "name": "Full body", "day_count": 1},
        {"id": upper["id"], "name": "upper/lower", "day_count": 2},
    ]


def test_list_programs_pages_with_limit_and_offset(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    ids = [
        create_program(client, auth_headers, program(squat, name=f"P{n}"))["id"]
        for n in range(5)
    ]

    response = client.get("/programs?limit=2&offset=1", headers=auth_headers)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [ids[1], ids[2]]


def test_list_programs_takes_the_same_queries_however_many_programs(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    create_program(client, auth_headers, program(squat, name="P0"))
    with count_queries() as one:
        client.get("/programs", headers=auth_headers)
    for n in range(1, 5):
        create_program(client, auth_headers, program(squat, name=f"P{n}"))

    with count_queries() as five:
        client.get("/programs", headers=auth_headers)

    assert len(five) == len(one)


def test_create_program_rejects_duplicate_name_ignoring_case(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    create_program(client, auth_headers, program(squat, name="PPL"))

    response = client.post(
        "/programs", json=program(squat, name="ppl"), headers=auth_headers
    )

    assert response.status_code == 409
    assert len(list_programs(client, auth_headers)) == 1


def test_create_program_rejects_two_days_with_the_same_position(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    body = program(days=[day(squat, position=3), day(squat, position=3)])

    response = client.post("/programs", json=body, headers=auth_headers)

    assert response.status_code == 409
    assert list_programs(client, auth_headers) == []


def test_different_users_can_have_programs_with_the_same_name(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    squat: int,
) -> None:
    create_program(client, auth_headers, program(squat, name="PPL"))
    other_squat = create_exercise(client, other_auth_headers)["id"]

    response = client.post(
        "/programs", json=program(other_squat, name="PPL"), headers=other_auth_headers
    )

    assert response.status_code == 201


@pytest.mark.parametrize(
    "overrides",
    [
        lambda e: {"name": "   "},
        lambda e: {"name": "x" * 101},
        lambda e: {"days": []},
        lambda e: {
            "days": [day(e, position=p) for p in range(1, MAX_DAYS_PER_PROGRAM + 2)]
        },
        lambda e: {"days": [day(e, position=0)]},
        lambda e: {"days": [day(e, position=MAX_DAYS_PER_PROGRAM + 1)]},
        lambda e: {"days": [day(e, name="  ")]},
        lambda e: {"days": [day()]},
        lambda e: {"days": [day(*[e] * (MAX_EXERCISES_PER_PROGRAM_DAY + 1))]},
        lambda e: {"days": [day(e) | {"exercises": [planned(e, sets=0)]}]},
        lambda e: {
            "days": [
                day(e) | {"exercises": [planned(e, sets=MAX_SETS_PER_EXERCISE + 1)]}
            ]
        },
        lambda e: {"days": [day(e) | {"exercises": [planned(e, reps=0)]}]},
        lambda e: {"days": [day(e) | {"exercises": [planned(e, reps=1001)]}]},
        lambda e: {"days": [day(e) | {"exercises": [planned(e, weight_kg=-0.5)]}]},
        lambda e: {"days": [day(e) | {"exercises": [planned(e, weight_kg=1000.5)]}]},
        lambda e: {"days": [day(0)]},
        lambda e: {"days": [day(2**31)]},
        lambda e: {"days": [day(e) | {"exercises": [{"exercise_id": e, "sets": 3}]}]},
    ],
    ids=[
        "name blank",
        "name too long",
        "no days",
        "8 days",
        "position 0",
        "position 8",
        "day name blank",
        "day without exercises",
        "21 exercises in a day",
        "0 sets",
        "51 sets",
        "0 reps",
        "1001 reps",
        "negative weight",
        "weight over 1000",
        "exercise id 0",
        "exercise id too large",
        "missing reps and weight",
    ],
)
def test_create_program_rejects_invalid_values(
    client: TestClient, auth_headers: dict[str, str], squat: int, overrides: Any
) -> None:
    body = program(squat, **overrides(squat))

    response = client.post("/programs", json=body, headers=auth_headers)

    assert response.status_code == 422
    assert list_programs(client, auth_headers) == []


@pytest.mark.parametrize(
    "query", ["limit=0", "limit=101", "offset=-1", f"offset={2**31}", "limit=a"]
)
def test_list_programs_rejects_invalid_paging(
    client: TestClient, auth_headers: dict[str, str], query: str
) -> None:
    response = client.get(f"/programs?{query}", headers=auth_headers)

    assert response.status_code == 422


def test_create_program_rejects_unknown_exercise(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    response = client.post("/programs", json=program(squat, 999), headers=auth_headers)

    assert response.status_code == 404
    assert list_programs(client, auth_headers) == []


def test_user_cannot_plan_another_users_exercise(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    squat: int,
) -> None:
    response = client.post("/programs", json=program(squat), headers=other_auth_headers)

    assert response.status_code == 404
    assert list_programs(client, other_auth_headers) == []


@pytest.mark.parametrize(
    ("method", "path"),
    [("GET", "/programs"), ("POST", "/programs"), ("GET", "/programs/1")],
)
def test_programs_endpoints_require_authentication(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(method, path, json=program(1))

    assert response.status_code == 401


def test_unknown_program_returns_404(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.get("/programs/999", headers=auth_headers)

    assert response.status_code == 404


@pytest.mark.parametrize("program_id", [0, -1, 2**31])
def test_out_of_range_program_id_returns_422(
    client: TestClient, auth_headers: dict[str, str], program_id: int
) -> None:
    response = client.get(f"/programs/{program_id}", headers=auth_headers)

    assert response.status_code == 422


def test_user_cannot_read_another_users_program(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    squat: int,
) -> None:
    created = create_program(client, auth_headers, program(squat))

    response = client.get(f"/programs/{created['id']}", headers=other_auth_headers)

    assert response.status_code == 404
