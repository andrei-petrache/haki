"""Every error response carries a stable `code` next to its `detail`."""

import re

import pytest
from fastapi.testclient import TestClient

from app.errors import ERRORS, ApiError, ErrorCode

FOOD = {
    "name": "Oats",
    "calories_per_100g": 389,
    "protein_per_100g": 17,
    "carbs_per_100g": 66,
    "fat_per_100g": 7,
}


def create_food(client: TestClient, headers: dict[str, str]) -> int:
    response = client.post("/foods", json=FOOD, headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def test_codes_are_snake_case() -> None:
    for code in ErrorCode:
        assert re.fullmatch(r"[a-z]+(_[a-z]+)*", code), code


@pytest.mark.parametrize("code", list(ERRORS))
def test_each_raised_code_has_a_4xx_or_5xx_status_and_a_message(
    code: ErrorCode,
) -> None:
    error = ApiError(code)

    assert 400 <= error.status_code < 600
    assert error.detail
    assert error.code == code


def test_an_unknown_path_is_not_found(client: TestClient) -> None:
    response = client.get("/no-such-path")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found", "code": "not_found"}


def test_a_wrong_method_is_method_not_allowed(client: TestClient) -> None:
    response = client.patch("/health")

    assert response.status_code == 405
    assert response.json()["code"] == "method_not_allowed"


def test_invalid_input_keeps_the_list_of_problems(
    client: TestClient, auth_headers: dict[str, str]
) -> None:
    response = client.post(
        "/foods", json={**FOOD, "calories_per_100g": -1}, headers=auth_headers
    )

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert body["detail"][0]["loc"] == ["body", "calories_per_100g"]


def test_a_request_without_a_token(client: TestClient) -> None:
    response = client.get("/foods")

    assert response.status_code == 401
    assert response.json() == {
        "detail": "Not authenticated",
        "code": "not_authenticated",
    }
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_a_request_with_a_bad_token(client: TestClient) -> None:
    response = client.get("/foods", headers={"Authorization": "Bearer nonsense"})

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_token"
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_a_wrong_login(client: TestClient, auth_headers: dict[str, str]) -> None:
    response = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "invalid_credentials"


def test_a_taken_email(client: TestClient) -> None:
    account = {"email": "taken@example.com", "password": "correct-horse-battery"}
    assert client.post("/auth/signup", json=account).status_code == 201

    response = client.post("/auth/signup", json=account)

    assert response.status_code == 409
    assert response.json() == {
        "detail": "Email already registered",
        "code": "email_taken",
    }


def test_another_users_food_is_food_not_found(
    client: TestClient,
    auth_headers: dict[str, str],
    other_auth_headers: dict[str, str],
) -> None:
    food_id = create_food(client, other_auth_headers)

    response = client.delete(f"/foods/{food_id}", headers=auth_headers)

    assert response.status_code == 404
    assert response.json() == {"detail": "Food not found", "code": "food_not_found"}
    assert len(client.get("/foods", headers=other_auth_headers).json()) == 1


def test_a_food_in_use(client: TestClient, auth_headers: dict[str, str]) -> None:
    food_id = create_food(client, auth_headers)
    entry = {
        "food_id": food_id,
        "eaten_on": "2026-11-13",
        "meal_type": "breakfast",
        "grams": 80,
    }
    assert client.post("/entries", json=entry, headers=auth_headers).status_code == 201

    response = client.delete(f"/foods/{food_id}", headers=auth_headers)

    assert response.status_code == 409
    assert response.json()["code"] == "food_in_use"


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("/entries/999", "entry_not_found"),
        ("/workouts/999", "workout_not_found"),
        ("/programs/999", "program_not_found"),
        ("/exercises/999", "exercise_not_found"),
        ("/catalog/foods/999", "catalog_food_not_found"),
        ("/catalog/exercises/999", "catalog_exercise_not_found"),
    ],
)
def test_missing_resources_name_what_is_missing(
    client: TestClient, auth_headers: dict[str, str], path: str, code: str
) -> None:
    method = "DELETE" if path.startswith(("/entries", "/exercises")) else "GET"

    response = client.request(method, path, headers=auth_headers)

    assert response.status_code == 404
    assert response.json()["code"] == code


def test_a_taken_program_name(client: TestClient, auth_headers: dict[str, str]) -> None:
    exercise = client.post("/exercises", json={"name": "Squat"}, headers=auth_headers)
    planned = {
        "exercise_id": exercise.json()["id"],
        "sets": 3,
        "reps": 5,
        "weight_kg": 100,
    }
    day = {"position": 1, "name": "Legs", "exercises": [planned]}
    program = {"name": "Strength", "days": [day]}
    first = client.post("/programs", json=program, headers=auth_headers)
    assert first.status_code == 201

    response = client.post("/programs", json=program, headers=auth_headers)

    assert response.status_code == 409
    assert response.json()["code"] == "program_conflict"
