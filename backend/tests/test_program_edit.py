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


# Days sent back with their ids are kept: workouts stay linked to them


def as_body(response: dict[str, Any]) -> dict[str, Any]:
    """A program from a response as the editor sends it back, ids included."""
    return {
        "name": response["name"],
        "days": [
            {
                "id": d["id"],
                "position": d["position"],
                "name": d["name"],
                "exercises": [without_name(e) for e in d["exercises"]],
            }
            for d in response["days"]
        ],
    }


def start(
    client: TestClient, headers: dict[str, str], program_id: int, day_id: int
) -> dict[str, Any]:
    response = client.post(
        f"/programs/{program_id}/days/{day_id}/workouts",
        json={"performed_on": "2026-11-12"},
        headers=headers,
    )
    assert response.status_code == 201
    return response.json()


def linked_day(client: TestClient, headers: dict[str, str], workout_id: int) -> Any:
    return client.get(f"/workouts/{workout_id}", headers=headers).json()[
        "program_day_id"
    ]


@pytest.fixture
def push_pull(
    client: TestClient, auth_headers: dict[str, str], squat: int, deadlift: int
) -> dict[str, Any]:
    body = {
        "name": "Push/Pull",
        "days": [
            day(squat, position=1, name="Push"),
            day(deadlift, position=2, name="Pull"),
        ],
    }
    return create_program(client, auth_headers, body)


def test_a_rename_keeps_the_days_and_their_workouts(
    client: TestClient, auth_headers: dict[str, str], push_pull: dict[str, Any]
) -> None:
    push, pull = (d["id"] for d in push_pull["days"])
    workout = start(client, auth_headers, push_pull["id"], push)

    response = replace(
        client, auth_headers, push_pull["id"], {**as_body(push_pull), "name": "PP"}
    )

    assert response.status_code == 200
    assert [d["id"] for d in response.json()["days"]] == [push, pull]
    assert linked_day(client, auth_headers, workout["id"]) == push


def test_swapping_two_days_keeps_each_workout_on_its_own_day(
    client: TestClient, auth_headers: dict[str, str], push_pull: dict[str, Any]
) -> None:
    push, pull = (d["id"] for d in push_pull["days"])
    pushed = start(client, auth_headers, push_pull["id"], push)
    pulled = start(client, auth_headers, push_pull["id"], pull)
    body = as_body(push_pull)
    body["days"][0]["position"], body["days"][1]["position"] = 2, 1

    response = replace(client, auth_headers, push_pull["id"], body)

    assert response.status_code == 200
    assert [(d["position"], d["name"], d["id"]) for d in response.json()["days"]] == [
        (1, "Pull", pull),
        (2, "Push", push),
    ]
    assert linked_day(client, auth_headers, pushed["id"]) == push
    assert linked_day(client, auth_headers, pulled["id"]) == pull
    assert read(client, auth_headers, push_pull["id"]) == response.json()
    # The scratch program the move passes through is gone
    names = [p["name"] for p in client.get("/programs", headers=auth_headers).json()]
    assert names == ["Push/Pull"]


def test_a_full_week_reversed_keeps_every_day(
    client: TestClient, auth_headers: dict[str, str], squat: int
) -> None:
    week = {
        "name": "Week",
        "days": [day(squat, position=p, name=f"Day {p}") for p in range(1, 8)],
    }
    created = create_program(client, auth_headers, week)
    body = as_body(created)
    for item in body["days"]:
        item["position"] = 8 - item["position"]

    response = replace(client, auth_headers, created["id"], body)

    assert response.status_code == 200
    assert [(d["position"], d["name"]) for d in response.json()["days"]] == [
        (p, f"Day {8 - p}") for p in range(1, 8)
    ]
    assert sorted(d["id"] for d in response.json()["days"]) == sorted(
        d["id"] for d in created["days"]
    )


def test_kept_left_out_and_new_days_together(
    client: TestClient,
    auth_headers: dict[str, str],
    push_pull: dict[str, Any],
    squat: int,
) -> None:
    push, pull = (d["id"] for d in push_pull["days"])
    pulled = start(client, auth_headers, push_pull["id"], pull)
    pushed = start(client, auth_headers, push_pull["id"], push)
    # Pull stays and moves to 3; Push is left out; a new day takes position 1
    kept = as_body(push_pull)["days"][1] | {"position": 3}
    body = {"name": "Push/Pull", "days": [day(squat, position=1, name="Legs"), kept]}

    response = replace(client, auth_headers, push_pull["id"], body)

    assert response.status_code == 200
    days = response.json()["days"]
    assert [(d["position"], d["name"]) for d in days] == [(1, "Legs"), (3, "Pull")]
    assert days[1]["id"] == pull and days[0]["id"] not in (push, pull)
    assert linked_day(client, auth_headers, pulled["id"]) == pull
    assert linked_day(client, auth_headers, pushed["id"]) is None


def test_a_kept_days_exercises_are_replaced(
    client: TestClient,
    auth_headers: dict[str, str],
    push_pull: dict[str, Any],
    deadlift: int,
) -> None:
    body = as_body(push_pull)
    body["days"][0]["exercises"] = [planned(deadlift, sets=5)]

    response = replace(client, auth_headers, push_pull["id"], body)

    assert response.status_code == 200
    first = response.json()["days"][0]
    assert first["id"] == push_pull["days"][0]["id"]
    assert [without_name(e) for e in first["exercises"]] == [planned(deadlift, sets=5)]


def test_the_same_day_id_twice_is_422_and_changes_nothing(
    client: TestClient, auth_headers: dict[str, str], push_pull: dict[str, Any]
) -> None:
    body = as_body(push_pull)
    body["days"][1]["id"] = body["days"][0]["id"]

    response = replace(client, auth_headers, push_pull["id"], body)

    assert response.status_code == 422
    assert read(client, auth_headers, push_pull["id"]) == push_pull


def test_a_day_id_of_another_program_is_404_and_changes_nothing(
    client: TestClient,
    auth_headers: dict[str, str],
    push_pull: dict[str, Any],
    squat: int,
) -> None:
    other = create_program(client, auth_headers, program(squat, name="Other"))
    body = as_body(push_pull)
    body["days"][0]["id"] = other["days"][0]["id"]

    response = replace(client, auth_headers, push_pull["id"], body)

    assert response.status_code == 404
    assert read(client, auth_headers, push_pull["id"]) == push_pull
    assert read(client, auth_headers, other["id"]) == other


def test_another_users_day_id_is_404_and_changes_nothing(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
    push_pull: dict[str, Any],
) -> None:
    their_squat = create_exercise(client, other_auth_headers, "Squat")["id"]
    theirs = create_program(client, other_auth_headers, program(their_squat))
    body = as_body(push_pull)
    body["days"][0]["id"] = theirs["days"][0]["id"]

    response = replace(client, auth_headers, push_pull["id"], body)

    assert response.status_code == 404
    assert read(client, other_auth_headers, theirs["id"]) == theirs


def test_two_kept_days_moved_onto_one_position_is_409_and_changes_nothing(
    client: TestClient, auth_headers: dict[str, str], push_pull: dict[str, Any]
) -> None:
    body = as_body(push_pull)
    body["days"][0]["position"] = body["days"][1]["position"] = 3

    response = replace(client, auth_headers, push_pull["id"], body)

    assert response.status_code == 409
    assert read(client, auth_headers, push_pull["id"]) == push_pull


def test_create_ignores_day_ids(
    client: TestClient, auth_headers: dict[str, str], push_pull: dict[str, Any]
) -> None:
    body = {**as_body(push_pull), "name": "Copy"}

    created = create_program(client, auth_headers, body)

    assert {d["id"] for d in created["days"]}.isdisjoint(
        d["id"] for d in push_pull["days"]
    )
    assert read(client, auth_headers, push_pull["id"]) == push_pull
