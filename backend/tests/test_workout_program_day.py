from fastapi.testclient import TestClient

from tests.test_exercises import create_exercise
from tests.test_programs import create_program, program
from tests.test_workouts import DAY, create_workout, workout

Headers = dict[str, str]


def start(client: TestClient, headers: Headers, created: dict) -> dict:
    day_id = created["days"][0]["id"]
    response = client.post(
        f"/programs/{created['id']}/days/{day_id}/workouts",
        json={"performed_on": DAY},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def test_a_workout_logged_by_hand_has_no_program_day(
    client: TestClient, auth_headers: Headers
) -> None:
    squat = create_exercise(client, auth_headers, "Squat")["id"]

    created = create_workout(client, auth_headers, workout(squat))

    assert created["program_day_id"] is None


def test_a_started_workout_remembers_its_day(
    client: TestClient, auth_headers: Headers
) -> None:
    squat = create_exercise(client, auth_headers, "Squat")["id"]
    plan = create_program(client, auth_headers, program(squat))

    started = start(client, auth_headers, plan)

    assert started["program_day_id"] == plan["days"][0]["id"]
    stored = client.get(f"/workouts/{started['id']}", headers=auth_headers).json()
    assert stored["program_day_id"] == plan["days"][0]["id"]


def test_editing_a_started_workout_keeps_its_day(
    client: TestClient, auth_headers: Headers
) -> None:
    squat = create_exercise(client, auth_headers, "Squat")["id"]
    plan = create_program(client, auth_headers, program(squat))
    started = start(client, auth_headers, plan)

    response = client.put(
        f"/workouts/{started['id']}",
        json=workout(squat, note="Heavier today"),
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json()["program_day_id"] == plan["days"][0]["id"]
