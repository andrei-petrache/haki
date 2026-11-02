from typing import Any

import pytest
from fastapi.testclient import TestClient

SQUAT = {"name": "Squat"}


def create_exercise(
    client: TestClient, headers: dict[str, str], name: str = "Squat"
) -> dict[str, Any]:
    response = client.post("/exercises", json={"name": name}, headers=headers)
    assert response.status_code == 201
    return response.json()


def test_create_exercise_returns_it_with_id(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/exercises", json={"name": "  Squat  "}, headers=auth_headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body == {"name": "Squat", "id": body["id"]}


def test_list_exercises_returns_own_exercises_sorted_ignoring_case(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    create_exercise(client, auth_headers, "squat")
    create_exercise(client, auth_headers, "Bench press")
    create_exercise(client, auth_headers, "Deadlift")
    create_exercise(client, other_auth_headers, "Curl")

    response = client.get("/exercises", headers=auth_headers)

    assert response.status_code == 200
    assert [exercise["name"] for exercise in response.json()] == [
        "Bench press",
        "Deadlift",
        "squat",
    ]


def test_rename_exercise_changes_its_name(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    exercise = create_exercise(client, auth_headers)

    response = client.put(
        f"/exercises/{exercise['id']}",
        json={"name": "Back squat"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    assert response.json() == {"name": "Back squat", "id": exercise["id"]}


def test_rename_exercise_to_a_different_case_of_its_own_name(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    exercise = create_exercise(client, auth_headers, "squat")

    response = client.put(
        f"/exercises/{exercise['id']}", json=SQUAT, headers=auth_headers
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Squat"


def test_delete_exercise_removes_it(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    exercise = create_exercise(client, auth_headers)

    response = client.delete(f"/exercises/{exercise['id']}", headers=auth_headers)

    assert response.status_code == 204
    assert client.get("/exercises", headers=auth_headers).json() == []


def test_delete_exercise_rejects_exercise_used_by_a_workout(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    exercise = create_exercise(client, auth_headers)
    workout = {
        "performed_on": "2026-11-01",
        "exercises": [
            {"exercise_id": exercise["id"], "sets": [{"reps": 5, "weight_kg": 100}]}
        ],
    }
    created = client.post("/workouts", json=workout, headers=auth_headers)
    assert created.status_code == 201

    response = client.delete(f"/exercises/{exercise['id']}", headers=auth_headers)

    assert response.status_code == 409
    assert client.get("/exercises", headers=auth_headers).json() == [exercise]
    # Once no workout uses it, it can go
    client.delete(f"/workouts/{created.json()['id']}", headers=auth_headers)
    response = client.delete(f"/exercises/{exercise['id']}", headers=auth_headers)
    assert response.status_code == 204


@pytest.mark.parametrize("body", [{"name": "   "}, {"name": "x" * 101}, {}])
def test_create_exercise_rejects_invalid_name(
    client: TestClient, auth_headers: dict[str, str], body: dict[str, Any]
) -> None:
    response = client.post("/exercises", json=body, headers=auth_headers)

    assert response.status_code == 422


@pytest.mark.parametrize("name", ["Squat", "squat", "  SQUAT "])
def test_create_exercise_rejects_duplicate_name_ignoring_case(
    client: TestClient, auth_headers: dict[str, str], name: str
) -> None:
    create_exercise(client, auth_headers)

    response = client.post("/exercises", json={"name": name}, headers=auth_headers)

    assert response.status_code == 409
    assert len(client.get("/exercises", headers=auth_headers).json()) == 1


def test_different_users_can_have_exercises_with_same_name(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    create_exercise(client, auth_headers)

    response = client.post("/exercises", json=SQUAT, headers=other_auth_headers)

    assert response.status_code == 201


def test_rename_exercise_rejects_existing_name(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    create_exercise(client, auth_headers, "Squat")
    deadlift = create_exercise(client, auth_headers, "Deadlift")

    response = client.put(
        f"/exercises/{deadlift['id']}", json={"name": "SQUAT"}, headers=auth_headers
    )

    assert response.status_code == 409


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/exercises"),
        ("POST", "/exercises"),
        ("PUT", "/exercises/1"),
        ("DELETE", "/exercises/1"),
    ],
)
def test_exercises_endpoints_require_authentication(
    client: TestClient, method: str, path: str
) -> None:
    response = client.request(method, path, json=SQUAT)

    assert response.status_code == 401


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_unknown_exercise_returns_404(
    client: TestClient, auth_headers: dict[str, str], method: str
) -> None:
    response = client.request(
        method, "/exercises/999", json=SQUAT, headers=auth_headers
    )

    assert response.status_code == 404


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
@pytest.mark.parametrize("exercise_id", [0, -1, 2**31])
def test_out_of_range_exercise_id_returns_422(
    client: TestClient, auth_headers: dict[str, str], method: str, exercise_id: int
) -> None:
    response = client.request(
        method, f"/exercises/{exercise_id}", json=SQUAT, headers=auth_headers
    )

    assert response.status_code == 422


def test_user_cannot_rename_another_users_exercise(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    exercise = create_exercise(client, auth_headers)

    response = client.put(
        f"/exercises/{exercise['id']}",
        json={"name": "Hacked"},
        headers=other_auth_headers,
    )

    assert response.status_code == 404
    assert client.get("/exercises", headers=auth_headers).json() == [exercise]


def test_user_cannot_delete_another_users_exercise(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    exercise = create_exercise(client, auth_headers)

    response = client.delete(f"/exercises/{exercise['id']}", headers=other_auth_headers)

    assert response.status_code == 404
    assert client.get("/exercises", headers=auth_headers).json() == [exercise]
