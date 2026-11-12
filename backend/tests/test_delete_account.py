from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Base
from tests.conftest import register_and_login

EMAIL = "andrei@example.com"
# The password register_and_login signs up with
PASSWORD = "correct-horse-battery"
DAY = "2026-11-12"


def user_tables() -> list[Any]:
    """Every table that can hold a user's data: all but the shared catalog."""
    return [
        table
        for table in Base.metadata.sorted_tables
        if not table.name.startswith("catalog_")
    ]


def row_counts(session: Session) -> dict[str, int]:
    return {
        table.name: session.scalar(select(func.count()).select_from(table)) or 0
        for table in user_tables()
    }


def fill_account(client: TestClient, headers: dict[str, str]) -> None:
    """Something in every table a user's data lives in."""

    def post(path: str, body: dict[str, Any]) -> dict[str, Any]:
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 201, (path, response.text)
        return response.json()

    food = post(
        "/foods",
        {
            "name": "Rice",
            "calories_per_100g": 130,
            "protein_per_100g": 2.6,
            "carbs_per_100g": 28,
            "fat_per_100g": 0.3,
        },
    )
    client.put(f"/foods/{food['id']}/favourite", headers=headers)
    post(
        "/entries",
        {"food_id": food["id"], "eaten_on": DAY, "meal_type": "lunch", "grams": 150},
    )
    post("/entries/quick", {"eaten_on": DAY, "meal_type": "snack", "calories": 200})
    squat = post("/exercises", {"name": "Squat"})
    post(
        "/workouts",
        {
            "performed_on": DAY,
            "note": "Legs",
            "exercises": [
                {"exercise_id": squat["id"], "sets": [{"reps": 5, "weight_kg": 100}]}
            ],
        },
    )
    post(
        "/programs",
        {
            "name": "Legs",
            "days": [
                {
                    "position": 1,
                    "name": "Legs",
                    "exercises": [
                        {
                            "exercise_id": squat["id"],
                            "sets": 3,
                            "reps": 5,
                            "weight_kg": 100,
                        }
                    ],
                }
            ],
        },
    )


def delete_account(
    client: TestClient, headers: dict[str, str], password: str = PASSWORD
) -> Any:
    return client.request(
        "DELETE", "/auth/me", json={"password": password}, headers=headers
    )


def test_delete_account_leaves_no_row_in_any_table(
    client: TestClient, session: Session
) -> None:
    headers = register_and_login(client, EMAIL)
    fill_account(client, headers)
    # Each table has something to delete; a new table that fill_account
    # does not reach fails here, until it does
    assert [name for name, n in row_counts(session).items() if n == 0] == []

    response = delete_account(client, headers)

    assert response.status_code == 204
    assert row_counts(session) == {table.name: 0 for table in user_tables()}


def test_delete_account_keeps_everyone_elses_data(
    client: TestClient, session: Session
) -> None:
    mine = register_and_login(client, EMAIL)
    theirs = register_and_login(client, "mallory@example.com")
    fill_account(client, mine)
    fill_account(client, theirs)
    before = row_counts(session)

    delete_account(client, mine)

    after = row_counts(session)
    # Exactly half of every table is left: the other user's half
    assert after == {name: n // 2 for name, n in before.items()}
    assert client.get("/foods", headers=theirs).json()[0]["name"] == "Rice"


def test_after_deleting_the_token_is_refused_and_the_email_is_free(
    client: TestClient,
) -> None:
    headers = register_and_login(client, EMAIL)

    delete_account(client, headers)

    assert client.get("/auth/me", headers=headers).status_code == 401
    login = client.post("/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert login.status_code == 401
    signup = client.post("/auth/signup", json={"email": EMAIL, "password": PASSWORD})
    assert signup.status_code == 201


def test_wrong_password_is_403_and_deletes_nothing(
    client: TestClient, session: Session
) -> None:
    headers = register_and_login(client, EMAIL)
    fill_account(client, headers)
    before = row_counts(session)

    response = delete_account(client, headers, password="not-my-password")

    # Not 401: the token is valid, and clients sign out on a 401
    assert response.status_code == 403
    assert row_counts(session) == before
    assert client.get("/auth/me", headers=headers).status_code == 200


@pytest.mark.parametrize("body", [None, {}, {"password": "x" * 129}])
def test_delete_account_rejects_a_missing_or_invalid_password(
    client: TestClient, session: Session, body: Any
) -> None:
    headers = register_and_login(client, EMAIL)

    response = client.request("DELETE", "/auth/me", json=body, headers=headers)

    assert response.status_code == 422
    assert client.get("/auth/me", headers=headers).status_code == 200


def test_delete_account_requires_login(client: TestClient) -> None:
    response = client.request("DELETE", "/auth/me", json={"password": PASSWORD})

    assert response.status_code == 401
