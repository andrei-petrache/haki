from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.test_exercises import create_exercise
from tests.test_programs import create_program, day, planned, program, without_name


@pytest.fixture
def squat(client: TestClient, auth_headers: dict[str, str]) -> int:
    return create_exercise(client, auth_headers, "Squat")["id"]


@pytest.fixture
def deadlift(client: TestClient, auth_headers: dict[str, str]) -> int:
    return create_exercise(client, auth_headers, "Deadlift")["id"]


def replace(
    client: TestClient, headers: dict[str, str], program_id: int, body: dict[str, Any]
) -> Any:
    return client.put(f"/programs/{program_id}", json=body, headers=headers)


def read(client: TestClient, headers: dict[str, str], program_id: int) -> Any:
    return client.get(f"/programs/{program_id}", headers=headers).json()


def test_replace_program_replaces_name_and_days(
    client: TestClient, auth_headers: dict[str, str], squat: int, deadlift: int
) -> None:
    created = create_program(client, auth_headers, program(squat))
    body = {
        "name": "  Upper/Lower  ",
        "days": [
            # Position 1 again, and a new position 4
            {"position": 1, "name": "Lower", "exercises": [planned(deadlift, sets=5)]},
            day(squat, deadlift, position=4, name="Full"),
        ],
    }

    response = replace(client, auth_headers, created["id"], body)

    assert response.status_code == 200
    replaced = response.json()
    assert replaced["id"] == created["id"]
    assert replaced["name"] == "Upper/Lower"
    assert [(d["position"], d["name"]) for d in replaced["days"]] == [
        (1, "Lower"),
        (4, "Full"),
    ]
    assert [without_name(e) for e in replaced["days"][0]["exercises"]] == [
        planned(deadlift, sets=5)
    ]
    assert read(client, auth_headers, created["id"]) == replaced


def test_a_replaced_programs_days_start_workouts(
    client: TestClient, auth_headers: dict[str, str], squat: int, deadlift: int
) -> None:
    # Clients re-read the day ids from the response: the days are new rows
    created = create_program(client, auth_headers, program(squat))
    replaced = replace(client, auth_headers, created["id"], program(deadlift)).json()
    day_id = replaced["days"][0]["id"]

    response = client.post(
        f"/programs/{created['id']}/days/{day_id}/workouts",
        json={"performed_on": "2026-11-12"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    assert [e["exercise_id"] for e in response.json()["exercises"]] == [deadlift]


def test_replace_program_leaves_started_workouts_alone(
    client: TestClient, auth_headers: dict[str, str], squat: int, deadlift: int
) -> None:
    created = create_program(client, auth_headers, program(squat))
    day_id = created["days"][0]["id"]
    started = client.post(
        f"/programs/{created['id']}/days/{day_id}/workouts",
        json={"performed_on": "2026-11-12"},
        headers=auth_headers,
    ).json()

    replace(client, auth_headers, created["id"], program(deadlift))

    workout = client.get(f"/workouts/{started['id']}", headers=auth_headers).json()
    # What was done stays; the replaced day is gone, so the link is cleared
    assert started["program_day_id"] == day_id
    assert workout == {**started, "program_day_id": None, "program_id": None}


def test_replace_program_keeps_its_own_name(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    created = create_program(client, auth_headers, program(squat, name="PPL"))

    response = replace(client, auth_headers, created["id"], program(squat, name="ppl"))

    assert response.status_code == 200
    assert response.json()["name"] == "ppl"


def test_replace_program_rejects_another_programs_name_and_keeps_it(
    client: TestClient, auth_headers: dict[str, str], squat: int, deadlift: int
) -> None:
    create_program(client, auth_headers, program(squat, name="PPL"))
    other = create_program(client, auth_headers, program(squat, name="Upper/Lower"))

    response = replace(client, auth_headers, other["id"], program(deadlift, name="ppl"))

    assert response.status_code == 409
    assert read(client, auth_headers, other["id"]) == other


def test_replace_program_rejects_two_days_on_one_position_and_keeps_it(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    created = create_program(client, auth_headers, program(squat))
    body = program(squat, days=[day(squat, position=2), day(squat, position=2)])

    response = replace(client, auth_headers, created["id"], body)

    assert response.status_code == 409
    assert read(client, auth_headers, created["id"]) == created


def test_replace_program_rejects_another_users_exercise_and_keeps_it(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    squat: int,
) -> None:
    created = create_program(client, auth_headers, program(squat))
    theirs = create_exercise(client, other_auth_headers, "Bench")["id"]

    response = replace(client, auth_headers, created["id"], program(theirs))

    assert response.status_code == 404
    assert read(client, auth_headers, created["id"]) == created


def test_user_cannot_replace_another_users_program(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    squat: int,
) -> None:
    created = create_program(client, auth_headers, program(squat))
    their_squat = create_exercise(client, other_auth_headers, "Squat")["id"]

    response = replace(client, other_auth_headers, created["id"], program(their_squat))

    assert response.status_code == 404
    assert read(client, auth_headers, created["id"]) == created


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "days": []},
        {"name": "PPL", "days": []},
        {"name": "PPL"},
    ],
)
def test_replace_program_rejects_invalid_bodies(
    client: TestClient, auth_headers: dict[str, str], squat: int, body: dict[str, Any]
) -> None:
    created = create_program(client, auth_headers, program(squat))

    response = replace(client, auth_headers, created["id"], body)

    assert response.status_code == 422
    assert read(client, auth_headers, created["id"]) == created


def test_replace_unknown_program_is_404(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    assert replace(client, auth_headers, 999, program(squat)).status_code == 404


def test_replace_program_requires_login(client: TestClient) -> None:
    assert client.put("/programs/1", json=program(1)).status_code == 401
